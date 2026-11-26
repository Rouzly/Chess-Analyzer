from io import StringIO

import chess
import chess.pgn
import pytest
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


def test_new_move_after_going_back_replaces_old_future_branch(
    chess_board: ChessBoardWidget,
) -> None:
    click_move(chess_board, "e2", "e4")
    click_move(chess_board, "e7", "e5")
    chess_board.go_back()

    click_move(chess_board, "c7", "c5")

    assert chess_board.san_history == ["e4", "c5"]
    assert chess_board.move_history == [
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("c7c5"),
    ]
    assert chess_board.board.piece_at(chess.C5) == chess.Piece(chess.PAWN, chess.BLACK)
    assert chess_board.position_index == 2
    assert not chess_board.forward_button.isEnabled()


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
    assert chess_board.history_text.toPlainText() == "1. d4 d5\n2. c4"
    assert not chess_board.back_button.isEnabled()
    assert chess_board.forward_button.isEnabled()
