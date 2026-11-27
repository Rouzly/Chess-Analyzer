from io import StringIO
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.models.move_analysis import (
    GameAnalysisResult,
    MoveCategory,
    MoveClassification,
)
from app.ui.pages import AnalysisPage


PGN_TEXT = """\
[Event "Analysis Test"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 e5 2. Nf3 *
"""


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def load_test_game() -> chess.pgn.Game:
    game = chess.pgn.read_game(StringIO(PGN_TEXT))
    assert game is not None
    return game


class FakeAnalysisWorker(QObject):
    finished_analysis = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        board: chess.Board,
        executable_path: str | Path,
        time_limit: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.board = board.copy()
        self.executable_path = executable_path
        self.time_limit = time_limit
        self.running = False

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def wait(self) -> bool:
        self.running = False
        return True

    def complete_with_result(self, result: chess.engine.InfoDict) -> None:
        self.finished_analysis.emit(result)
        self.running = False
        self.finished.emit()

    def complete_with_error(self, message: str) -> None:
        self.error.emit(message)
        self.running = False
        self.finished.emit()


class FakeGameAnalysisWorker(QObject):
    progress = Signal(int, int)
    finished_analysis = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        game: chess.pgn.Game,
        executable_path: str | Path,
        time_limit: float,
        white_elo: int,
        black_elo: int,
        opening_book_path: str | Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.executable_path = executable_path
        self.time_limit = time_limit
        self.white_elo = white_elo
        self.black_elo = black_elo
        self.opening_book_path = opening_book_path
        self.running = False

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def wait(self) -> bool:
        self.running = False
        return True

    def complete_with_result(self, result: GameAnalysisResult) -> None:
        self.finished_analysis.emit(result)
        self.running = False
        self.finished.emit()

    def complete_with_error(self, message: str) -> None:
        self.error.emit(message)
        self.running = False
        self.finished.emit()


@pytest.fixture
def analysis_page(qapp: QApplication):
    page = AnalysisPage()
    page.display_game(load_test_game())
    yield page
    page.stop_analysis()
    page.close()
    page.deleteLater()


def test_selecting_a_piece_does_not_start_stockfish_analysis(
    analysis_page: AnalysisPage,
) -> None:
    status_before_selection = analysis_page.stockfish_status.text()
    analysis_page.chess_board._on_square_clicked(chess.E2)

    assert analysis_page._analysis_worker is None
    assert analysis_page.analyze_button.isEnabled()
    assert analysis_page.stockfish_status.text() == status_before_selection


def test_analysis_uses_current_position_and_displays_san_result(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    analysis_page.chess_board.go_forward()
    workers: list[FakeAnalysisWorker] = []

    def make_worker(board, executable_path, time_limit, parent=None):
        worker = FakeAnalysisWorker(board, executable_path, time_limit, parent)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)

    analysis_page.analyze_button.click()

    assert len(workers) == 1
    worker = workers[0]
    assert worker.board.fen() == analysis_page.chess_board.board.fen()
    assert worker.board is not analysis_page.chess_board.board
    assert worker.time_limit == 1.0
    assert not analysis_page.analyze_button.isEnabled()

    result = {
        "score": chess.engine.PovScore(chess.engine.Cp(29), chess.WHITE),
        "pv": [chess.Move.from_uci("e7e5"), chess.Move.from_uci("g1f3")],
        "depth": 12,
    }
    worker.complete_with_result(result)

    assert analysis_page.stockfish_evaluation.text() == (
        "Оценка (ход чёрных): -0.29"
    )
    assert analysis_page.stockfish_best_move.text() == "Лучший ход: e5"
    assert analysis_page.stockfish_pv.text() == "Основной вариант (SAN): e5 Nf3"
    assert analysis_page.stockfish_depth.text() == "Глубина: 12"
    assert analysis_page.stockfish_status.text() == "Анализ завершён."
    assert analysis_page.analyze_button.isEnabled()


