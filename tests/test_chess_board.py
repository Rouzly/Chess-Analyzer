from io import StringIO

import chess
import chess.pgn
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui.chess_board import ChessBoardWidget


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def chess_board(qapp: QApplication):
    widget = ChessBoardWidget()
    yield widget
    widget.close()
    widget.deleteLater()


def click_move(chess_board: ChessBoardWidget, start: str, end: str) -> None:
    chess_board._on_square_clicked(chess.parse_square(start))
    chess_board._on_square_clicked(chess.parse_square(end))


def load_game(pgn_text: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(StringIO(pgn_text))
    assert game is not None
    return game


def test_initial_position_has_twenty_legal_moves(
    chess_board: ChessBoardWidget,
) -> None:
    assert len(list(chess_board.board.legal_moves)) == 20


def test_selecting_same_piece_twice_clears_selection(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board._on_square_clicked(chess.E2)
    assert chess_board.selected_square == chess.E2

    chess_board._on_square_clicked(chess.E2)

    assert chess_board.selected_square is None
    assert chess_board.move_markers[chess.E3].isHidden()


def test_piece_symbols_are_explicit_for_both_colors(
    chess_board: ChessBoardWidget,
) -> None:
    white_king = chess.Piece(chess.KING, chess.WHITE)
    black_king = chess.Piece(chess.KING, chess.BLACK)

    assert chess_board._piece_symbol(white_king) == "\u2654"
    assert chess_board._piece_symbol(black_king) == "\u265a"


def test_legal_move_changes_position_and_turn(
    chess_board: ChessBoardWidget,
) -> None:
    initial_position = chess_board.board.fen()

    click_move(chess_board, "e2", "e4")

    assert chess_board.board.fen() != initial_position
    assert chess_board.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert chess_board.board.turn == chess.BLACK
    assert chess_board.move_history == [chess.Move.from_uci("e2e4")]
    assert chess_board.san_history == ["e4"]


def test_illegal_move_does_not_change_position_or_history(
    chess_board: ChessBoardWidget,
) -> None:
    initial_position = chess_board.board.fen()

    click_move(chess_board, "e2", "e5")

    assert chess_board.board.fen() == initial_position
    assert chess_board.move_history == []
    assert chess_board.san_history == []
    assert chess_board.position_index == 0


def test_can_move_back_and_forward_through_history(
    chess_board: ChessBoardWidget,
) -> None:
    click_move(chess_board, "e2", "e4")
    position_after_e4 = chess_board.board.fen()

    chess_board.go_back()

    assert chess_board.board.fen() == chess.Board().fen()
    assert chess_board.position_index == 0

    chess_board.go_forward()

    assert chess_board.board.fen() == position_after_e4
    assert chess_board.position_index == 1


def test_experimenting_preserves_the_original_line_and_adds_variations(
    chess_board: ChessBoardWidget,
) -> None:
    game = load_game("1. e4 e5 2. Nf3 Nc6 3. Bb5 *")
    chess_board.load_pgn_game(game)
    original_line = list(chess_board.game_tree.mainline())

    chess_board.go_to_position(3)
    click_move(chess_board, "d7", "d6")
    click_move(chess_board, "c2", "c4")

    assert chess_board.san_history == ["e4", "e5", "Nf3", "d6", "c4"]
    assert chess_board.current_node is not None
    assert [child.san() for child in original_line[2].variations] == ["Nc6", "d6"]
    assert list(chess_board.game_tree.mainline()) == original_line
    assert chess_board.has_alternative_line
    assert "Экспериментальная линия" in chess_board.alternative_line_label.text()

    chess_board.return_to_mainline()
    assert chess_board.san_history == ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    assert chess_board.position_index == 5
    assert not chess_board.has_alternative_line

    chess_board.go_to_position(len(chess_board.move_history))
    assert chess_board.board.peek() == chess.Move.from_uci("f1b5")

    chess_board.go_to_position(3)
    alternate_index = chess_board.variation_selector.findData(
        chess.Move.from_uci("d7d6").uci()
    )
    assert alternate_index > 0
    chess_board.variation_selector.setCurrentIndex(alternate_index)
    assert chess_board.san_history == ["e4", "e5", "Nf3", "d6", "c4"]
    assert chess_board.board.peek() == chess.Move.from_uci("d7d6")
    assert len(original_line[2].variations) == 2

    chess_board.go_to_position(3)
    original_continuation = chess_board.variation_selector.findData(
        chess.Move.from_uci("b8c6").uci()
    )
    assert original_continuation > 0
    chess_board.variation_selector.setCurrentIndex(original_continuation)
    assert chess_board.san_history == ["e4", "e5", "Nf3", "Nc6", "Bb5"]
    assert chess_board.board.peek() == chess.Move.from_uci("b8c6")

    chess_board.return_to_mainline()
    chess_board.go_to_position(1)
    click_move(chess_board, "c7", "c5")
    click_move(chess_board, "g1", "f3")

    assert chess_board.san_history == ["e4", "c5", "Nf3"]
    assert [child.san() for child in chess_board.game_tree.variations[0].variations] == [
        "e5",
        "c5",
    ]

    chess_board.return_to_mainline()
    assert chess_board.san_history == ["e4", "e5", "Nf3", "Nc6", "Bb5"]


def test_replaying_existing_move_does_not_create_duplicate_variation(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board.load_pgn_game(load_game("1. e4 e5 *"))
    chess_board.go_to_position(1)
    click_move(chess_board, "e7", "e5")

    assert len(chess_board.game_tree.variations[0].variations) == 1
    assert chess_board.san_history == ["e4", "e5"]


def test_loading_new_pgn_resets_previous_game_history(
    chess_board: ChessBoardWidget,
) -> None:
    previous_game = chess.pgn.read_game(StringIO("1. e4 e5 *"))
    new_game = chess.pgn.read_game(StringIO("1. d4 d5 2. c4 *"))
    assert previous_game is not None
    assert new_game is not None

    chess_board.load_pgn_game(previous_game)
    chess_board.go_forward()
    chess_board.go_forward()
    chess_board.load_pgn_game(new_game)

    assert chess_board.san_history == ["d4", "d5", "c4"]
    assert chess_board.position_index == 0
    assert chess_board.board.fen() == chess_board.start_board.fen()
    assert "1. d4 d5" in chess_board.history_text.toPlainText()
    assert "2. c4" in chess_board.history_text.toPlainText()
    assert not chess_board.back_button.isEnabled()
    assert chess_board.forward_button.isEnabled()
    assert chess_board.start_button.isEnabled() is False
    assert not chess_board.has_alternative_line


def test_selecting_piece_shows_only_its_legal_moves(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board._on_square_clicked(chess.E2)

    assert chess_board.move_markers[chess.E3].isVisibleTo(chess_board)
    assert chess_board.move_markers[chess.E4].isVisibleTo(chess_board)
    assert chess_board.move_markers[chess.E5].isHidden()
    assert chess_board.square_buttons[chess.E2].property("selected")


def test_selecting_another_piece_replaces_move_hints(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board._on_square_clicked(chess.E2)
    chess_board._on_square_clicked(chess.C2)

    assert chess_board.move_markers[chess.E3].isHidden()
    assert chess_board.move_markers[chess.C3].isVisibleTo(chess_board)
    assert chess_board.square_buttons[chess.C2].property("selected")


def test_capture_and_en_passant_destinations_use_capture_marker(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board.load_pgn_game(load_game("1. e4 d5 *"))
    chess_board.go_forward()
    chess_board.go_forward()
    chess_board._on_square_clicked(chess.E4)

    marker = chess_board.move_markers[chess.D5]
    assert marker.objectName() == "legalCaptureMarker"
    assert marker.isVisibleTo(chess_board)

    chess_board.load_pgn_game(load_game("1. e4 a6 2. e5 d5 *"))
    for _ in range(4):
        chess_board.go_forward()
    chess_board._on_square_clicked(chess.E5)

    assert chess_board.board.piece_at(chess.D6) is None
    assert chess_board.move_markers[chess.D6].objectName() == "legalCaptureMarker"
    assert chess_board.move_markers[chess.D6].isVisibleTo(chess_board)


def test_castling_and_promotion_squares_are_shown_as_legal_moves(
    chess_board: ChessBoardWidget,
) -> None:
    castling_game = load_game(
        "1. Nf3 Nf6 2. g3 g6 3. Bg2 Bg7 4. O-O *"
    )
    chess_board.load_pgn_game(castling_game)
    for _ in range(6):
        chess_board.go_forward()
    chess_board._on_square_clicked(chess.E1)

    assert chess_board.move_markers[chess.G1].isVisibleTo(chess_board)

    promotion_game = load_game(
        '[SetUp "1"]\n'
        '[FEN "7k/P7/8/8/8/8/8/7K w - - 0 1"]\n'
        '[Result "*"]\n\n'
        "1. a8=Q+ *"
    )
    chess_board.load_pgn_game(promotion_game)
    chess_board._on_square_clicked(chess.A7)

    assert chess_board.move_markers[chess.A8].isVisibleTo(chess_board)
    chess_board._on_square_clicked(chess.A8)
    assert chess_board.board.piece_at(chess.A8) == chess.Piece(
        chess.QUEEN,
        chess.WHITE,
    )


def test_check_animation_tracks_the_side_to_move_and_stops_after_check(
    chess_board: ChessBoardWidget,
) -> None:
    game = load_game("1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7+ *")
    chess_board.load_pgn_game(game)
    for _ in range(7):
        chess_board.go_forward()

    assert chess_board.board.is_check()
    assert chess_board.square_buttons[chess.E8].property("inCheck")
    assert chess_board._check_timer.isActive()

    pulse_before = chess_board.square_buttons[chess.E8].property("checkPulse")
    chess_board._toggle_check_pulse()
    assert chess_board.square_buttons[chess.E8].property("checkPulse") != pulse_before

    chess_board.go_back()
    assert not chess_board.square_buttons[chess.E8].property("inCheck")
    assert not chess_board._check_timer.isActive()

    white_check_game = load_game(
        '[SetUp "1"]\n'
        '[FEN "7k/8/8/8/8/8/6q1/4K3 b - - 0 1"]\n'
        '[Result "*"]\n\n'
        "1... Qe2+ *"
    )
    chess_board.load_pgn_game(white_check_game)
    chess_board.go_forward()

    assert chess_board.board.is_check()
    assert chess_board.square_buttons[chess.E1].property("inCheck")
    assert not chess_board.square_buttons[chess.E8].property("inCheck")


def test_last_move_highlight_follows_history_navigation(
    chess_board: ChessBoardWidget,
) -> None:
    chess_board.load_pgn_game(load_game("1. e4 e5 *"))

    assert not chess_board.square_buttons[chess.E2].property("lastMove")
    chess_board.go_forward()
    assert chess_board.square_buttons[chess.E2].property("lastMove")
    assert chess_board.square_buttons[chess.E4].property("lastMove")

    chess_board.go_forward()
    assert chess_board.square_buttons[chess.E7].property("lastMove")
    assert chess_board.square_buttons[chess.E5].property("lastMove")

    chess_board.go_back()
    assert chess_board.square_buttons[chess.E2].property("lastMove")
    assert chess_board.square_buttons[chess.E4].property("lastMove")
    assert not chess_board.square_buttons[chess.E7].property("lastMove")


def test_board_coordinates_follow_orientation(
    chess_board: ChessBoardWidget,
) -> None:
    assert [label.text() for label in chess_board.file_labels] == list("abcdefgh")
    assert [label.text() for label in chess_board.rank_labels] == list("87654321")
    assert chess_board.board_grid.getItemPosition(
        chess_board.board_grid.indexOf(chess_board.square_buttons[chess.A8])
    ) == (0, 1, 1, 1)

    chess_board.set_flipped(True)

    assert [label.text() for label in chess_board.file_labels] == list("hgfedcba")
    assert [label.text() for label in chess_board.rank_labels] == list("12345678")
    assert chess_board.board_grid.getItemPosition(
        chess_board.board_grid.indexOf(chess_board.square_buttons[chess.A8])
    ) == (7, 8, 1, 1)


def test_clicking_history_moves_to_position_after_selected_move(
    chess_board: ChessBoardWidget,
    qapp: QApplication,
) -> None:
    chess_board.load_pgn_game(load_game("1. e4 e5 2. Nf3 Nc6 *"))
    chess_board.show()
    qapp.processEvents()

    def click_history_text(text: str, position: int) -> None:
        cursor = chess_board.history_text.document().find(text)
        point: QPoint = chess_board.history_text.cursorRect(cursor).center()
        assert chess_board.history_text.anchorAt(point) == f"position:{position}"
        QTest.mouseClick(
            chess_board.history_text.viewport(),
            Qt.MouseButton.LeftButton,
            pos=point,
        )
        qapp.processEvents()

    click_history_text("Nf3", 3)

    assert chess_board.position_index == 3
    assert chess_board.board.peek() == chess.Move.from_uci("g1f3")
    assert chess_board.square_buttons[chess.F3].property("lastMove")
    assert "background-color:#3a493e" in chess_board.history_text.toHtml()

    click_history_text("e4", 1)
    assert chess_board.position_index == 1
    assert chess_board.board.peek() == chess.Move.from_uci("e2e4")
    assert chess_board.square_buttons[chess.E4].property("lastMove")

    chess_board.start_button.click()
    assert chess_board.position_index == 0
    assert chess_board.board.move_stack == []
    assert not chess_board.start_button.isEnabled()
