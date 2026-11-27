from io import StringIO
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import pytest

import app.services.move_classifier as move_classifier_module
from app.models.move_analysis import MoveCategory
from app.services.move_classifier import (
    GameMoveClassifier,
    MoveClassificationError,
)


def load_game(pgn_text: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(StringIO(pgn_text))
    assert game is not None
    return game


class FakeEngine:
    def __init__(self, missing_score: bool = False) -> None:
        self.missing_score = missing_score

    def analyze_variations(
        self,
        board: chess.Board,
        time_limit: float,
        count: int,
    ) -> list[chess.engine.InfoDict]:
        legal_moves = list(board.legal_moves)
        if self.missing_score:
            return [{"pv": legal_moves[:1]}]
        return [
            {
                "score": chess.engine.PovScore(
                    chess.engine.Cp(score),
                    board.turn,
                ),
                "pv": [move],
            }
            for move, score in zip(legal_moves[:2], (100, 95))
        ]

    def analyze(
        self,
        board: chess.Board,
        time_limit: float,
    ) -> chess.engine.InfoDict:
        mover = not board.turn
        score = None if self.missing_score else chess.engine.PovScore(
            chess.engine.Cp(100),
            mover,
        )
        return {"score": score, "pv": []}


class LosingMateEngine(FakeEngine):
    def analyze(
        self,
        board: chess.Board,
        time_limit: float,
    ) -> chess.engine.InfoDict:
        if board.is_checkmate():
            return {
                "score": chess.engine.PovScore(
                    chess.engine.Cp(-1000),
                    not board.turn,
                ),
                "pv": [],
            }
        return super().analyze(board, time_limit)


def test_classifies_each_move_across_mainline_and_variations() -> None:
    game = load_game("1. e4 (1. d4 d5) e5 *")
    progress: list[tuple[int, int]] = []
    classifier = GameMoveClassifier(FakeEngine(), time_limit=0.1)

    result = classifier.classify(
        game,
        white_elo=1800,
        black_elo=1600,
        progress_callback=lambda completed, total: progress.append(
            (completed, total)
        ),
    )

    assert len(result.classifications) == 4
    assert result.white_elo == 1800
    assert result.black_elo == 1600
    assert all(
        classification.category == MoveCategory.BEST
        for classification in result.classifications
    )
    assert progress[-1] == (4, 4)
    assert {classification.move_path for classification in result.classifications} == {
        ("e2e4",),
        ("e2e4", "e7e5"),
        ("d2d4",),
        ("d2d4", "d7d5"),
    }


def test_control_game_checkmate_is_best_without_changing_other_move_categories() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "chesscom_control_game.pgn"
    )
    with fixture_path.open(encoding="utf-8") as pgn_file:
        game = chess.pgn.read_game(pgn_file)
    assert game is not None

    baseline = GameMoveClassifier(FakeEngine(), time_limit=0.1).classify(game)
    with_losing_mate_score = GameMoveClassifier(
        LosingMateEngine(),
        time_limit=0.1,
    ).classify(game)
    checkmating_move = next(
        item for item in with_losing_mate_score.classifications if item.san == "Rh1#"
    )
    baseline_by_path = {
        item.move_path: item for item in baseline.classifications
    }

    assert checkmating_move.category is MoveCategory.BEST
    assert all(
        item.category is baseline_by_path[item.move_path].category
        and item.expected_points_loss
        == baseline_by_path[item.move_path].expected_points_loss
        for item in with_losing_mate_score.classifications
        if item.san != "Rh1#"
    )


def test_missing_engine_score_fails_without_fabricated_classifications() -> None:
    game = load_game("1. e4 *")
    classifier = GameMoveClassifier(FakeEngine(missing_score=True))

    with pytest.raises(MoveClassificationError, match="не вернул оценку"):
        classifier.classify(game)


