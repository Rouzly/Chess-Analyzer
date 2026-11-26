from pathlib import Path

import pytest

from app.services.pgn_service import load_first_game


SINGLE_GAME_PGN = """\
[Event "Test Match"]
[Site "Local"]
[Date "2024.01.02"]
[Round "1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0
"""

MULTIPLE_GAMES_PGN = """\
[Event "First Game"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 1-0

[Event "Second Game"]
[White "Carol"]
[Black "Dave"]
[Result "0-1"]

1. d4 d5 0-1
"""


def write_pgn(tmp_path: Path, content: str) -> Path:
    pgn_path = tmp_path / "game.pgn"
    pgn_path.write_text(content, encoding="utf-8")
    return pgn_path


def test_loads_single_game_with_headers_and_san_moves(tmp_path):
    pgn_path = write_pgn(tmp_path, SINGLE_GAME_PGN)

    game = load_first_game(str(pgn_path))

    assert game.headers["White"] == "Alice"
    assert game.headers["Black"] == "Bob"
    assert game.headers["Result"] == "1-0"

    board = game.board()
    san_moves = []
    for move in game.mainline_moves():
        san_moves.append(board.san(move))
        board.push(move)

    assert san_moves == ["e4", "e5", "Nf3", "Nc6"]


def test_loads_first_game_when_file_contains_multiple_games(tmp_path):
    pgn_path = write_pgn(tmp_path, MULTIPLE_GAMES_PGN)

    game = load_first_game(str(pgn_path))

    assert game.headers["Event"] == "First Game"
    assert game.headers["White"] == "Alice"
    assert game.headers["Black"] == "Bob"
    assert game.headers["Result"] == "1-0"
    assert [move.uci() for move in game.mainline_moves()] == ["e2e4", "e7e5"]


def test_rejects_empty_pgn(tmp_path):
    pgn_path = write_pgn(tmp_path, " \n\t")

    with pytest.raises(ValueError, match="пуст"):
        load_first_game(str(pgn_path))


def test_rejects_text_without_a_pgn_game(tmp_path):
    pgn_path = write_pgn(tmp_path, "this is not a pgn game")

    with pytest.raises(ValueError, match="корректной"):
        load_first_game(str(pgn_path))


def test_rejects_invalid_move_data(tmp_path):
    pgn_path = write_pgn(
        tmp_path,
        '[Event "Broken Game"]\n[Result "*"]\n\n1. e5 *\n',
    )

    with pytest.raises(ValueError, match="некорректные"):
        load_first_game(str(pgn_path))


def test_accepts_incomplete_headers_and_partial_game(tmp_path):
    pgn_path = write_pgn(
        tmp_path,
        '[White "Alice"]\n\n1. e4 e5\n',
    )

    game = load_first_game(str(pgn_path))

    assert game.headers["White"] == "Alice"
    assert len(list(game.mainline_moves())) == 2
    assert game.errors == []
