from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import chess.polyglot

from app.engine.stockfish_engine import StockfishEngine
from app.models.game_record import parse_elo
from app.models.move_analysis import (
    GameAnalysisResult,
    MoveCategory,
    MoveClassification,
)


class MoveClassificationError(RuntimeError):
    pass


class GameMoveClassifier:
    """Approximate move labels from a calibrated score curve and tactics.

    Expected points use Lichess's published logistic win-percent coefficient
    (0.00368208 per centipawn), with the player Elo difference added in Elo
    log-odds. Unlike rounded engine WDL counts, the curve remains continuous
    when an engine reports a decisive position. This approximation is not
    Chess.com's unpublished Expected Points formula.
    """

    MULTIPV_COUNT = 4
    LICHESS_CP_LOGIT = 0.00368208
    MAX_CP_FOR_EXPECTED_POINTS = 1000
    EXPECTED_POINTS_TOLERANCE = 0.005
    BEST_MAX_LOSS = 0.005
    EXCELLENT_MAX_LOSS = 0.02
    GOOD_MAX_LOSS = 0.05
    INACCURACY_MAX_LOSS = 0.10
    MISTAKE_MAX_LOSS = 0.20
    BRILLIANT_MAX_LOSS = 0.01
    BRILLIANT_MAX_CENTIPAWN_LOSS = 35
    BRILLIANT_MIN_DEPTH = 10
    MATERIAL_VALUES = {
        chess.PAWN: 1.0,
        chess.KNIGHT: 3.0,
        chess.BISHOP: 3.0,
        chess.ROOK: 5.0,
        chess.QUEEN: 9.0,
        chess.KING: 0.0,
    }

    def __init__(
        self,
        engine: StockfishEngine,
        time_limit: float = 0.25,
        opening_book_path: str | Path | None = None,
    ) -> None:
        if time_limit <= 0:
            raise ValueError("Ограничение времени должно быть положительным.")
        self.engine = engine
        self.time_limit = time_limit
        self.opening_book_path = (
            Path(opening_book_path) if opening_book_path is not None else None
        )

    def classify(
        self,
        game: chess.pgn.Game,
        white_elo: int | None = None,
        black_elo: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> GameAnalysisResult:
        white_elo = parse_elo(
            str(white_elo) if white_elo is not None else game.headers.get("WhiteElo")
        )
        black_elo = parse_elo(
            str(black_elo) if black_elo is not None else game.headers.get("BlackElo")
        )
        total_moves = self._count_moves(game)
        completed_moves = 0
        results: list[MoveClassification] = []
        book_warning: str | None = None

        def analyze_tree(
            node: chess.pgn.GameNode,
            path: tuple[str, ...],
            previous_opponent_loss: float | None,
            book_reader: chess.polyglot.MemoryMappedReader | None,
        ) -> None:
            nonlocal completed_moves
            if not node.variations:
                return

            board = node.board()
            mover = board.turn
            player_elo, opponent_elo = (
                (white_elo, black_elo)
                if mover == chess.WHITE
                else (black_elo, white_elo)
            )
            candidates = self.engine.analyze_variations(
                board,
                self.time_limit,
                count=self.MULTIPV_COUNT,
            )
            candidate_values: dict[chess.Move, float] = {}
            candidate_infos: dict[chess.Move, chess.engine.InfoDict] = {}
            for info in candidates:
                pv = info.get("pv")
                if not isinstance(pv, list) or not pv or not board.is_legal(pv[0]):
                    continue
                candidate_values.setdefault(
                    pv[0],
                    self._expected_points(
                        info,
                        mover,
                        player_elo,
                        opponent_elo,
                        board.ply(),
                    ),
                )
                candidate_infos.setdefault(pv[0], info)

            if not candidate_values:
                raise MoveClassificationError(
                    f"Stockfish не вернул оцениваемые варианты перед ходом "
                    f"{len(path) + 1}."
                )
            best_expected = max(candidate_values.values())

            for child in node.variations:
                move = child.move
                next_path = path + (move.uci(),)
                board_after_move = child.board()
                actual_info = self.engine.analyze(
                    board_after_move,
                    self.time_limit,
                )
                actual_expected = self._expected_points(
                    actual_info,
                    mover,
                    player_elo,
                    opponent_elo,
                    board_after_move.ply(),
                )
                expected_loss = max(
                    0.0,
                    min(1.0, best_expected - actual_expected),
                )
                category = self._classify_category(
                    board=board,
                    move=move,
                    board_after_move=board_after_move,
                    actual_info=actual_info,
                    actual_expected=actual_expected,
                    expected_loss=expected_loss,
                    best_expected=best_expected,
                    candidate_values=candidate_values,
                    candidate_infos=candidate_infos,
                    previous_opponent_loss=previous_opponent_loss,
                    book_reader=book_reader,
                )
                results.append(
                    MoveClassification(
                        move_path=next_path,
                        san=board.san(move),
                        category=category,
                        expected_points_loss=expected_loss,
                    )
                )
                completed_moves += 1
                if progress_callback is not None:
                    progress_callback(completed_moves, total_moves)
                analyze_tree(child, next_path, expected_loss, book_reader)

        reader: chess.polyglot.MemoryMappedReader | None = None
        if self.opening_book_path is None:
            book_warning = (
                "Файл Polyglot не настроен; анализ продолжен без дебютной базы."
            )
        else:
            try:
                reader = chess.polyglot.open_reader(self.opening_book_path)
                self._validate_book(reader)
            except (OSError, ValueError, IndexError) as error:
                if reader is not None:
                    reader.close()
                    reader = None
                book_warning = (
                    "Не удалось открыть или проверить Polyglot-базу "
                    f"{self.opening_book_path}: {error}. "
                    "Анализ продолжен без дебютной базы."
                )

        try:
            analyze_tree(game, (), None, reader)
        finally:
            if reader is not None:
                reader.close()

        return GameAnalysisResult(
            white_elo=white_elo,
            black_elo=black_elo,
            classifications=tuple(results),
            opening_book_warning=book_warning,
        )

    @staticmethod
    def _expected_points(
        info: chess.engine.InfoDict,
        player_color: chess.Color,
        player_elo: int,
        opponent_elo: int,
        ply: int,
    ) -> float:
        score = info.get("score")
        if score is not None:
            try:
                side_score = score.pov(player_color)
                mate = side_score.mate()
                if mate is not None:
                    return 1.0 if mate > 0 else 0.0
                centipawns = side_score.score()
            except (AttributeError, TypeError, ValueError) as error:
                raise MoveClassificationError(
                    "Stockfish вернул некорректную оценку позиции."
                ) from error
            if centipawns is None:
                raise MoveClassificationError(
                    "Stockfish не вернул числовую оценку позиции."
                )
            centipawns = max(
                -GameMoveClassifier.MAX_CP_FOR_EXPECTED_POINTS,
                min(GameMoveClassifier.MAX_CP_FOR_EXPECTED_POINTS, centipawns),
            )
            rating_difference = max(
                -800,
                min(800, player_elo - opponent_elo),
            )
            log_odds = (
                GameMoveClassifier.LICHESS_CP_LOGIT * centipawns
                + rating_difference * math.log(10.0) / 400.0
            )
            return 1.0 / (1.0 + math.exp(-log_odds))

        wdl = info.get("wdl")
        if isinstance(wdl, chess.engine.PovWdl):
            wdl = wdl.pov(player_color)
        if wdl is None:
            raise MoveClassificationError(
                "Stockfish не вернул оценку или WDL позиции."
            )
        try:
            wins = float(wdl.wins)
            draws = float(wdl.draws)
            losses = float(wdl.losses)
        except (AttributeError, TypeError, ValueError) as error:
            raise MoveClassificationError(
                "Stockfish вернул некорректное распределение WDL."
            ) from error
        if (
            not all(math.isfinite(value) and value >= 0 for value in (wins, draws, losses))
            or wins + draws + losses <= 0
        ):
            raise MoveClassificationError(
                "Stockfish вернул некорректное распределение WDL."
            )

        total = wins + draws + losses
        decisive = wins + losses
        if decisive == 0:
            return 0.5

        # WDL-only engine results use a rating adjustment because no continuous
        # centipawn score is available to evaluate with the calibrated curve.
        win_share = wins / decisive
        win_share = min(1.0 - 1e-6, max(1e-6, win_share))
        log_odds = math.log(win_share / (1.0 - win_share))
        rating_difference = max(
            -800,
            min(800, player_elo - opponent_elo),
        )
        log_odds += rating_difference * math.log(10.0) / 400.0
        adjusted_win_share = 1.0 / (1.0 + math.exp(-log_odds))

        expected_points = (
            (decisive / total) * adjusted_win_share
            + 0.5 * (draws / total)
        )
        return min(1.0, max(0.0, expected_points))

    @staticmethod
    def _validate_book(reader: chess.polyglot.MemoryMappedReader) -> None:
        if not len(reader):
            raise ValueError("файл Polyglot пуст")
        previous_key = -1
        for index in range(len(reader)):
            entry = reader[index]
            if entry.key < previous_key:
                raise ValueError(
                    "записи Polyglot не отсортированы по ключу позиции"
                )
            if entry.move.promotion not in (
                None,
                chess.KNIGHT,
                chess.BISHOP,
                chess.ROOK,
                chess.QUEEN,
            ):
                raise ValueError(
                    "обнаружен некорректный ход в Polyglot-записи"
                )
            if entry.move.from_square == entry.move.to_square:
                raise ValueError("обнаружен некорректный ход в Polyglot-записи")
            previous_key = entry.key

    @staticmethod
    def _count_moves(node: chess.pgn.GameNode) -> int:
        return sum(
            1 + GameMoveClassifier._count_moves(child)
            for child in node.variations
        )

    def _classify_category(
        self,
        board: chess.Board,
        move: chess.Move,
        board_after_move: chess.Board,
        actual_info: chess.engine.InfoDict,
        actual_expected: float,
        expected_loss: float,
        best_expected: float,
        candidate_values: dict[chess.Move, float],
        candidate_infos: dict[chess.Move, chess.engine.InfoDict],
        previous_opponent_loss: float | None,
        book_reader: chess.polyglot.MemoryMappedReader | None,
    ) -> MoveCategory:
        if board_after_move.is_checkmate():
            return MoveCategory.BEST

        if book_reader is not None and any(
            entry.move == move for entry in book_reader.find_all(board)
        ):
            return MoveCategory.BOOK

        candidate_info = candidate_infos.get(move)
        candidate_expected = candidate_values.get(move)
        if (
            candidate_info is not None
            and candidate_expected is not None
            and expected_loss <= self.BRILLIANT_MAX_LOSS
            and best_expected - candidate_expected <= self.BRILLIANT_MAX_LOSS
            and self._has_sufficient_depth(candidate_info)
            and self._has_sufficient_depth(actual_info)
            and self._is_near_best_by_centipawns(
                move,
                board.turn,
                candidate_infos,
            )
            and self._is_material_sacrifice(
                board,
                move,
                board_after_move,
                actual_info,
            )
        ):
            return MoveCategory.BRILLIANT

        if self._is_great_move(
            move,
            best_expected,
            expected_loss,
            candidate_values,
        ):
            return MoveCategory.GREAT

        if self._is_missed_opportunity(
            previous_opponent_loss,
            best_expected,
            actual_expected,
            expected_loss,
        ):
            return MoveCategory.MISS

        return self._quality_category(expected_loss)

    @classmethod
    def _is_near_best_by_centipawns(
        cls,
        move: chess.Move,
        player_color: chess.Color,
        candidate_infos: dict[chess.Move, chess.engine.InfoDict],
    ) -> bool:
        candidate_scores: dict[chess.Move, int] = {}
        for candidate, info in candidate_infos.items():
            score = info.get("score")
            if score is None:
                continue
            try:
                candidate_score = score.pov(player_color).score(mate_score=100_000)
            except (AttributeError, TypeError, ValueError):
                continue
            if candidate_score is not None:
                candidate_scores[candidate] = candidate_score

        if move not in candidate_scores:
            return False
        best_score = max(candidate_scores.values())
        return (
            best_score - candidate_scores[move]
            <= cls.BRILLIANT_MAX_CENTIPAWN_LOSS
        )

    @classmethod
    def _quality_category(cls, expected_loss: float) -> MoveCategory:
        if not math.isfinite(expected_loss) or expected_loss < 0:
            raise ValueError("Потеря ожидаемых очков должна быть конечной.")
        tolerance = cls.EXPECTED_POINTS_TOLERANCE
        if expected_loss <= cls.BEST_MAX_LOSS:
            return MoveCategory.BEST
        if expected_loss <= cls.EXCELLENT_MAX_LOSS + tolerance:
            return MoveCategory.EXCELLENT
        if expected_loss <= cls.GOOD_MAX_LOSS + tolerance:
            return MoveCategory.GOOD
        if expected_loss <= cls.INACCURACY_MAX_LOSS + tolerance:
            return MoveCategory.INACCURACY
        if expected_loss <= cls.MISTAKE_MAX_LOSS + tolerance:
            return MoveCategory.MISTAKE
        return MoveCategory.BLUNDER

    @classmethod
    def _is_great_move(
        cls,
        move: chess.Move,
        best_expected: float,
        expected_loss: float,
        candidate_values: dict[chess.Move, float],
    ) -> bool:
        if (
            expected_loss > cls.BEST_MAX_LOSS
            or len(candidate_values) < 3
            or not (best_expected <= 0.35 or best_expected >= 0.75)
        ):
            return False

        alternatives = [
            value for candidate, value in candidate_values.items() if candidate != move
        ]
        if not alternatives:
            return False

        closest_alternative = max(alternatives)
        return (
            best_expected - closest_alternative
            >= cls.INACCURACY_MAX_LOSS + cls.EXPECTED_POINTS_TOLERANCE
        )

    @classmethod
    def _is_missed_opportunity(
        cls,
        previous_opponent_loss: float | None,
        best_expected: float,
        actual_expected: float,
        expected_loss: float,
    ) -> bool:
        return (
            previous_opponent_loss is not None
            and previous_opponent_loss
            >= cls.INACCURACY_MAX_LOSS + cls.EXPECTED_POINTS_TOLERANCE
            and best_expected >= 0.75
            and expected_loss >= cls.INACCURACY_MAX_LOSS
            and actual_expected <= best_expected - cls.INACCURACY_MAX_LOSS
        )

    @classmethod
    def _is_material_sacrifice(
        cls,
        board: chess.Board,
        move: chess.Move,
        board_after_move: chess.Board,
        actual_info: chess.engine.InfoDict,
    ) -> bool:
        moved_piece = board.piece_at(move.from_square)
        if moved_piece is None or moved_piece.piece_type < chess.KNIGHT:
            return False
        pv = actual_info.get("pv")
        if not isinstance(pv, list) or not pv:
            return False

        tracked_square = move.to_square
        tracked_piece_captured = False
        variation = board_after_move.copy()
        for response in pv[:8]:
            if not variation.is_legal(response):
                break
            moving_piece = variation.piece_at(response.from_square)
            captured_piece = variation.piece_at(response.to_square)
            if (
                moving_piece is not None
                and moving_piece.color != moved_piece.color
                and response.to_square == tracked_square
                and captured_piece is not None
            ):
                tracked_piece_captured = True
            if (
                moving_piece is not None
                and moving_piece.color == moved_piece.color
                and response.from_square == tracked_square
            ):
                tracked_square = response.to_square
            variation.push(response)

        if not tracked_piece_captured:
            return False
        material_change = (
            cls._material_balance(variation, moved_piece.color)
            - cls._material_balance(board, moved_piece.color)
        )
        return material_change <= -1.5

    @classmethod
    def _material_balance(
        cls,
        board: chess.Board,
        color: chess.Color,
    ) -> float:
        balance = 0.0
        for piece in board.piece_map().values():
            value = cls.MATERIAL_VALUES[piece.piece_type]
            balance += value if piece.color == color else -value
        return balance

    @classmethod
    def _has_sufficient_depth(cls, info: chess.engine.InfoDict) -> bool:
        depth = info.get("depth")
        return isinstance(depth, int) and depth >= cls.BRILLIANT_MIN_DEPTH