def test_expected_points_use_rating_and_mate_scores_are_supported() -> None:
    score = chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE)
    white_expected = GameMoveClassifier._expected_points(
        {"score": score},
        chess.WHITE,
        1200,
        1200,
        24,
    )
    black_expected = GameMoveClassifier._expected_points(
        {"score": score},
        chess.BLACK,
        1200,
        1200,
        24,
    )
    higher_rated_expected = GameMoveClassifier._expected_points(
        {"score": score},
        chess.WHITE,
        1800,
        1200,
        24,
    )
    winning_mate = GameMoveClassifier._expected_points(
        {"score": chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)},
        chess.WHITE,
        1200,
        1200,
        24,
    )
    losing_mate = GameMoveClassifier._expected_points(
        {"score": chess.engine.PovScore(chess.engine.Mate(-3), chess.WHITE)},
        chess.WHITE,
        1200,
        1200,
        24,
    )

    assert white_expected == pytest.approx(1.0 - black_expected, abs=0.01)
    assert higher_rated_expected > white_expected
    assert winning_mate > 0.99
    assert losing_mate < 0.01


def test_centipawn_curve_remains_continuous_in_decisive_positions() -> None:
    almost_lost = GameMoveClassifier._expected_points(
        {"score": chess.engine.PovScore(chess.engine.Cp(-487), chess.WHITE)},
        chess.WHITE,
        536,
        564,
        24,
    )
    worse_position = GameMoveClassifier._expected_points(
        {"score": chess.engine.PovScore(chess.engine.Cp(-584), chess.WHITE)},
        chess.WHITE,
        536,
        564,
        24,
    )

    assert 0.0 < worse_position < almost_lost < 0.5
    assert almost_lost - worse_position > 0.02


def test_classifier_uses_elo_headers_when_ratings_are_not_passed() -> None:
    game = load_game('[WhiteElo "536"]\n[BlackElo "564"]\n\n1. e4 *')

    result = GameMoveClassifier(FakeEngine(), time_limit=0.1).classify(game)

    assert result.white_elo == 536
    assert result.black_elo == 564


def test_engine_wdl_and_rating_adjustment_are_used_in_the_requested_pov() -> None:
    wdl = chess.engine.PovWdl(
        chess.engine.Wdl(wins=500, draws=400, losses=100),
        chess.WHITE,
    )
    white_expected = GameMoveClassifier._expected_points(
        {"wdl": wdl},
        chess.WHITE,
        1200,
        1200,
        10,
    )
    black_expected = GameMoveClassifier._expected_points(
        {"wdl": wdl},
        chess.BLACK,
        1200,
        1200,
        10,
    )
    rated_white_expected = GameMoveClassifier._expected_points(
        {"wdl": wdl},
        chess.WHITE,
        1600,
        1200,
        10,
    )

    assert white_expected == pytest.approx(0.7)
    assert black_expected == pytest.approx(0.3)
    assert rated_white_expected > white_expected


def test_expected_points_rejects_missing_or_invalid_engine_information() -> None:
    with pytest.raises(MoveClassificationError, match="не вернул оценку или WDL"):
        GameMoveClassifier._expected_points({}, chess.WHITE, 1200, 1200, 0)
    with pytest.raises(MoveClassificationError, match="некорректное распределение WDL"):
        GameMoveClassifier._expected_points(
            {"wdl": chess.engine.PovWdl(chess.engine.Wdl(-1, 1001, 0), chess.WHITE)},
            chess.WHITE,
            1200,
            1200,
            0,
        )


@pytest.mark.parametrize(
    ("loss", "category"),
    [
        (0.0, MoveCategory.BEST),
        (0.005, MoveCategory.BEST),
        (0.006, MoveCategory.EXCELLENT),
        (0.02, MoveCategory.EXCELLENT),
        (0.025, MoveCategory.EXCELLENT),
        (0.026, MoveCategory.GOOD),
        (0.05, MoveCategory.GOOD),
        (0.055, MoveCategory.GOOD),
        (0.056, MoveCategory.INACCURACY),
        (0.10, MoveCategory.INACCURACY),
        (0.105, MoveCategory.INACCURACY),
        (0.106, MoveCategory.MISTAKE),
        (0.20, MoveCategory.MISTAKE),
        (0.205, MoveCategory.MISTAKE),
        (0.206, MoveCategory.BLUNDER),
        (1.0, MoveCategory.BLUNDER),
    ],
)
def test_expected_points_loss_boundaries(
    loss: float,
    category: MoveCategory,
) -> None:
    assert GameMoveClassifier._quality_category(loss) is category


