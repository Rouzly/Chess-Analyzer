from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import chess
import chess.engine
import chess.pgn
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.database.game_repository import GameRepository
from app.models.game_record import parse_elo
from app.models.move_analysis import GameAnalysisResult
from app.services.pgn_service import load_first_game
from app.workers.game_analysis_worker import GameAnalysisWorker
from app.ui.chess_board import ChessBoardWidget
from app.ui.move_category_labels import move_category_label
from app.ui.my_games_page import GameCardWidget, MyGamesPage
from app.ui.theme_manager import ThemeManager, ThemePalette
from app.workers.stockfish_analysis_worker import StockfishAnalysisWorker


class PlaceholderPage(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("placeholderPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        layout.addStretch()


class ThemeSettingsPage(QWidget):
    def __init__(
        self,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._theme_manager = theme_manager
        self.theme_cards: dict[str, ThemeOptionCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        section_title = QLabel("Цветовая тема")
        section_title.setObjectName("settingsSectionTitle")
        layout.addWidget(section_title)

        description = QLabel("Выберите оформление приложения.")
        description.setObjectName("themeDescription")
        layout.addWidget(description)

        for theme_id, palette in theme_manager.available_themes.items():
            card = ThemeOptionCard(theme_id, palette)
            card.clicked.connect(theme_manager.set_theme)
            self.theme_cards[theme_id] = card
            layout.addWidget(card)

        layout.addStretch()
        theme_manager.theme_changed.connect(self._sync_selected_theme)
        self._sync_selected_theme(theme_manager.current_theme)

    def _sync_selected_theme(self, theme_id: str) -> None:
        for card_id, card in self.theme_cards.items():
            card.set_selected(card_id == theme_id)


class ThemeOptionCard(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        theme_id: str,
        palette: ThemePalette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.theme_id = theme_id
        self.setObjectName("themeCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        preview = QFrame()
        preview.setObjectName("themePreview")
        preview.setFixedSize(92, 48)
        preview.setStyleSheet(
            f"background-color: {palette.preview[0]};"
            f"border: 1px solid {palette.border}; border-radius: 6px;"
        )
        preview_layout = QHBoxLayout(preview)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)
        for color in palette.preview[1:]:
            swatch = QFrame()
            swatch.setStyleSheet(
                f"background-color: {color}; border-radius: 3px;"
            )
            preview_layout.addWidget(swatch)
        layout.addWidget(preview)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        name = QLabel(palette.name)
        name.setObjectName("themeName")
        details = QLabel(palette.description)
        details.setObjectName("themeDescription")
        details.setWordWrap(True)
        text_layout.addWidget(name)
        text_layout.addWidget(details)
        layout.addLayout(text_layout, 1)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.theme_id)
        super().mousePressEvent(event)


class AnalysisPage(QWidget):
    open_games_requested = Signal()
    ANALYSIS_TIME_LIMIT = 1.0
    GAME_ANALYSIS_TIME_LIMIT = 0.2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisPage")
        self.stockfish_path = (
            Path(__file__).resolve().parents[2] / "engines" / "stockfish.exe"
        )
        self._analysis_worker: StockfishAnalysisWorker | None = None
        self._analysis_board: chess.Board | None = None
        self._analysis_position_key: tuple[
            int, str, int, tuple[str, ...]
        ] | None = None
        self._game_analysis_workers: list[GameAnalysisWorker] = []
        self._active_game_analysis_worker: GameAnalysisWorker | None = None
        self._game_revision = 0
        self._game_analysis_id = 0
        self.game_analysis_result: GameAnalysisResult | None = None
        self.opening_book_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "opening_book"
            / "gm2001.bin"
        )
        self._position_revision = 0
        self._has_loaded_game = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("analysisScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        content = QWidget()
        content.setObjectName("analysisContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        scroll_area.setWidget(content)
        root_layout.addWidget(scroll_area)
        self._analysis_content_layout = None

        title_label = QLabel("Анализ")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        title_label.setObjectName("pageTitle")

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(title_label)
        top_layout.addStretch()

        self.my_games_button = QPushButton("Мои партии")
        self.my_games_button.setObjectName("historyButton")
        self.my_games_button.clicked.connect(self.open_games_requested.emit)
        top_layout.addWidget(self.my_games_button)

        load_button = QPushButton("Загрузить PGN")
        load_button.setObjectName("historyButton")
        load_button.clicked.connect(self._load_pgn)
        top_layout.addWidget(load_button)

        self.analyze_game_button = QPushButton("Анализировать партию")
        self.analyze_game_button.setObjectName("historyButton")
        self.analyze_game_button.clicked.connect(self._analyze_game)
        top_layout.addWidget(self.analyze_game_button)

        self.info_label = QLabel(
            "Белые: Неизвестно\n"
            "Чёрные: Неизвестно\n"
            "Результат: Неизвестно\n"
            "Дата: Неизвестно\n"
            "Турнир: Неизвестно"
        )
        self.info_label.setObjectName("gameInfo")
        self.info_label.setMargin(10)
        self.info_label.setWordWrap(True)

        self.chess_board = ChessBoardWidget()
        self.game_repository: GameRepository | None = None
        self.chess_board.position_changed.connect(self._on_position_changed)
        self.stockfish_panel = QFrame()
        self.stockfish_panel.setObjectName("stockfishPanel")
        self.stockfish_panel.setMinimumWidth(250)
        self.stockfish_panel.setMaximumWidth(340)

        stockfish_layout = QVBoxLayout(self.stockfish_panel)
        stockfish_layout.setContentsMargins(18, 16, 18, 16)
        stockfish_layout.setSpacing(12)

        stockfish_header = QHBoxLayout()
        stockfish_title = QLabel("Анализ Stockfish")
        stockfish_title.setObjectName("stockfishTitle")
        stockfish_header.addWidget(stockfish_title)
        stockfish_header.addStretch()

        self.analyze_button = QPushButton("Анализировать")
        self.analyze_button.setObjectName("historyButton")
        self.analyze_button.clicked.connect(self._analyze_position)
        stockfish_header.addWidget(self.analyze_button)

        self.stockfish_status = QLabel("Ожидает анализа.")
        self.stockfish_status.setObjectName("stockfishStatus")
        self.stockfish_status.setWordWrap(True)

        self.stockfish_evaluation = QLabel("Оценка (ход белых): —")
        self.stockfish_evaluation.setObjectName("stockfishEvaluation")
        self.stockfish_evaluation.setWordWrap(True)
        self.stockfish_best_move = QLabel("Лучший ход: —")
        self.stockfish_best_move.setObjectName("stockfishBestMove")
        self.stockfish_best_move.setWordWrap(True)
        self.stockfish_pv = QLabel("Основной вариант (SAN): —")
        self.stockfish_pv.setObjectName("stockfishResult")
        self.stockfish_pv.setWordWrap(True)
        self.stockfish_depth = QLabel("Глубина: —")
        self.stockfish_depth.setObjectName("stockfishResult")
        self.selected_move_classification = QLabel("Классификация хода: —")
        self.selected_move_classification.setObjectName(
            "selectedMoveClassification"
        )
        self.selected_move_classification.setWordWrap(True)
        self.game_analysis_status = QLabel(
            "Загрузите партию и запустите её анализ."
        )
        self.game_analysis_status.setObjectName("gameAnalysisStatus")
        self.game_analysis_status.setWordWrap(True)
        self.game_analysis_progress = QProgressBar()
        self.game_analysis_progress.setObjectName("gameAnalysisProgress")
        self.game_analysis_progress.setRange(0, 100)
        self.game_analysis_progress.setValue(0)
        self.game_analysis_progress.hide()

        stockfish_layout.addLayout(stockfish_header)
        stockfish_layout.addWidget(self.stockfish_status)
        stockfish_layout.addWidget(self.game_analysis_status)
        stockfish_layout.addWidget(self.game_analysis_progress)
        stockfish_layout.addWidget(self.selected_move_classification)
        stockfish_layout.addWidget(self.stockfish_evaluation)
        stockfish_layout.addWidget(self.stockfish_best_move)
        stockfish_layout.addWidget(self.stockfish_pv)
        stockfish_layout.addWidget(self.stockfish_depth)
        stockfish_layout.addStretch()

        layout.addLayout(top_layout)
        layout.addWidget(self.info_label)

        self._analysis_content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._analysis_content_layout.setContentsMargins(0, 0, 0, 0)
        self._analysis_content_layout.setSpacing(16)
        self._analysis_content_layout.addWidget(self.chess_board, 0)
        self._analysis_content_layout.addWidget(self.stockfish_panel, 1)
        layout.addLayout(self._analysis_content_layout)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._analysis_content_layout is None:
            return

        if self.width() < 900:
            direction = QBoxLayout.Direction.TopToBottom
        else:
            direction = QBoxLayout.Direction.LeftToRight
        if self._analysis_content_layout.direction() != direction:
            self._analysis_content_layout.setDirection(direction)

    def display_game(self, game: chess.pgn.Game) -> None:
        self._game_revision += 1
        self._game_analysis_id += 1
        self._active_game_analysis_worker = None
        self.analyze_game_button.setEnabled(True)
        self.game_analysis_result = None
        self.game_analysis_progress.hide()
        self.game_analysis_progress.setValue(0)
        self.game_analysis_status.setText(
            "Партия загружена. Запустите анализ, чтобы классифицировать ходы."
        )
        self.chess_board.set_move_classifications(())
        self._has_loaded_game = True
        self.chess_board.load_pgn_game(game)
        game_info = self.chess_board.get_game_info(game)
        self.info_label.setText(
            "\n".join(f"{name}: {value}" for name, value in game_info.items())
        )

    def _analyze_game(self) -> None:
        if not self._has_loaded_game or self.chess_board.game_tree is None:
            self.game_analysis_status.setText(
                "Сначала загрузите партию PGN для анализа."
            )
            return
        if not self.stockfish_path.is_file():
            self.game_analysis_status.setText(
                f"Stockfish не найден. Ожидаемый путь: {self.stockfish_path}"
            )
            return

        game = copy.deepcopy(self.chess_board.game_tree)
        white_elo = parse_elo(game.headers.get("WhiteElo"))
        black_elo = parse_elo(game.headers.get("BlackElo"))
        self._game_analysis_id += 1
        analysis_id = self._game_analysis_id
        game_revision = self._game_revision
        self.game_analysis_result = None
        self.chess_board.set_move_classifications(())
        self._update_selected_move_classification()
        self.game_analysis_status.setText("Анализируется вся партия...")
        self.game_analysis_progress.setRange(0, 0)
        self.game_analysis_progress.show()
        self.analyze_game_button.setEnabled(False)

        worker = GameAnalysisWorker(
            game,
            self.stockfish_path,
            self.GAME_ANALYSIS_TIME_LIMIT,
            white_elo,
            black_elo,
            opening_book_path=self.opening_book_path,
            parent=self,
        )
        worker.progress.connect(
            lambda completed, total, run_id=analysis_id, revision=game_revision:
                self._on_game_analysis_progress(
                    run_id, revision, completed, total
                )
        )
        worker.finished_analysis.connect(
            lambda result, run_id=analysis_id, revision=game_revision:
                self._on_game_analysis_finished(run_id, revision, result)
        )
        worker.error.connect(
            lambda message, run_id=analysis_id, revision=game_revision:
                self._on_game_analysis_error(run_id, revision, message)
        )
        worker.finished.connect(
            lambda worker=worker: self._on_game_analysis_worker_finished(worker)
        )
        worker.finished.connect(worker.deleteLater)
        self._game_analysis_workers.append(worker)
        self._active_game_analysis_worker = worker
        try:
            worker.start()
        except RuntimeError as error:
            self._game_analysis_workers.remove(worker)
            self._active_game_analysis_worker = None
            self.analyze_game_button.setEnabled(True)
            self.game_analysis_progress.hide()
            self.game_analysis_status.setText(
                f"Не удалось запустить анализ партии: {error}"
            )
            worker.deleteLater()

    def _on_game_analysis_progress(
        self,
        analysis_id: int,
        game_revision: int,
        completed: int,
        total: int,
    ) -> None:
        if (
            analysis_id != self._game_analysis_id
            or game_revision != self._game_revision
        ):
            return
        self.game_analysis_progress.setRange(0, max(total, 1))
        self.game_analysis_progress.setValue(completed)
        self.game_analysis_status.setText(
            f"Анализ ходов: {completed} из {total}."
        )

    def _on_game_analysis_finished(
        self,
        analysis_id: int,
        game_revision: int,
        result: GameAnalysisResult,
    ) -> None:
        if (
            analysis_id != self._game_analysis_id
            or game_revision != self._game_revision
        ):
            return
        self.game_analysis_result = result
        self.chess_board.set_move_classifications(result.classifications)
        total = len(result.classifications)
        self.game_analysis_progress.setRange(0, max(total, 1))
        self.game_analysis_progress.setValue(total)
        self.game_analysis_status.setText(
            f"Анализ завершён. Классифицировано ходов: {total}."
        )
        if result.opening_book_warning is not None:
            self.game_analysis_status.setText(
                f"Анализ завершён. Классифицировано ходов: {total}. "
                f"Предупреждение: {result.opening_book_warning}"
            )
        self._update_selected_move_classification()

    def _on_game_analysis_error(
        self,
        analysis_id: int,
        game_revision: int,
        message: str,
    ) -> None:
        if (
            analysis_id != self._game_analysis_id
            or game_revision != self._game_revision
        ):
            return
        self.game_analysis_result = None
        self.chess_board.set_move_classifications(())
        self.game_analysis_progress.hide()
        self.game_analysis_status.setText(f"Ошибка анализа партии: {message}")

    def _on_game_analysis_worker_finished(
        self,
        worker: GameAnalysisWorker,
    ) -> None:
        if worker in self._game_analysis_workers:
            self._game_analysis_workers.remove(worker)
        if self._active_game_analysis_worker is worker:
            self._active_game_analysis_worker = None
            self.analyze_game_button.setEnabled(True)

    def _update_selected_move_classification(self) -> None:
        position_index = self.chess_board.position_index
        if position_index == 0:
            self.selected_move_classification.setText("Классификация хода: —")
            return
        move_path = tuple(
            node.move.uci()
            for node in self.chess_board.active_line[:position_index]
        )
        classification = self.chess_board.move_classifications.get(move_path)
        if classification is None:
            text = "Классификация хода: ещё не рассчитана"
        else:
            text = (
                "Классификация хода: "
                f"{move_category_label(classification.category)}"
            )
        self.selected_move_classification.setText(text)

    def _analyze_position(self) -> None:
        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            return

        if not self._has_loaded_game:
            self.stockfish_status.setText(
                "Сначала загрузите партию PGN для анализа."
            )
            return

        if not self.stockfish_path.is_file():
            self.stockfish_status.setText(
                f"Stockfish не найден. Ожидаемый путь: {self.stockfish_path}"
            )
            return

        self._analysis_board = self.chess_board.board.copy()
        self._analysis_position_key = self._current_position_key()
        self._clear_stockfish_result()
        self.stockfish_status.setText("Выполняется анализ...")
        self.analyze_button.setEnabled(False)

        worker = StockfishAnalysisWorker(
            self._analysis_board,
            self.stockfish_path,
            self.ANALYSIS_TIME_LIMIT,
            parent=self,
        )
        worker.finished_analysis.connect(self._on_analysis_finished)
        worker.error.connect(self._on_analysis_error)
        worker.finished.connect(self._on_analysis_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._analysis_worker = worker

        try:
            worker.start()
        except RuntimeError as error:
            self._analysis_worker = None
            self.analyze_button.setEnabled(True)
            self.stockfish_status.setText(f"Не удалось запустить анализ: {error}")
            worker.deleteLater()

    def _on_analysis_finished(self, result: chess.engine.InfoDict) -> None:
        if self._analysis_position_key != self._current_position_key():
            self.stockfish_status.setText(
                "Позиция изменилась во время анализа. Результат не показан."
            )
            return

        self._show_stockfish_result(result)
        self.stockfish_status.setText("Анализ завершён.")

    def _on_analysis_error(self, message: str) -> None:
        if self._analysis_position_key != self._current_position_key():
            self.stockfish_status.setText(
                "Позиция изменилась во время анализа. Результат не показан."
            )
            return

        self.stockfish_status.setText(f"Ошибка анализа: {message}")

    def _on_analysis_worker_finished(self) -> None:
        self._analysis_worker = None
        self.analyze_button.setEnabled(True)

    def _on_position_changed(self) -> None:
        self._position_revision += 1
        self._clear_stockfish_result()
        self._update_selected_move_classification()

        if self._analysis_worker is not None and self._analysis_worker.isRunning():
            self.stockfish_status.setText(
                "Позиция изменилась. Результат текущего анализа будет отброшен."
            )
        else:
            self.stockfish_status.setText(
                "Позиция изменилась. Запустите анализ заново."
            )

    def _current_position_key(self) -> tuple[int, str, int, tuple[str, ...]]:
        return (
            self._position_revision,
            self.chess_board.start_board.fen(),
            self.chess_board.position_index,
            tuple(move.uci() for move in self.chess_board.board.move_stack),
        )

    def _clear_stockfish_result(self) -> None:
        side_to_move = "белых" if self.chess_board.board.turn == chess.WHITE else "чёрных"
        self.stockfish_evaluation.setText(
            f"Оценка (ход {side_to_move}): —"
        )
        self.stockfish_best_move.setText("Лучший ход: —")
        self.stockfish_pv.setText("Основной вариант (SAN): —")
        self.stockfish_depth.setText("Глубина: —")

    def _show_stockfish_result(self, result: chess.engine.InfoDict) -> None:
        score = result.get("score")
        evaluation = "Нет данных"
        analysis_board = self._analysis_board or self.chess_board.board.copy()
        side_to_move = (
            "белых" if analysis_board.turn == chess.WHITE else "чёрных"
        )
        if score is not None:
            try:
                side_score = score.pov(analysis_board.turn)
                centipawns = side_score.score()
                if centipawns is not None:
                    evaluation = f"{centipawns / 100:+.2f}"
                else:
                    mate_score = side_score.mate()
                    if mate_score is not None:
                        evaluation = f"Мат #{mate_score:+d}"
            except (AttributeError, TypeError, ValueError):
                evaluation = "Некорректные данные"
        self.stockfish_evaluation.setText(
            f"Оценка (ход {side_to_move}): {evaluation}"
        )

        pv = result.get("pv")
        san_moves: list[str] = []
        valid_variation = True
        if isinstance(pv, list) and pv and self._analysis_board is not None:
            board = self._analysis_board.copy()
            for move in pv:
                try:
                    san_moves.append(board.san(move))
                    board.push(move)
                except (TypeError, ValueError):
                    valid_variation = False
                    break

        best_move = san_moves[0] if valid_variation and san_moves else "Нет данных"
        self.stockfish_best_move.setText(f"Лучший ход: {best_move}")
        if valid_variation and san_moves:
            pv_text = " ".join(san_moves)
        else:
            pv_text = "Нет данных"
        self.stockfish_pv.setText(f"Основной вариант (SAN): {pv_text}")

        depth = result.get("depth")
        depth_text = str(depth) if depth is not None else "Нет данных"
        self.stockfish_depth.setText(f"Глубина: {depth_text}")

    def stop_analysis(self) -> None:
        self._game_analysis_id += 1
        worker = self._analysis_worker
        if worker is not None:
            worker.wait()
            self._analysis_worker = None
        for game_worker in tuple(self._game_analysis_workers):
            game_worker.wait()
        self._game_analysis_workers.clear()
        self._active_game_analysis_worker = None

    def _load_pgn(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить PGN",
            "",
            "PGN-файлы (*.pgn);;Все файлы (*)",
        )
        if not file_path:
            return

        try:
            game = load_first_game(file_path)
        except FileNotFoundError as error:
            QMessageBox.warning(self, "Ошибка загрузки PGN", str(error))
            return
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка загрузки PGN", str(error))
            return
        except Exception:
            QMessageBox.critical(
                self,
                "Ошибка загрузки PGN",
                "Не удалось загрузить файл PGN.",
            )
            return

        try:
            if self.game_repository is None:
                self.game_repository = GameRepository()
            self.game_repository.save_game(game)
        except (OSError, sqlite3.Error) as error:
            QMessageBox.warning(
                self,
                "Ошибка сохранения партии",
                f"Партия загружена, но не сохранена в SQLite: {error}",
            )

        self.display_game(game)
