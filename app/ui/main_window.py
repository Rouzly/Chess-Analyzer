from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.pgn_service import parse_first_game
from app.ui.my_games_page import MyGamesPage
from app.ui.pages import AnalysisPage, PlaceholderPage, ThemeSettingsPage
from app.ui.theme_manager import ThemeManager


class MainWindow(QMainWindow):
    APP_VERSION = "0.1.0"

    def __init__(self, theme_manager: ThemeManager | None = None) -> None:
        super().__init__()
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("Для создания главного окна требуется QApplication.")
        self.theme_manager = theme_manager or ThemeManager(application)
        self.setWindowTitle("Chess Analyzer")
        self.resize(1920, 1080)
        self.setMinimumSize(960, 640)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.pages = QStackedWidget()
        self.pages.setObjectName("centralPages")

        self.analysis_page = AnalysisPage()
        self.analysis_page.open_games_requested.connect(
            lambda: self._select_page(1)
        )
        self.theme_manager.theme_changed.connect(
            self._sync_analysis_history_theme
        )
        self._sync_analysis_history_theme(self.theme_manager.current_theme)
        self.my_games_page = MyGamesPage(self._open_saved_game)
        self.settings_page = ThemeSettingsPage(self.theme_manager)
        page_widgets = [
            PlaceholderPage("Главная"),
            self.my_games_page,
            self.analysis_page,
            PlaceholderPage("Статистика"),
            self.settings_page,
        ]
        for page in page_widgets:
            self.pages.addWidget(page)

        self.navigation = self._create_navigation()

        root_layout.addWidget(self.navigation)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def _sync_analysis_history_theme(self, theme_id: str) -> None:
        palette = self.theme_manager.available_themes[theme_id]
        self.analysis_page.chess_board.set_history_colors(
            palette.accent,
            palette.selected,
            palette.selected_text,
        )

    def _create_navigation(self) -> QWidget:
        navigation = QFrame()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(220)

        layout = QVBoxLayout(navigation)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(8)

        nav_items = ["Главная", "Мои партии", "Анализ", "Статистика", "Настройки"]
        self.navigation_buttons: list[QPushButton] = []

        for index, name in enumerate(nav_items):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setObjectName("navigationButton")
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            layout.addWidget(button)
            self.navigation_buttons.append(button)

        layout.addStretch()

        brand = QLabel("Chess Analyzer")
        brand.setObjectName("brand")
        version = QLabel(f"Версия {self.APP_VERSION}")
        version.setObjectName("version")

        layout.addWidget(brand)
        layout.addWidget(version)

        self._select_page(0)
        return navigation

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.navigation_buttons):
            button.setChecked(button_index == index)
        if self.pages.widget(index) is self.my_games_page:
            self.my_games_page.refresh_games()

    def _open_saved_game(self, pgn_text: str) -> None:
        try:
            game = parse_first_game(pgn_text)
        except ValueError as error:
            QMessageBox.warning(self, "Ошибка загрузки партии", str(error))
            return

        self.analysis_page.display_game(game)
        self._select_page(2)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.my_games_page.stop_import()
        self.analysis_page.stop_analysis()
        super().closeEvent(event)
