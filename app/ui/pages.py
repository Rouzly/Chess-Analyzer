from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.chess_board import ChessBoardWidget
from app.services.pgn_service import load_first_game


class PlaceholderPage(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        layout.addStretch()


class AnalysisPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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
        load_button.setStyleSheet(
            """
            QPushButton#historyButton {
                min-height: 38px;
                border: none;
                border-radius: 8px;
                background-color: #30343C;
                color: #F3F4F5;
                padding: 0 14px;
            }
            QPushButton#historyButton:hover {
                background-color: #3A3F47;
            }
            """
        )

        self.info_label = QLabel(
            "Белые: Неизвестно\n"
            "Чёрные: Неизвестно\n"
            "Результат: Неизвестно\n"
            "Дата: Неизвестно\n"
            "Турнир: Неизвестно"
        )
        self.info_label.setObjectName("gameInfo")
        self.info_label.setStyleSheet(
            """
            QLabel#gameInfo {
                background-color: #252930;
                color: #C8CBD0;
                border-radius: 8px;
                padding: 10px 12px;
            }
            """
        )

        self.chess_board = ChessBoardWidget()

        layout.addLayout(top_layout)
        layout.addWidget(self.info_label)
        layout.addWidget(self.chess_board)
        layout.addStretch()

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

        self.chess_board.load_pgn_game(game)
        game_info = self.chess_board.get_game_info(game)
        self.info_label.setText("\n".join(
            f"{name}: {value}" for name, value in game_info.items()
        ))
