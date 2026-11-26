from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from app.database.game_repository import GameRepository
from app.services.chess_com_service import (
    ChessComConnectionError,
    ChessComService,
    InvalidChessComResponseError,
    PlayerNotFoundError,
    RateLimitError,
    ChessComTimeoutError,
)


GAME_PGN = """\
[Event "Chess.com Blitz"]
[Site "Chess.com"]
[Date "2024.01.02"]
[Round "-"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""

SECOND_GAME_PGN = """\
[Event "Chess.com Rapid"]
[Site "Chess.com"]
[Date "2024.02.03"]
[Round "-"]
[White "Carol"]
[Black "Dave"]
[Result "0-1"]

1. d4 d5 2. c4 0-1
"""


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def install_http_mock(monkeypatch, responses, requested=None) -> None:
    pending = iter(responses)

    def fake_get(url, *, headers, timeout):
        if requested is not None:
            requested.append((url, headers, timeout))
        response = next(pending)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("app.services.chess_com_service.requests.get", fake_get)


def test_get_profile_returns_public_profile_and_sets_user_agent(monkeypatch) -> None:
    requested = []
    install_http_mock(
        monkeypatch,
        [FakeResponse(200, {"username": "alice", "title": "WGM"})],
        requested,
    )
    service = ChessComService(timeout=4)

    profile = service.get_profile("alice")

    assert profile == {"username": "alice", "title": "WGM"}
    assert requested[0][0] == "https://api.chess.com/pub/player/alice"
    assert requested[0][1]["User-Agent"] == service.USER_AGENT
    assert requested[0][2] == 4


def test_get_archives_returns_archive_urls(monkeypatch) -> None:
    archives = [
        "https://api.chess.com/pub/player/alice/games/2024/01",
        "https://api.chess.com/pub/player/alice/games/2024/02",
    ]
    install_http_mock(monkeypatch, [FakeResponse(200, {"archives": archives})])

    assert ChessComService().get_archives("alice") == archives


def test_fetches_parties_from_last_months_sequentially(monkeypatch) -> None:
    requested = []
    archives = [
        "https://api.chess.com/pub/player/alice/games/2024/01",
        "https://api.chess.com/pub/player/alice/games/2024/02",
        "https://api.chess.com/pub/player/alice/games/2024/03",
    ]
    install_http_mock(
        monkeypatch,
        [
            FakeResponse(200, {"archives": archives}),
            FakeResponse(200, {"games": [{"pgn": SECOND_GAME_PGN}]}),
            FakeResponse(200, {"games": [{"pgn": GAME_PGN}]}),
        ],
        requested,
    )

    games = ChessComService().fetch_games("alice", months=2)

    assert len(games) == 2
    assert [game.headers["White"] for game in games] == ["Carol", "Alice"]
    assert [request[0] for request in requested] == [
        "https://api.chess.com/pub/player/alice/games/archives",
        archives[2],
        archives[1],
    ]


def test_fetches_all_archives_when_all_history_is_selected(monkeypatch) -> None:
    archives = [
        "https://api.chess.com/pub/player/alice/games/2023/12",
        "https://api.chess.com/pub/player/alice/games/2024/01",
    ]
    requested = []
    install_http_mock(
        monkeypatch,
        [
            FakeResponse(200, {"archives": archives}),
            FakeResponse(200, {"games": [{"pgn": GAME_PGN}]}),
            FakeResponse(200, {"games": [{"pgn": SECOND_GAME_PGN}]}),
        ],
        requested,
    )

    games = ChessComService().fetch_games("alice", all_history=True)

    assert len(games) == 2
    assert [request[0] for request in requested[1:]] == list(reversed(archives))


def test_nonexistent_player_raises_clear_error(monkeypatch) -> None:
    install_http_mock(monkeypatch, [FakeResponse(404)])

    with pytest.raises(PlayerNotFoundError):
        ChessComService().get_profile("unknown")


def test_rate_limit_raises_clear_error(monkeypatch) -> None:
    install_http_mock(monkeypatch, [FakeResponse(429)])

    with pytest.raises(RateLimitError):
        ChessComService().get_archives("alice")


def test_timeout_raises_clear_error(monkeypatch) -> None:
    install_http_mock(monkeypatch, [requests.Timeout("timed out")])

    with pytest.raises(ChessComTimeoutError):
        ChessComService().get_profile("alice")


def test_connection_error_raises_clear_error(monkeypatch) -> None:
    install_http_mock(monkeypatch, [requests.ConnectionError("offline")])

    with pytest.raises(ChessComConnectionError):
        ChessComService().get_profile("alice")


def test_invalid_json_raises_clear_error(monkeypatch) -> None:
    install_http_mock(
        monkeypatch,
        [FakeResponse(200, ValueError("invalid JSON"))],
    )

    with pytest.raises(InvalidChessComResponseError):
        ChessComService().get_profile("alice")


def test_skips_invalid_pgn_without_stopping_import(monkeypatch) -> None:
    install_http_mock(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "archives": [
                        "https://api.chess.com/pub/player/alice/games/2024/01"
                    ]
                },
            ),
            FakeResponse(
                200,
                {
                    "games": [
                        {"pgn": "not a valid PGN"},
                        {"pgn": GAME_PGN},
                        {"pgn": None},
                    ]
                },
            ),
        ],
    )

    games = ChessComService().fetch_games("alice", months=1)

    assert len(games) == 1
    assert games[0].headers["White"] == "Alice"


def test_import_does_not_save_duplicates_to_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = GameRepository(tmp_path / "chess.sqlite3")
    requested = []
    archive_url = "https://api.chess.com/pub/player/alice/games/2024/01"
    install_http_mock(
        monkeypatch,
        [
            FakeResponse(200, {"archives": [archive_url]}),
            FakeResponse(
                200,
                {"games": [{"pgn": GAME_PGN}, {"pgn": GAME_PGN}]},
            ),
            FakeResponse(200, {"archives": [archive_url]}),
            FakeResponse(200, {"games": [{"pgn": GAME_PGN}]}),
        ],
        requested,
    )
    service = ChessComService(repository=repository)

    first_import = service.import_games("alice", months=1)
    second_import = service.import_games("alice", months=1)

    assert len(first_import) == 1
    assert second_import == []
    assert len(repository.get_all_games()) == 1


def test_invalid_api_json_shape_raises_clear_error(monkeypatch) -> None:
    install_http_mock(monkeypatch, [FakeResponse(200, {"archives": "not-a-list"})])

    with pytest.raises(InvalidChessComResponseError):
        ChessComService().get_archives("alice")
