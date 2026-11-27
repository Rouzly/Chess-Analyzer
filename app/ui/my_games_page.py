from __future__ import annotations

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.database.game_repository import GameRepository
from app.models.game_record import GameRecord
from app.workers.chess_com_import_worker import ChessComImportWorker


class MyGamesPage(QWidget):
    RESULT_ALL = "all"
    RESULT_WHITE_WINS = "white_wins"
    RESULT_BLACK_WINS = "black_wins"
    RESULT_DRAWS = "draws"

    def __init__(
        self,
        open_game: Callable[[str], None],
        repository: GameRepository | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("myGamesPage")
        self._open_game_callback = open_game
        self._repository = repository
        self._games_by_id: dict[int, GameRecord] = {}
        self._games: list[GameRecord] = []
        self.game_cards: list[GameCardWidget] = []
        self._selected_game_id: int | None = None
        self._import_worker: ChessComImportWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        top_layout = QHBoxLayout()
        title_label = QLabel("История партий")
        title_label.setObjectName("pageTitle")
        top_layout.addWidget(title_label)

        self.count_label = QLabel("Всего партий: 0")
        self.count_label.setObjectName("gameCount")
        top_layout.addWidget(self.count_label)
        top_layout.addStretch()

        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.setObjectName("historyButton")
        self.refresh_button.clicked.connect(self.refresh_games)
        top_layout.addWidget(self.refresh_button)

        import_panel = QFrame()
        import_panel.setObjectName("chessComImportPanel")
        import_layout = QVBoxLayout(import_panel)
        import_layout.setContentsMargins(14, 12, 14, 12)
        import_layout.setSpacing(8)

        import_controls = QHBoxLayout()
        import_controls.setSpacing(8)
        self.chess_com_username = QLineEdit()
        self.chess_com_username.setObjectName("chessComUsername")
        self.chess_com_username.setPlaceholderText("Ник Chess.com")

        self.chess_com_period = QComboBox()
        self.chess_com_period.setObjectName("chessComPeriod")
        for label, months in (
            ("1 месяц", 1),
            ("3 месяца", 3),
            ("6 месяцев", 6),
            ("12 месяцев", 12),
            ("Вся история", None),
        ):
            self.chess_com_period.addItem(label, months)

        self.chess_com_import_button = QPushButton("Импортировать")
        self.chess_com_import_button.setObjectName("historyButton")
        self.chess_com_import_button.clicked.connect(self._start_chess_com_import)
        import_controls.addWidget(self.chess_com_username, 1)
        import_controls.addWidget(self.chess_com_period)
        import_controls.addWidget(self.chess_com_import_button)

        self.chess_com_progress = QProgressBar()
        self.chess_com_progress.setObjectName("chessComProgress")
        self.chess_com_progress.setRange(0, 0)
        self.chess_com_progress.setTextVisible(False)
        self.chess_com_progress.setFixedHeight(5)
        self.chess_com_progress.hide()

        self.chess_com_status = QLabel()
        self.chess_com_status.setObjectName("chessComStatus")
        self.chess_com_status.setWordWrap(True)

        import_layout.addLayout(import_controls)
        import_layout.addWidget(self.chess_com_progress)
        import_layout.addWidget(self.chess_com_status)

        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("gameSearch")
        self.search_input.setPlaceholderText("Поиск по именам игроков")
        self.search_input.textChanged.connect(self._apply_filters)

        self.result_filter = QComboBox()
        self.result_filter.setObjectName("resultFilter")
        self.result_filter.addItem("Все результаты", self.RESULT_ALL)
        self.result_filter.addItem("Победа белых", self.RESULT_WHITE_WINS)
        self.result_filter.addItem("Победа чёрных", self.RESULT_BLACK_WINS)
        self.result_filter.addItem("Ничья", self.RESULT_DRAWS)
        self.result_filter.currentIndexChanged.connect(self._apply_filters)
        filters_layout.addWidget(self.search_input, 1)
        filters_layout.addWidget(self.result_filter)

        self.message_label = QLabel()
        self.message_label.setObjectName("gamesMessage")
        self.message_label.setWordWrap(True)

        self.cards_content = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_content)
        self.cards_layout.setContentsMargins(2, 2, 8, 2)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setObjectName("gamesScrollArea")
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setWidget(self.cards_content)

        self.open_button = QPushButton("Открыть в анализе")
        self.open_button.setObjectName("historyButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected_game)

        layout.addLayout(top_layout)
        layout.addWidget(import_panel)
        layout.addLayout(filters_layout)
        layout.addWidget(self.cards_scroll, 1)
        layout.addWidget(self.message_label)
        layout.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignRight)

        self.refresh_games()

    def _start_chess_com_import(self) -> None:
        if self._import_worker is not None and self._import_worker.isRunning():
            return

        username = self.chess_com_username.text().strip()
        if not username:
            self.chess_com_status.setText("Введите ник Chess.com.")
            return

        if self._repository is None:
            try:
                self._repository = GameRepository()
            except (OSError, sqlite3.Error):
                self.chess_com_status.setText(
                    "Не удалось открыть базу данных для импорта партий."
                )
                return

        months = self.chess_com_period.currentData()
        all_history = months is None
        self.chess_com_import_button.setEnabled(False)
        self.chess_com_username.setEnabled(False)
        self.chess_com_period.setEnabled(False)
        self.chess_com_progress.show()
        self.chess_com_status.setText("Подготовка импорта Chess.com...")

        self._import_worker = ChessComImportWorker(
            username=username,
            months=months if months is not None else 3,
            all_history=all_history,
            database_path=self._repository.database_path,
            parent=self,
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.succeeded.connect(self._on_import_succeeded)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.cancelled.connect(self._on_import_cancelled)
        self._import_worker.finished.connect(self._on_import_thread_finished)
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        self._import_worker.start()

    @Slot(str)
    def _on_import_progress(self, message: str) -> None:
        self.chess_com_status.setText(message)

    @Slot(int, int)
    def _on_import_succeeded(self, imported_count: int, found_count: int) -> None:
        if imported_count:
            self.chess_com_status.setText(
                f"Импорт завершён. Добавлено партий: {imported_count} из {found_count}."
            )
        elif found_count:
            self.chess_com_status.setText(
                f"Новых партий нет: все {found_count} уже есть в базе."
            )
        else:
            self.chess_com_status.setText(
                "В выбранном периоде не найдено партий с корректным PGN."
            )
        self._finish_import_controls()
        self.refresh_games()

    @Slot(str)
    def _on_import_failed(self, message: str) -> None:
        self.chess_com_status.setText(message)
        self._finish_import_controls()

    @Slot()
    def _on_import_cancelled(self) -> None:
        self.chess_com_status.setText("Импорт отменён.")
        self._finish_import_controls()

    @Slot()
    def _on_import_thread_finished(self) -> None:
        self._import_worker = None
        self._finish_import_controls()

    def _finish_import_controls(self) -> None:
        self.chess_com_import_button.setEnabled(True)
        self.chess_com_username.setEnabled(True)
        self.chess_com_period.setEnabled(True)
        self.chess_com_progress.hide()

    def stop_import(self) -> None:
        worker = self._import_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
        self._import_worker = None

    def refresh_games(self) -> None:
        self._clear_cards()
        self._games_by_id.clear()
        self._games.clear()
        self.open_button.setEnabled(False)
        self._selected_game_id = None

        try:
            if self._repository is None:
                self._repository = GameRepository()
            games = self._repository.get_all_games()
        except (OSError, sqlite3.Error) as error:
            self.count_label.setText("Всего партий: —")
            self.message_label.setText(
                f"Не удалось загрузить список партий из базы данных: {error}"
            )
            return

        self._games = games
        self._games_by_id = {game.id: game for game in games}
        self.count_label.setText(f"Всего партий: {len(games)}")

        if not games:
            self.message_label.setText(
                "Сохранённых партий пока нет. Загрузите PGN на странице «Анализ»."
            )
            return

        self._apply_filters()

    def _open_selected_game(self) -> None:
        self._open_game(self._selected_game_id)

    def _open_game(self, game_id: int | None) -> None:
        game = self._games_by_id.get(game_id)
        if game is not None:
            self._select_game(game.id)
            self._open_game_callback(game.pgn_text)

    def _apply_filters(self, *_args) -> None:
        self._clear_cards()
        self.open_button.setEnabled(False)
        self._selected_game_id = None

        if not self._games:
            return

        query = self.search_input.text().strip().casefold()
        selected_result = self.result_filter.currentData()

        matching_games = []
        for game in self._games:
            if (
                query
                and query not in game.white_player.casefold()
                and query not in game.black_player.casefold()
            ):
                continue

            outcome = self._outcome_for_game(game)
            if selected_result != self.RESULT_ALL and outcome != selected_result:
                continue
            matching_games.append((game, outcome))

        if not matching_games:
            self.message_label.setText("По выбранным условиям партии не найдены.")
            return

        self.message_label.clear()
        for game, outcome in matching_games:
            card = GameCardWidget(game, outcome)
            card.clicked.connect(self._select_game)
            card.double_clicked.connect(self._open_game)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
            self.game_cards.append(card)

    @classmethod
    def _outcome_for_game(cls, game: GameRecord) -> str:
        if game.result == "1/2-1/2":
            return cls.RESULT_DRAWS
        if game.result == "1-0":
            return cls.RESULT_WHITE_WINS
        if game.result == "0-1":
            return cls.RESULT_BLACK_WINS
        return cls.RESULT_ALL

    def _select_game(self, game_id: int) -> None:
        self._selected_game_id = game_id
        for index in range(self.cards_layout.count() - 1):
            widget = self.cards_layout.itemAt(index).widget()
            if isinstance(widget, GameCardWidget):
                widget.set_selected(widget.game.id == game_id)
        self.open_button.setEnabled(game_id in self._games_by_id)

    def _clear_cards(self) -> None:
        self.game_cards.clear()
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class GameCardWidget(QFrame):
    clicked = Signal(int)
    double_clicked = Signal(int)

    def __init__(
        self,
        game: GameRecord,
        outcome: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName("gameCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(12)

        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(5)

        self.players_label = QLabel(f"{game.white_player}  —  {game.black_player}")
        self.players_label.setObjectName("gamePlayers")

        event = game.event if game.event not in ("", "?") else "Событие неизвестно"
        date = game.date if game.date not in ("", "????.??.??") else "Дата неизвестна"
        self.details_label = QLabel(f"{date}   ·   {event}")
        self.details_label.setObjectName("gameDetails")
        detail_layout.addWidget(self.players_label)
        detail_layout.addWidget(self.details_label)
        layout.addLayout(detail_layout, 1)

        badge_text, outcome_key = self._outcome_style(outcome)
        self.outcome_label = QLabel(badge_text)
        self.outcome_label.setObjectName("gameOutcome")
        self.outcome_label.setProperty("outcome", outcome_key)
        self.result_label = QLabel(game.result)
        self.result_label.setObjectName("gameDetails")

        result_layout = QVBoxLayout()
        result_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        result_layout.addWidget(self.outcome_label, 0, Qt.AlignmentFlag.AlignRight)
        result_layout.addWidget(self.result_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(result_layout)

    @staticmethod
    def _outcome_style(outcome: str) -> tuple[str, str]:
        labels = {
            MyGamesPage.RESULT_WHITE_WINS: ("Победа белых", "white_wins"),
            MyGamesPage.RESULT_BLACK_WINS: ("Победа чёрных", "black_wins"),
            MyGamesPage.RESULT_DRAWS: ("Ничья", "draw"),
            MyGamesPage.RESULT_ALL: ("Без результата", "unknown"),
        }
        return labels.get(outcome, labels[MyGamesPage.RESULT_ALL])

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.game.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.game.id)
        super().mouseDoubleClickEvent(event)