def test_great_requires_a_unique_critical_move_not_only_a_multipv_gap() -> None:
    moves = [
        chess.Move.from_uci(uci)
        for uci in ("e2e4", "d2d4", "g1f3", "c2c4")
    ]

    assert not GameMoveClassifier._is_great_move(
        moves[0],
        best_expected=0.50,
        expected_loss=0.0,
        candidate_values={
            moves[0]: 0.50,
            moves[1]: 0.30,
            moves[2]: 0.20,
            moves[3]: 0.10,
        },
    )
    assert not GameMoveClassifier._is_great_move(
        moves[0],
        best_expected=0.20,
        expected_loss=0.0,
        candidate_values={
            moves[0]: 0.20,
            moves[1]: 0.195,
            moves[2]: 0.05,
            moves[3]: 0.02,
        },
    )
    assert not GameMoveClassifier._is_great_move(
        moves[0],
        best_expected=0.90,
        expected_loss=0.0,
        candidate_values={
            moves[0]: 0.90,
            moves[1]: 0.82,
            moves[2]: 0.41,
            moves[3]: 0.26,
        },
    )
    assert GameMoveClassifier._is_great_move(
        moves[0],
        best_expected=0.20,
        expected_loss=0.0,
        candidate_values={
            moves[0]: 0.20,
            moves[1]: 0.05,
            moves[2]: 0.03,
            moves[3]: 0.01,
        },
    )


def test_miss_requires_an_opponent_error_and_a_lost_winning_reply() -> None:
    is_miss = GameMoveClassifier._is_missed_opportunity

    assert not is_miss(None, 0.90, 0.70, 0.20)
    assert not is_miss(0.08, 0.90, 0.70, 0.20)
    assert not is_miss(0.15, 0.70, 0.50, 0.20)
    assert not is_miss(0.15, 0.90, 0.82, 0.08)
    assert is_miss(0.15, 0.90, 0.70, 0.20)


def test_material_sacrifice_requires_a_real_net_loss_not_an_exchange() -> None:
    classifier = GameMoveClassifier(FakeEngine())

    losing_sacrifice_board = chess.Board(
        "4k3/5p2/8/6N1/8/8/8/K7 w - - 0 1"
    )
    losing_sacrifice = losing_sacrifice_board.parse_san("Nxf7")
    losing_after = losing_sacrifice_board.copy()
    losing_after.push(losing_sacrifice)
    losing_line = [losing_after.parse_san("Kxf7")]
    assert classifier._is_material_sacrifice(
        losing_sacrifice_board,
        losing_sacrifice,
        losing_after,
        {"pv": losing_line},
    )

    exchange_board = chess.Board(
        "7k/5n2/8/4p3/2N5/8/1B6/K7 w - - 0 1"
    )
    exchange_move = exchange_board.parse_san("Nxe5")
    exchange_after = exchange_board.copy()
    exchange_after.push(exchange_move)
    exchange_line = [
        exchange_after.parse_san("Nxe5"),
    ]
    exchange_after.push(exchange_line[0])
    exchange_line.append(exchange_after.parse_san("Bxe5"))
    exchange_position = exchange_board.copy()
    exchange_position.push(exchange_move)
    assert not classifier._is_material_sacrifice(
        exchange_board,
        exchange_move,
        exchange_position,
        {"pv": exchange_line},
    )


def test_brilliant_requires_a_best_quality_sacrifice_with_engine_depth() -> None:
    classifier = GameMoveClassifier(FakeEngine())
    board = chess.Board("4k3/5p2/8/6N1/8/8/8/K7 w - - 0 1")
    move = board.parse_san("Nxf7")
    board_after = board.copy()
    board_after.push(move)
    actual_info = {
        "depth": 14,
        "pv": [board_after.parse_san("Kxf7")],
        "score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE),
    }
    candidate_info = {
        "depth": 14,
        "pv": [move],
        "score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE),
    }

    category = classifier._classify_category(
        board=board,
        move=move,
        board_after_move=board_after,
        actual_info=actual_info,
        actual_expected=0.50,
        expected_loss=0.005,
        best_expected=0.505,
        candidate_values={move: 0.505},
        candidate_infos={move: candidate_info},
        previous_opponent_loss=None,
        book_reader=None,
    )
    losing_category = classifier._classify_category(
        board=board,
        move=move,
        board_after_move=board_after,
        actual_info=actual_info,
        actual_expected=0.20,
        expected_loss=0.30,
        best_expected=0.50,
        candidate_values={move: 0.50},
        candidate_infos={move: candidate_info},
        previous_opponent_loss=None,
        book_reader=None,
    )

    assert category is MoveCategory.BRILLIANT
    assert losing_category is MoveCategory.BLUNDER


