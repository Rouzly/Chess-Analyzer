from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.pages import PlaceholderPage


class MainWindow(QMainWindow):
    APP_VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess Analyzer")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.pages = QStackedWidget()
        self.pages.setObjectName("centralPages")

        page_names = ["Главная", "Мои партии", "Анализ", "Статистика", "Настройки"]
        for name in page_names:
            self.pages.addWidget(PlaceholderPage(name))

        self.navigation = self._create_navigation()

        root_layout.addWidget(self.navigation)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(self._stylesheet())

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

    @staticmethod
    def _stylesheet() -> str:
        return """
        QMainWindow, QWidget {
            background-color: #17191D;
            color: #F3F4F5;
            font-family: "Segoe UI";
            font-size: 14px;
        }

        #navigation {
            background-color: #252930;
            border-right: 1px solid #30343C;
        }

        #navigationButton {
            min-height: 42px;
            padding: 0 14px;
            border: none;
            border-radius: 8px;
            background-color: transparent;
            color: #C8CBD0;
            text-align: left;
        }

        #navigationButton:hover {
            background-color: #30343C;
            color: #F3F4F5;
        }

        #navigationButton:checked {
            background-color: #8BC49A;
            color: #17191D;
            font-weight: 600;
        }

        #brand {
            color: #F3F4F5;
            font-size: 14px;
            font-weight: 600;
        }

        #version {
            color: #9DA2A9;
            font-size: 12px;
        }

        #centralPages {
            background-color: #17191D;
        }

        #pageTitle {
            color: #F3F4F5;
            font-size: 24px;
            font-weight: 600;
        }
        """
