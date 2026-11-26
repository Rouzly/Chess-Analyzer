from __future__ import annotations

import sqlite3

import chess.pgn
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.database.game_repository import GameRepository
from app.services.pgn_service import load_first_game
from app.ui.chess_board import ChessBoardWidget
from app.ui.my_games_page import GameCardWidget, MyGamesPage
from app.ui.theme_manager import ThemeManager, ThemePalette


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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)

        title_label = QLabel("Анализ")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        title_label.setObjectName("pageTitle")

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(title_label)
        top_layout.addStretch()

        load_button = QPushButton("Загрузить PGN")
        load_button.setObjectName("historyButton")
        load_button.clicked.connect(self._load_pgn)
        top_layout.addWidget(load_button)

        self.info_label = QLabel(
            "Белые: Неизвестно\n"
            "Чёрные: Неизвестно\n"
            "Результат: Неизвестно\n"
            "Дата: Неизвестно\n"
            "Турнир: Неизвестно"
        )
        self.info_label.setObjectName("gameInfo")
        self.info_label.setMargin(10)

        self.chess_board = ChessBoardWidget()
        self.game_repository: GameRepository | None = None

        layout.addLayout(top_layout)
        layout.addWidget(self.info_label)
        layout.addWidget(self.chess_board)
        layout.addStretch()

    def display_game(self, game: chess.pgn.Game) -> None:
        self.chess_board.load_pgn_game(game)
        game_info = self.chess_board.get_game_info(game)
        self.info_label.setText(
            "\n".join(f"{name}: {value}" for name, value in game_info.items())
        )

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