def test_brilliant_is_rejected_when_root_score_shows_a_poor_sacrifice() -> None:
    classifier = GameMoveClassifier(FakeEngine())
    board = chess.Board("4k3/5p2/8/6N1/8/8/8/K7 w - - 0 1")
    move = board.parse_san("Nxf7")
    alternative = board.parse_san("Nh3")
    board_after = board.copy()
    board_after.push(move)
    candidate_infos = {
        move: {
            "depth": 14,
            "pv": [move],
            "score": chess.engine.PovScore(chess.engine.Cp(-500), chess.WHITE),
        },
        alternative: {
            "depth": 14,
            "pv": [alternative],
            "score": chess.engine.PovScore(chess.engine.Cp(-400), chess.WHITE),
        },
    }

    category = classifier._classify_category(
        board=board,
        move=move,
        board_after_move=board_after,
        actual_info={
            "depth": 14,
            "pv": [board_after.parse_san("Kxf7")],
            "score": chess.engine.PovScore(chess.engine.Cp(-500), chess.WHITE),
        },
        actual_expected=0.50,
        expected_loss=0.005,
        best_expected=0.505,
        candidate_values={move: 0.505, alternative: 0.505},
        candidate_infos=candidate_infos,
        previous_opponent_loss=None,
        book_reader=None,
    )

    assert category is not MoveCategory.BRILLIANT


def test_gm2001_classifies_known_opening_moves_and_variations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "opening_book"
        / "gm2001.bin"
    )
    assert book_path.is_file()
    game = load_game("1. e4 (1. d4 d5) e5 2. Nf3 Nc6 3. Bb5 *")
    readers = []
    open_reader = chess.polyglot.open_reader

    def track_reader(path):
        reader = open_reader(path)
        readers.append(reader)
        return reader

    monkeypatch.setattr(
        move_classifier_module.chess.polyglot,
        "open_reader",
        track_reader,
    )
    result = GameMoveClassifier(
        FakeEngine(),
        time_limit=0.1,
        opening_book_path=book_path,
    ).classify(game)

    by_path = {
        classification.move_path: classification
        for classification in result.classifications
    }
    assert by_path[("e2e4",)].category is MoveCategory.BOOK
    assert by_path[("e2e4", "e7e5")].category is MoveCategory.BOOK
    assert by_path[("e2e4", "e7e5", "g1f3")].category is MoveCategory.BOOK
    assert by_path[("d2d4",)].category is MoveCategory.BOOK
    assert by_path[("d2d4", "d7d5")].category is MoveCategory.BOOK
    assert result.opening_book_warning is None
    assert len(readers) == 1
    assert readers[0].mmap.closed


def test_move_not_in_gm2001_falls_back_to_stockfish_category() -> None:
    book_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "opening_book"
        / "gm2001.bin"
    )
    game = load_game("1. e4 a5 *")

    result = GameMoveClassifier(
        FakeEngine(),
        time_limit=0.1,
        opening_book_path=book_path,
    ).classify(game)

    a5 = next(item for item in result.classifications if item.san == "a5")
    assert a5.category is not MoveCategory.BOOK
    assert result.opening_book_warning is None


@pytest.mark.parametrize(
    "book_state",
    ["missing", "corrupt", "malformed-record"],
)
def test_missing_or_corrupt_book_warns_and_continues_analysis(
    tmp_path: Path,
    book_state: str,
) -> None:
    book_path = tmp_path / "opening.bin"
    if book_state == "corrupt":
        book_path.write_bytes(b"not-a-polyglot-book")
    elif book_state == "malformed-record":
        book_path.write_bytes(bytes(16))

    result = GameMoveClassifier(
        FakeEngine(),
        time_limit=0.1,
        opening_book_path=book_path,
    ).classify(load_game("1. e4 *"))

    assert result.opening_book_warning is not None
    assert "Анализ продолжен без дебютной базы" in result.opening_book_warning
    assert result.classifications
    assert result.classifications[0].category is not MoveCategory.BOOK