def test_evaluation_perspective_matches_side_to_move_and_history(
    analysis_page: AnalysisPage,
) -> None:
    score = chess.engine.PovScore(chess.engine.Cp(75), chess.WHITE)
    analysis_page._analysis_board = analysis_page.chess_board.board.copy()
    analysis_page._show_stockfish_result({"score": score})

    assert analysis_page.stockfish_evaluation.text() == (
        "Оценка (ход белых): +0.75"
    )

    analysis_page.chess_board.go_forward()
    assert analysis_page.stockfish_evaluation.text() == "Оценка (ход чёрных): —"
    analysis_page._analysis_board = analysis_page.chess_board.board.copy()
    analysis_page._show_stockfish_result({"score": score})
    assert analysis_page.stockfish_evaluation.text() == (
        "Оценка (ход чёрных): -0.75"
    )

    analysis_page.chess_board.go_back()
    assert analysis_page.stockfish_evaluation.text() == "Оценка (ход белых): —"


def test_analysis_is_not_started_before_a_game_is_loaded(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = AnalysisPage()
    monkeypatch.setattr(
        "app.ui.pages.StockfishAnalysisWorker",
        lambda *args, **kwargs: pytest.fail("worker should not be created"),
    )

    page.analyze_button.click()

    assert "Сначала загрузите партию" in page.stockfish_status.text()
    assert page.analyze_button.isEnabled()
    page.close()


def test_missing_stockfish_reports_expected_path(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path = Path("missing") / "stockfish.exe"
    analysis_page.stockfish_path = missing_path
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    analysis_page.analyze_button.click()

    assert "Stockfish не найден" in analysis_page.stockfish_status.text()
    assert str(missing_path) in analysis_page.stockfish_status.text()
    assert analysis_page.analyze_button.isEnabled()


def test_stale_analysis_result_is_discarded_after_position_changes(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    workers: list[FakeAnalysisWorker] = []

    def make_worker(board, executable_path, time_limit, parent=None):
        worker = FakeAnalysisWorker(board, executable_path, time_limit, parent)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)

    analysis_page.analyze_button.click()
    worker = workers[0]
    analysis_page.chess_board.go_forward()
    worker.complete_with_result(
        {
            "score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE),
            "pv": [chess.Move.from_uci("e2e4")],
            "depth": 10,
        }
    )

    assert "Результат не показан" in analysis_page.stockfish_status.text()
    assert analysis_page.stockfish_evaluation.text() == "Оценка (ход чёрных): —"
    assert analysis_page.analyze_button.isEnabled()


def test_switching_variation_discards_previous_analysis_result(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    board_widget = analysis_page.chess_board
    board_widget.go_to_position(1)
    board_widget._on_square_clicked(chess.C7)
    board_widget._on_square_clicked(chess.C5)

    workers: list[FakeAnalysisWorker] = []

    def make_worker(board, executable_path, time_limit, parent=None):
        worker = FakeAnalysisWorker(board, executable_path, time_limit, parent)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)
    analysis_page.analyze_button.click()

    assert workers[0].board.fen() == board_widget.board.fen()
    board_widget.return_to_mainline()
    workers[0].complete_with_result(
        {
            "score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE),
            "pv": [chess.Move.from_uci("g1f3")],
            "depth": 10,
        }
    )

    assert "Результат не показан" in analysis_page.stockfish_status.text()
    assert analysis_page.stockfish_evaluation.text().endswith("—")


def test_missing_analysis_fields_are_displayed_without_crashing(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def make_worker(board, executable_path, time_limit, parent=None):
        return FakeAnalysisWorker(board, executable_path, time_limit, parent)

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)
    analysis_page.analyze_button.click()
    worker = analysis_page._analysis_worker
    assert isinstance(worker, FakeAnalysisWorker)
    worker.complete_with_result({})

    assert analysis_page.stockfish_evaluation.text().endswith("Нет данных")
    assert analysis_page.stockfish_best_move.text() == "Лучший ход: Нет данных"
    assert analysis_page.stockfish_pv.text() == "Основной вариант (SAN): Нет данных"
    assert analysis_page.stockfish_depth.text() == "Глубина: Нет данных"


def test_mate_score_is_displayed_from_white_perspective(
    analysis_page: AnalysisPage,
) -> None:
    analysis_page._analysis_board = analysis_page.chess_board.board.copy()
    result = {
        "score": chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE),
        "pv": [],
        "depth": 18,
    }

    analysis_page._show_stockfish_result(result)

    assert analysis_page.stockfish_evaluation.text() == (
        "Оценка (ход белых): Мат #+3"
    )


def test_mate_score_is_inverted_for_black_to_move(
    analysis_page: AnalysisPage,
) -> None:
    analysis_page.chess_board.go_forward()
    analysis_page._analysis_board = analysis_page.chess_board.board.copy()
    result = {
        "score": chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE),
        "pv": [],
        "depth": 18,
    }

    analysis_page._show_stockfish_result(result)

    assert analysis_page.stockfish_evaluation.text() == (
        "Оценка (ход чёрных): Мат #-3"
    )


