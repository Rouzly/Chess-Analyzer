import copy

import chess
import chess.pgn
from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.models.move_analysis import MoveClassification
from app.ui.move_category_labels import move_category_label

PIECE_SYMBOLS = {
    chess.WHITE: {
        chess.KING: "\u2654",
        chess.QUEEN: "\u2655",
        chess.ROOK: "\u2656",
        chess.BISHOP: "\u2657",
        chess.KNIGHT: "\u2658",
        chess.PAWN: "\u2659",
    },
    chess.BLACK: {
        chess.KING: "\u265a",
        chess.QUEEN: "\u265b",
        chess.ROOK: "\u265c",
        chess.BISHOP: "\u265d",
        chess.KNIGHT: "\u265e",
        chess.PAWN: "\u265f",
    },
}


class ChessBoardWidget(QWidget):
    position_changed = Signal()
    SQUARE_SIZE = 64
    COORDINATE_SIZE = 22
    FILE_NAMES = "abcdefgh"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.start_board = chess.Board()
        self.game_tree: chess.pgn.Game | None = None
        self.current_node: chess.pgn.GameNode | None = None
        self.active_line: list[chess.pgn.ChildNode] = []
        self.move_history: list[chess.Move] = []
        self.san_history: list[str] = []
        self.move_classifications: dict[tuple[str, ...], MoveClassification] = {}
        self.position_index = 0
        self.selected_square: chess.Square | None = None
        self.board_flipped = False
        self.has_alternative_line = False
        self._history_accent = "#8BC49A"
        self._history_selected = "#3A493E"
        self._history_selected_text = "#F3F4F5"
        self.square_buttons: dict[chess.Square, QPushButton] = {}
        self.move_markers: dict[chess.Square, QLabel] = {}
        self.file_labels: list[QLabel] = []
        self.rank_labels: list[QLabel] = []
        self._check_square: chess.Square | None = None
        self._check_pulse = False
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(420)
        self._check_timer.timeout.connect(self._toggle_check_pulse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        board_container = QWidget()
        board_container.setObjectName("boardContainer")
        board_container.setFixedSize(
            self.SQUARE_SIZE * 8 + self.COORDINATE_SIZE + 2,
            self.SQUARE_SIZE * 8 + self.COORDINATE_SIZE + 2,
        )
        board_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        board_layout = QGridLayout(board_container)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(0)
        self.board_grid = board_layout

        for row in range(8):
            rank_label = self._create_coordinate_label()
            rank_label.setFixedSize(self.COORDINATE_SIZE, self.SQUARE_SIZE)
            self.rank_labels.append(rank_label)
            board_layout.addWidget(rank_label, row, 0)

            for column in range(8):
                square = chess.square(column, 7 - row)
                button = QPushButton()
                button.setProperty("boardSquare", True)
                button.setFixedSize(self.SQUARE_SIZE, self.SQUARE_SIZE)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda checked=False, square=square: self._on_square_clicked(square)
                )
                board_layout.addWidget(button, row, column + 1)
                self.square_buttons[square] = button
                marker = QLabel(button)
                marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                marker.hide()
                self.move_markers[square] = marker

        for column in range(8):
            file_label = self._create_coordinate_label()
            file_label.setFixedSize(self.SQUARE_SIZE, self.COORDINATE_SIZE)
            self.file_labels.append(file_label)
            board_layout.addWidget(file_label, 8, column + 1)

        history_title = QLabel("История ходов")
        history_title.setObjectName("historyTitle")

        self.history_text = QTextBrowser()
        self.history_text.setOpenLinks(False)
        self.history_text.setOpenExternalLinks(False)
        self.history_text.setObjectName("moveHistory")
        self.history_text.setMinimumHeight(92)
        self.history_text.anchorClicked.connect(self._on_history_link_clicked)

        self.alternative_line_label = QLabel()
        self.alternative_line_label.setObjectName("alternativeLineNotice")
        self.alternative_line_label.setWordWrap(True)
        self.alternative_line_label.hide()

        self.back_button = QPushButton("Назад")
        self.forward_button = QPushButton("Вперёд")
        self.start_button = QPushButton("К началу")
        self.back_button.setObjectName("historyButton")
        self.forward_button.setObjectName("historyButton")
        self.start_button.setObjectName("historyButton")
        self.back_button.clicked.connect(self.go_back)
        self.forward_button.clicked.connect(self.go_forward)
        self.start_button.clicked.connect(self.go_to_start)

        self.variation_selector = QComboBox()
        self.variation_selector.setObjectName("variationSelector")
        self.variation_selector.currentIndexChanged.connect(
            self._on_variation_selected
        )
        self.mainline_button = QPushButton("Основная линия")
        self.mainline_button.setObjectName("historyButton")
        self.mainline_button.clicked.connect(self.return_to_mainline)

        self.turn_label = QLabel()
        self.turn_label.setObjectName("boardTurn")
        self.flip_button = QPushButton("Перевернуть доску")
        self.flip_button.setObjectName("historyButton")
        self.flip_button.clicked.connect(self._toggle_board_orientation)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self.back_button)
        controls_layout.addWidget(self.forward_button)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.variation_selector)
        controls_layout.addWidget(self.mainline_button)
        controls_layout.addWidget(self.turn_label, 1)
        controls_layout.addWidget(self.flip_button)

        layout.addWidget(board_container, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(history_title)
        layout.addWidget(self.alternative_line_label)
        layout.addWidget(self.history_text)
        layout.addLayout(controls_layout)
        self._update_coordinates()
        self._update_board()
        self._update_history()

    @staticmethod
    def _create_coordinate_label() -> QLabel:
        label = QLabel()
        label.setObjectName("boardCoordinate")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _on_square_clicked(self, square: chess.Square) -> None:
        piece = self.board.piece_at(square)

        if piece is not None and piece.color == self.board.turn:
            if square == self.selected_square:
                self.selected_square = None
            else:
                self.selected_square = square
            self._update_board()
            return

        if self.selected_square is None:
            self._update_board()
            return

        move = self._get_legal_move(self.selected_square, square)
        if move is None:
            self.selected_square = None
            self._update_board()
            return

        self._play_move(move)
        self.selected_square = None
        self._update_board()
        self._update_history()
        self.position_changed.emit()

    def set_flipped(self, flipped: bool) -> None:
        if self.board_flipped == flipped:
            return
        self.board_flipped = flipped
        self._update_coordinates()
        self._update_board()

    def _toggle_board_orientation(self) -> None:
        self.set_flipped(not self.board_flipped)

    def _play_move(self, move: chess.Move) -> None:
        if self.current_node is None:
            if self.game_tree is None:
                self.game_tree = chess.pgn.Game()
                self.start_board = self.game_tree.board()
            self.current_node = self.game_tree

        child = next(
            (
                variation
                for variation in self.current_node.variations
                if variation.move == move
            ),
            None,
        )
        if child is None:
            child = self.current_node.add_variation(move)

        self._select_node(child)

    def go_back(self) -> None:
        self.go_to_position(self.position_index - 1)

    def go_forward(self) -> None:
        self.go_to_position(self.position_index + 1)

    def go_to_start(self) -> None:
        self.go_to_position(0)

    def set_history_colors(
        self,
        accent: str,
        selected: str,
        selected_text: str,
    ) -> None:
        self._history_accent = accent
        self._history_selected = selected
        self._history_selected_text = selected_text
        self._update_history()

    def set_move_classifications(
        self,
        classifications: tuple[MoveClassification, ...],
    ) -> None:
        self.move_classifications = {
            classification.move_path: classification
            for classification in classifications
        }
        self._update_history()

    def go_to_position(self, position_index: int) -> None:
        if not 0 <= position_index <= len(self.move_history):
            return
        if position_index == self.position_index:
            return

        if self.game_tree is None:
            return
        self.position_index = position_index
        self._rebuild_position()
        self._update_history()
        self.position_changed.emit()

    def return_to_mainline(self) -> None:
        if self.game_tree is None:
            return

        self.active_line = list(self.game_tree.mainline())
        self.position_index = min(self.position_index, len(self.active_line))
        self._sync_line_lists()
        self._rebuild_position()
        self._update_history()
        self.position_changed.emit()

    def _select_node(self, node: chess.pgn.ChildNode) -> None:
        if self.game_tree is None:
            return

        path: list[chess.pgn.ChildNode] = []
        current: chess.pgn.GameNode | None = node
        while current is not None and current.parent is not None:
            if not isinstance(current, chess.pgn.ChildNode):
                break
            path.append(current)
            current = current.parent
        path.reverse()

        self.active_line = path + list(node.mainline())
        self.position_index = len(path)
        self._sync_line_lists()
        self._rebuild_position()
        self._update_history()

    def _sync_line_lists(self) -> None:
        self.move_history = [node.move for node in self.active_line]
        self.san_history = [node.san() for node in self.active_line]
        if self.game_tree is not None:
            self.current_node = (
                self.game_tree
                if self.position_index == 0
                else self.active_line[self.position_index - 1]
            )
        self.has_alternative_line = self._active_line_is_alternative()

    def _active_line_is_alternative(self) -> bool:
        if self.game_tree is None:
            return False
        mainline = list(self.game_tree.mainline())
        return any(
            index >= len(mainline) or node is not mainline[index]
            for index, node in enumerate(self.active_line)
        )

    def _on_variation_selected(self, index: int) -> None:
        if index <= 0 or self.current_node is None:
            return
        move_uci = self.variation_selector.itemData(index)
        if not isinstance(move_uci, str):
            return
        move = chess.Move.from_uci(move_uci)
        for child in self.current_node.variations:
            if child.move == move:
                self._select_node(child)
                self.position_changed.emit()
                return

    def _update_variation_selector(self) -> None:
        self.variation_selector.blockSignals(True)
        self.variation_selector.clear()
        self.variation_selector.addItem("Продолжения из позиции")

        if self.current_node is not None:
            current_board = self.current_node.board()
            main_variation = (
                self.current_node.variations[0]
                if self.current_node.variations
                else None
            )
            for child in self.current_node.variations:
                san = current_board.san(child.move)
                label = (
                    f"{san} · основная"
                    if child is main_variation
                    else f"{san} · вариант"
                )
                self.variation_selector.addItem(label, child.move.uci())

            if self.position_index < len(self.active_line):
                next_move = self.active_line[self.position_index].move.uci()
                selected_index = self.variation_selector.findData(next_move)
                if selected_index >= 0:
                    self.variation_selector.setCurrentIndex(selected_index)

        self.variation_selector.blockSignals(False)
        self.mainline_button.setEnabled(self.has_alternative_line)

    def _on_history_link_clicked(self, url: QUrl) -> None:
        target = url.toString()
        if not target.startswith("position:"):
            return
        try:
            position_index = int(target.removeprefix("position:"))
        except ValueError:
            return
        self.go_to_position(position_index)

    def _rebuild_position(self) -> None:
        self.selected_square = None
        if self.game_tree is None:
            self.board = self.start_board.copy()
            self.current_node = None
        else:
            self.board = self.game_tree.board()
            for node in self.active_line[:self.position_index]:
                self.board.push(node.move)
            self.current_node = (
                self.game_tree
                if self.position_index == 0
                else self.active_line[self.position_index - 1]
            )
        self._update_board()

    def load_pgn_game(self, game: chess.pgn.Game) -> None:
        self.game_tree = copy.deepcopy(game)
        self.start_board = self.game_tree.board()
        self.board = self.start_board.copy()
        self.current_node = self.game_tree
        self.active_line = list(self.game_tree.mainline())
        self.move_classifications.clear()
        self.position_index = 0
        self.selected_square = None
        self._sync_line_lists()
        self.alternative_line_label.clear()
        self.alternative_line_label.hide()
        self._update_board()
        self._update_history()
        self.position_changed.emit()

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
        scroll_bar = self.history_text.verticalScrollBar()
        scroll_position = scroll_bar.value()
        self.history_text.document().setDefaultStyleSheet(
            "a {"
            f"color: {self._history_accent};"
            "text-decoration: none;"
            "padding: 2px 4px;"
            "}"
            ".currentMove {"
            f"background-color: {self._history_selected};"
            f"color: {self._history_selected_text};"
            "font-weight: bold;"
            "}"
            ".moveRow { margin: 4px 0; }"
            f".moveClassification {{ color: {self._history_accent}; }}"
            ".startRow { margin-bottom: 8px; }"
        )
        lines: list[str] = []
        replay_board = self.start_board.copy()
        move_rows: dict[int, dict[chess.Color, str]] = {}
        for move_index, move in enumerate(self.move_history):
            move_number = replay_board.fullmove_number
            side_to_move = replay_board.turn
            san = self.san_history[move_index]
            if self.position_index == move_index + 1:
                link = (
                    f'<a href="position:{move_index + 1}" '
                    f'class="currentMove">{san} </a>'
                )
            else:
                link = f'<a href="position:{move_index + 1}">{san} </a>'
            move_path = tuple(
                node.move.uci()
                for node in self.active_line[:move_index + 1]
            )
            classification = self.move_classifications.get(move_path)
            if classification is not None:
                link += (
                    '<span class="moveClassification">'
                    f'[{move_category_label(classification.category)}]</span>'
                )
            move_rows.setdefault(move_number, {})[side_to_move] = link
            replay_board.push(move)

        for move_number, moves in move_rows.items():
            white_move = moves.get(chess.WHITE, "")
            black_move = moves.get(chess.BLACK, "")
            if not white_move:
                lines.append(
                    f'<div class="moveRow">{move_number}. ... {black_move}</div>'
                )
            else:
                lines.append(
                    f'<div class="moveRow">{move_number}. {white_move}'
                    f'{black_move}</div>'
                )

        self.history_text.setHtml(
            '<div class="startRow">'
            f'<a href="position:0" class="{"currentMove" if self.position_index == 0 else ""}">'
            "Начальная позиция</a></div>"
            + "\n".join(lines)
        )
        scroll_bar.setValue(min(scroll_position, scroll_bar.maximum()))
        self.back_button.setEnabled(self.position_index > 0)
        self.forward_button.setEnabled(self.position_index < len(self.move_history))
        self.start_button.setEnabled(self.position_index > 0)
        side_to_move = "белых" if self.board.turn == chess.WHITE else "чёрных"
        self.turn_label.setText(f"Ход {side_to_move}")
        self._update_variation_selector()
        if self.has_alternative_line:
            self.alternative_line_label.setText(
                "Экспериментальная линия · сохранена только в текущем сеансе"
            )
        else:
            self.alternative_line_label.setText("Основная линия")
        self.alternative_line_label.show()

    def _update_coordinates(self) -> None:
        for row, label in enumerate(self.rank_labels):
            rank = row + 1 if self.board_flipped else 8 - row
            label.setText(str(rank))

        for column, label in enumerate(self.file_labels):
            file_index = 7 - column if self.board_flipped else column
            label.setText(self.FILE_NAMES[file_index])

        for square, button in self.square_buttons.items():
            row, column = self._square_grid_position(square)
            self.board_grid.addWidget(button, row, column)

    def _square_grid_position(self, square: chess.Square) -> tuple[int, int]:
        file_index = chess.square_file(square)
        rank_index = chess.square_rank(square)
        if self.board_flipped:
            return rank_index, 8 - file_index
        return 7 - rank_index, file_index + 1

    def _legal_destinations(self) -> dict[chess.Square, bool]:
        destinations: dict[chess.Square, bool] = {}
        if self.selected_square is None:
            return destinations

        for move in self.board.legal_moves:
            if move.from_square == self.selected_square:
                destinations[move.to_square] = (
                    destinations.get(move.to_square, False)
                    or self.board.is_capture(move)
                )
        return destinations

    def _refresh_button_style(self, button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _update_check_animation(self) -> chess.Square | None:
        checked_king = self.board.king(self.board.turn) if self.board.is_check() else None
        if checked_king is None:
            self._check_timer.stop()
            self._check_square = None
            self._check_pulse = False
            return None

        if checked_king != self._check_square:
            self._check_square = checked_king
            self._check_pulse = False

        if not self._check_timer.isActive():
            self._check_timer.start()
        return checked_king

    def _toggle_check_pulse(self) -> None:
        if self._check_square is None:
            self._check_timer.stop()
            return

        self._check_pulse = not self._check_pulse
        button = self.square_buttons[self._check_square]
        button.setProperty("checkPulse", self._check_pulse)
        self._refresh_button_style(button)

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
        return PIECE_SYMBOLS[piece.color][piece.piece_type]

    def _update_board(self) -> None:
        destinations = self._legal_destinations()
        checked_king = self._update_check_animation()
        last_move = (
            self.move_history[self.position_index - 1]
            if self.position_index > 0
            else None
        )

        for square, button in self.square_buttons.items():
            file_index = chess.square_file(square)
            rank_index = chess.square_rank(square)
            is_light = (file_index + rank_index) % 2 == 1

            piece = self.board.piece_at(square)
            button.setText(self._piece_symbol(piece) if piece is not None else "")
            button.setProperty("squareTone", "light" if is_light else "dark")
            button.setProperty("pieceColor", (
                "white" if piece.color == chess.WHITE else "black"
            ) if piece is not None else "")
            button.setProperty("selected", square == self.selected_square)
            button.setProperty(
                "lastMove",
                last_move is not None
                and square in (last_move.from_square, last_move.to_square),
            )
            button.setProperty("inCheck", square == checked_king)
            button.setProperty(
                "checkPulse",
                self._check_pulse if square == checked_king else False,
            )
            self._refresh_button_style(button)

            marker = self.move_markers[square]
            if square in destinations:
                is_capture = destinations[square]
                marker.setObjectName(
                    "legalCaptureMarker" if is_capture else "legalMoveMarker"
                )
                if is_capture:
                    marker.setGeometry(
                        8,
                        8,
                        self.SQUARE_SIZE - 16,
                        self.SQUARE_SIZE - 16,
                    )
                else:
                    marker_size = 16
                    marker.setGeometry(
                        (self.SQUARE_SIZE - marker_size) // 2,
                        (self.SQUARE_SIZE - marker_size) // 2,
                        marker_size,
                        marker_size,
                    )
                marker.style().unpolish(marker)
                marker.style().polish(marker)
                marker.show()
                marker.raise_()
            else:
                marker.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._check_timer.stop()
        super().closeEvent(event)
