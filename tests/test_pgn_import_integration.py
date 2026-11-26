from pathlib import Path

import pytest

from app.database.game_repository import GameRepository
from app.services.pgn_service import load_first_game


VALID_PGN = """\
[Event "Integration Test"]
[Date "2024.01.02"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""


def test_loaded_pgn_game_is_saved_to_repository(tmp_path: Path) -> None:
    pgn_path = tmp_path / "imported.pgn"
    pgn_path.write_text(VALID_PGN, encoding="utf-8")
    repository = GameRepository(tmp_path / "games.sqlite3")

    game = load_first_game(str(pgn_path))
    game_id = repository.save_game(game)

    saved_game = repository.get_game_by_id(game_id)
    assert saved_game is not None
    assert saved_game.white_player == "Alice"
    assert saved_game.black_player == "Bob"
    assert saved_game.result == "1-0"
    assert saved_game.date == "2024.01.02"
    assert saved_game.event == "Integration Test"
    assert "1. e4 e5 2. Nf3" in saved_game.pgn_text


def test_invalid_pgn_is_not_saved(tmp_path: Path) -> None:
    pgn_path = tmp_path / "invalid.pgn"
    pgn_path.write_text(
        '[Event "Invalid"]\n[Result "*"]\n\n1. e5 *\n',
        encoding="utf-8",
    )
    repository = GameRepository(tmp_path / "games.sqlite3")

    with pytest.raises(ValueError):
        load_first_game(str(pgn_path))

    assert repository.get_all_games() == []