def test_worker_error_is_shown_and_button_is_restored(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def make_worker(board, executable_path, time_limit, parent=None):
        return FakeAnalysisWorker(board, executable_path, time_limit, parent)

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)
    analysis_page.analyze_button.click()
    worker = analysis_page._analysis_worker
    assert isinstance(worker, FakeAnalysisWorker)

    worker.complete_with_error("движок не запустился")

    assert analysis_page.stockfish_status.text() == (
        "Ошибка анализа: движок не запустился"
    )
    assert analysis_page.analyze_button.isEnabled()


def test_repeated_analysis_click_does_not_start_a_second_worker(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    workers: list[FakeAnalysisWorker] = []

    def make_worker(board, executable_path, time_limit, parent=None):
        worker = FakeAnalysisWorker(board, executable_path, time_limit, parent)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.StockfishAnalysisWorker", make_worker)

    analysis_page.analyze_button.click()
    analysis_page._analyze_position()

    assert len(workers) == 1
    assert not analysis_page.analyze_button.isEnabled()


def test_full_game_analysis_classifies_moves_and_updates_selected_move(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: path.name == "fake-stockfish.exe",
    )
    workers: list[FakeGameAnalysisWorker] = []

    def make_worker(*args, **kwargs):
        worker = FakeGameAnalysisWorker(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.GameAnalysisWorker", make_worker)
    analysis_page.analyze_game_button.click()

    assert len(workers) == 1
    worker = workers[0]
    assert worker.time_limit == analysis_page.GAME_ANALYSIS_TIME_LIMIT
    assert worker.white_elo == 1200
    assert worker.black_elo == 1200
    assert not analysis_page.analyze_game_button.isEnabled()

    analysis_page.chess_board.go_forward()
    result = GameAnalysisResult(
        white_elo=1200,
        black_elo=1200,
        classifications=(
            MoveClassification(
                move_path=("e2e4",),
                san="e4",
                category=MoveCategory.EXCELLENT,
                expected_points_loss=0.01,
            ),
        ),
        opening_book_warning=(
            "Не удалось открыть или проверить Polyglot-базу: file missing. "
            "Анализ продолжен без дебютной базы."
        ),
    )
    worker.complete_with_result(result)

    assert analysis_page.game_analysis_result == result
    assert "[Отличный]" in analysis_page.chess_board.history_text.toHtml()
    assert analysis_page.selected_move_classification.text() == (
        "Классификация хода: Отличный"
    )
    assert "Классифицировано ходов: 1." in (
        analysis_page.game_analysis_status.text()
    )
    assert "Анализ продолжен без дебютной базы" in (
        analysis_page.game_analysis_status.text()
    )
    assert analysis_page.analyze_game_button.isEnabled()


def test_full_game_analysis_discards_results_for_previous_game(
    analysis_page: AnalysisPage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_page.stockfish_path = Path("fake-stockfish.exe")
    monkeypatch.setattr(Path, "is_file", lambda path: path.name == "fake-stockfish.exe")
    workers: list[FakeGameAnalysisWorker] = []

    def make_worker(*args, **kwargs):
        worker = FakeGameAnalysisWorker(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr("app.ui.pages.GameAnalysisWorker", make_worker)
    analysis_page.analyze_game_button.click()
    analysis_page.display_game(
        chess.pgn.read_game(StringIO("1. d4 d5 *"))
    )
    stale_result = GameAnalysisResult(
        white_elo=1200,
        black_elo=1200,
        classifications=(
            MoveClassification(
                move_path=("e2e4",),
                san="e4",
                category=MoveCategory.BLUNDER,
                expected_points_loss=0.5,
            ),
        ),
    )
    workers[0].complete_with_result(stale_result)

    assert analysis_page.game_analysis_result is None
    assert not analysis_page.chess_board.move_classifications
    assert "Запустите анализ" in analysis_page.game_analysis_status.text()
