from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import chess
import chess.pgn
import requests

from app.database.game_repository import GameRepository
from app.models.game_record import GameRecord
from app.services.pgn_service import parse_first_game


class ChessComAPIError(Exception):
    """Base error for Chess.com PubAPI failures."""


class PlayerNotFoundError(ChessComAPIError):
    """The requested public Chess.com profile does not exist."""


class RateLimitError(ChessComAPIError):
    """Chess.com rejected the request due to rate limiting."""


class ChessComConnectionError(ChessComAPIError):
    """A network connection to Chess.com could not be established."""


class ChessComTimeoutError(ChessComAPIError):
    """A Chess.com PubAPI request timed out."""


class InvalidChessComResponseError(ChessComAPIError):
    """Chess.com returned an invalid response."""


class ImportCancelledError(ChessComAPIError):
    """The Chess.com import was cancelled by the caller."""


@dataclass(frozen=True)
class ChessComImportSummary:
    found_count: int
    imported_games: list[chess.pgn.Game]

    @property
    def imported_count(self) -> int:
        return len(self.imported_games)


class ChessComService:
    BASE_URL = "https://api.chess.com/pub"
    USER_AGENT = "ChessAnalyzer/0.1.0 (Python chess game importer)"
    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        repository: GameRepository | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Таймаут должен быть положительным")
        self.repository = repository
        self.timeout = timeout

    def get_profile(self, username: str) -> dict[str, Any]:
        url = f"{self.BASE_URL}/player/{self._normalize_username(username)}"
        payload = self._get_json(url)
        if not isinstance(payload, dict):
            raise InvalidChessComResponseError(
                "Chess.com вернул некорректные данные профиля"
            )
        return payload

    def get_archives(self, username: str) -> list[str]:
        url = (
            f"{self.BASE_URL}/player/{self._normalize_username(username)}"
            "/games/archives"
        )
        payload = self._get_json(url)
        if not isinstance(payload, dict):
            raise InvalidChessComResponseError(
                "Chess.com вернул некорректный список архивов"
            )

        archives = payload.get("archives")
        if not isinstance(archives, list) or not all(
            isinstance(archive, str) for archive in archives
        ):
            raise InvalidChessComResponseError(
                "В ответе Chess.com отсутствует корректный список архивов"
            )
        return archives

    def fetch_games(
        self,
        username: str,
        months: int = 3,
        all_history: bool = False,
        cancellation_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[chess.pgn.Game]:
        if not all_history and (not isinstance(months, int) or months <= 0):
            raise ValueError("Количество месяцев должно быть положительным целым числом")

        self._check_cancelled(cancellation_check)
        if progress_callback is not None:
            progress_callback("Получение списка архивов Chess.com...")
        archives = self.get_archives(username)
        selected_archives = archives if all_history else archives[-months:]
        games: list[chess.pgn.Game] = []
        seen_signatures: set[tuple[Any, ...]] = set()

        for archive_index, archive_url in enumerate(reversed(selected_archives), start=1):
            self._check_cancelled(cancellation_check)
            self._validate_archive_url(archive_url)
            if progress_callback is not None:
                progress_callback(
                    f"Загрузка архива {archive_index} из {len(selected_archives)}..."
                )
            payload = self._get_json(archive_url)
            if not isinstance(payload, dict):
                raise InvalidChessComResponseError(
                    "Chess.com вернул некорректный месячный архив"
                )

            archive_games = payload.get("games")
            if not isinstance(archive_games, list):
                raise InvalidChessComResponseError(
                    "В месячном архиве отсутствует корректный список партий"
                )

            for archive_game in archive_games:
                self._check_cancelled(cancellation_check)
                if not isinstance(archive_game, dict):
                    continue
                pgn_text = archive_game.get("pgn")
                if not isinstance(pgn_text, str):
                    continue
                try:
                    game = parse_first_game(pgn_text)
                except ValueError:
                    continue

                signature = self._game_signature(game)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                games.append(game)

        return games

    def import_games(
        self,
        username: str,
        months: int = 3,
        all_history: bool = False,
        cancellation_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[chess.pgn.Game]:
        return self.import_games_with_summary(
            username,
            months=months,
            all_history=all_history,
            cancellation_check=cancellation_check,
            progress_callback=progress_callback,
        ).imported_games

    def import_games_with_summary(
        self,
        username: str,
        months: int = 3,
        all_history: bool = False,
        cancellation_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> ChessComImportSummary:
        games = self.fetch_games(
            username,
            months=months,
            all_history=all_history,
            cancellation_check=cancellation_check,
            progress_callback=progress_callback,
        )
        self._check_cancelled(cancellation_check)
        repository = self.repository
        if repository is None:
            repository = GameRepository()
            self.repository = repository

        existing_signatures = set()
        for record in repository.get_all_games():
            signature = self._record_signature(record)
            if signature is not None:
                existing_signatures.add(signature)
        imported_games: list[chess.pgn.Game] = []

        for game in games:
            self._check_cancelled(cancellation_check)
            signature = self._game_signature(game)
            if signature in existing_signatures:
                continue
            repository.save_game(game)
            existing_signatures.add(signature)
            imported_games.append(game)

        return ChessComImportSummary(
            found_count=len(games),
            imported_games=imported_games,
        )

    def _get_json(self, url: str) -> Any:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            raise ChessComTimeoutError(
                "Истекло время ожидания ответа Chess.com"
            ) from error
        except requests.ConnectionError as error:
            raise ChessComConnectionError(
                "Не удалось подключиться к Chess.com"
            ) from error
        except requests.RequestException as error:
            raise ChessComAPIError(f"Ошибка запроса к Chess.com: {error}") from error

        if response.status_code == 404:
            raise PlayerNotFoundError("Публичный профиль Chess.com не найден")
        if response.status_code == 429:
            raise RateLimitError(
                "Chess.com временно ограничил частоту запросов. Попробуйте позже"
            )
        if not 200 <= response.status_code < 300:
            raise ChessComAPIError(
                f"Chess.com вернул HTTP-ошибку {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as error:
            raise InvalidChessComResponseError(
                "Chess.com вернул некорректный JSON"
            ) from error

    @staticmethod
    def _normalize_username(username: str) -> str:
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Укажите имя пользователя Chess.com")
        return quote(username.strip(), safe="")

    @classmethod
    def _validate_archive_url(cls, archive_url: str) -> None:
        parsed_url = urlsplit(archive_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "api.chess.com"
            or not parsed_url.path.startswith("/pub/player/")
            or "/games/" not in parsed_url.path
        ):
            raise InvalidChessComResponseError(
                "Список архивов содержит недопустимый адрес"
            )

    @staticmethod
    def _game_signature(game: chess.pgn.Game) -> tuple[Any, ...]:
        headers = game.headers
        board = game.board()
        moves = tuple(move.uci() for move in game.mainline_moves())
        return (
            board.fen(),
            moves,
            headers.get("White", "?").casefold(),
            headers.get("Black", "?").casefold(),
            headers.get("Date", "????.??.??"),
            headers.get("Result", "*"),
        )

    @classmethod
    def _record_signature(cls, record: GameRecord) -> tuple[Any, ...] | None:
        try:
            return cls._game_signature(parse_first_game(record.pgn_text))
        except ValueError:
            return None

    @staticmethod
    def _check_cancelled(
        cancellation_check: Callable[[], bool] | None,
    ) -> None:
        if cancellation_check is not None and cancellation_check():
            raise ImportCancelledError("Импорт отменён")
