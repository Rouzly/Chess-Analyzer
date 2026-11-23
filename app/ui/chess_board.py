import chess
import chess.pgn
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PIECE_SYMBOLS = {
    chess.KING: "\u265a",
    chess.QUEEN: "\u265b",
    chess.ROOK: "\u265c",
    chess.BISHOP: "\u265d",
    chess.KNIGHT: "\u265e",
    chess.PAWN: "\u265f",
}


class ChessBoardWidget(QWidget):
    LIGHT_SQUARE = "#D9CDB8"
    DARK_SQUARE = "#78866B"
    SELECTED_SQUARE = "#8BC49A"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.start_board = chess.Board()
        self.move_history: list[chess.Move] = []
        self.san_history: list[str] = []
        self.position_index = 0
        self.selected_square: chess.Square | None = None
        self.square_buttons: dict[chess.Square, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        board_container = QWidget()
        board_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        board_layout = QGridLayout(board_container)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(0)

        for rank in range(7, -1, -1):
            for file in range(8):
                square = chess.square(file, rank)
                button = QPushButton()
                button.setFixedSize(72, 72)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda checked=False, square=square: self._on_square_clicked(square)
                )
                board_layout.addWidget(button, 7 - rank, file)
                self.square_buttons[square] = button

        history_panel = QWidget()
        history_panel.setFixedWidth(220)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(8)

        history_title = QLabel("История ходов")
        history_title.setObjectName("historyTitle")

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setObjectName("moveHistory")

        navigation_layout = QHBoxLayout()
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(8)

        self.back_button = QPushButton("Назад")
        self.forward_button = QPushButton("Вперёд")
        self.back_button.setObjectName("historyButton")
        self.forward_button.setObjectName("historyButton")
        self.back_button.clicked.connect(self.go_back)
        self.forward_button.clicked.connect(self.go_forward)
        navigation_layout.addWidget(self.back_button)
        navigation_layout.addWidget(self.forward_button)

        history_layout.addWidget(history_title)
        history_layout.addWidget(self.history_text, 1)
        history_layout.addLayout(navigation_layout)

        content_layout.addWidget(board_container)
        content_layout.addWidget(history_panel)

        layout.addLayout(content_layout)
        layout.addStretch()
        self._apply_history_styles()
        self._update_board()
        self._update_history()

    def _on_square_clicked(self, square: chess.Square) -> None:
        piece = self.board.piece_at(square)

        if self.selected_square is None:
            if piece is not None and piece.color == self.board.turn:
                self.selected_square = square
            self._update_board()
            return

        if square == self.selected_square:
            self.selected_square = None
            self._update_board()
            return

        if piece is not None and piece.color == self.board.turn:
            self.selected_square = square
            self._update_board()
            return

        move = self._get_legal_move(self.selected_square, square)
        if move is not None:
            san = self.board.san(move)
            if self.position_index < len(self.move_history):
                self.move_history = self.move_history[:self.position_index]
                self.san_history = self.san_history[:self.position_index]
            self.board.push(move)
            self.move_history.append(move)
            self.san_history.append(san)
            self.position_index = len(self.move_history)

        self.selected_square = None
        self._update_board()
        self._update_history()

    def go_back(self) -> None:
        if self.position_index <= 0:
            return
        self.position_index -= 1
        self._rebuild_position()
        self._update_history()

    def go_forward(self) -> None:
        if self.position_index >= len(self.move_history):
            return
        self.position_index += 1
        self._rebuild_position()
        self._update_history()

    def _rebuild_position(self) -> None:
        self.selected_square = None
        self.board = self.start_board.copy()
        for move in self.move_history[:self.position_index]:
            self.board.push(move)
        self._update_board()

    def load_pgn_game(self, game: chess.pgn.Game) -> None:
        self.start_board = game.board()
        self.board = self.start_board.copy()
        self.move_history = []
        self.san_history = []
        self.position_index = 0
        self.selected_square = None

        replay_board = self.start_board.copy()
        for move in game.mainline_moves():
            san = replay_board.san(move)
            replay_board.push(move)
            self.move_history.append(move)
            self.san_history.append(san)

        self.board = self.start_board.copy()
        self.position_index = 0
        self._update_board()
        self._update_history()

    def get_game_info(self, game: chess.pgn.Game) -> dict[str, str]:
        headers = game.headers

        def header(name: str) -> str:
            value = headers.get(name, "").strip()
            return value if value else "Неизвестно"

        return {
            "Белые": header("White"),
            "Чёрные": header("Black"),
            "Результат": header("Result"),
            "Дата": header("Date"),
            "Турнир": header("Event"),
        }

    def _update_history(self) -> None:
        lines: list[str] = []
        for move_index in range(0, len(self.san_history), 2):
            move_number = move_index // 2 + 1
            white_san = self.san_history[move_index]
            black_san = (
                f" {self.san_history[move_index + 1]}"
                if move_index + 1 < len(self.san_history)
                else ""
            )
            lines.append(f"{move_number}. {white_san}{black_san}")

        self.history_text.setPlainText("\n".join(lines))
        self.back_button.setEnabled(self.position_index > 0)
        self.forward_button.setEnabled(self.position_index < len(self.move_history))

    def _apply_history_styles(self) -> None:
        self.history_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #252930;
                color: #F3F4F5;
                border: 1px solid #30343C;
                border-radius: 8px;
                padding: 12px;
                font-family: "Segoe UI";
                font-size: 14px;
            }
            """
        )
        self.setStyleSheet(
            """
            QLabel#historyTitle {
                color: #F3F4F5;
                font-size: 16px;
                font-weight: 600;
            }

            QPushButton#historyButton {
                min-height: 38px;
                border: none;
                border-radius: 8px;
                background-color: #30343C;
                color: #F3F4F5;
                padding: 0 12px;
            }

            QPushButton#historyButton:hover {
                background-color: #3A3F47;
            }

            QPushButton#historyButton:pressed {
                background-color: #8BC49A;
                color: #17191D;
            }

            QPushButton#historyButton:disabled {
                background-color: #202329;
                color: #777C84;
            }
            """
        )

    def _get_legal_move(
        self,
        from_square: chess.Square,
        to_square: chess.Square,
    ) -> chess.Move | None:
        matching_moves = [
            move
            for move in self.board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]

        if not matching_moves:
            return None

        for move in matching_moves:
            if move.promotion == chess.QUEEN:
                return move
        return matching_moves[0]

    def _piece_symbol(self, piece: chess.Piece) -> str:
        symbol = PIECE_SYMBOLS[piece.piece_type]
        if piece.color == chess.WHITE:
            return chr(ord(symbol) - 6)
        return symbol

    def _update_board(self) -> None:
        for square, button in self.square_buttons.items():
            file_index = chess.square_file(square)
            rank_index = chess.square_rank(square)
            is_light = (file_index + rank_index) % 2 == 1
            background = self.LIGHT_SQUARE if is_light else self.DARK_SQUARE

            if square == self.selected_square:
                background = self.SELECTED_SQUARE

            piece = self.board.piece_at(square)
            button.setText(self._piece_symbol(piece) if piece is not None else "")

            text_color = "#F7F4EC" if piece is not None and piece.color == chess.WHITE else "#17191D"
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {background};
                    color: {text_color};
                    border: none;
                    font-family: "Segoe UI Symbol";
                    font-size: 42px;
                }}
                """
            )
