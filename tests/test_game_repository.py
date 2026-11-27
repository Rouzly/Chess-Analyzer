import sqlite3
from pathlib import Path

import chess.pgn
import pytest

from app.database.game_repository import GameRepository


@pytest.fixture
def repository(tmp_path: Path) -> GameRepository:
    return GameRepository(tmp_path / "test_games.sqlite3")


def make_game() -> chess.pgn.Game:
    game = chess.pgn.Game()
    game.headers["Event"] = "Repository Test"
    game.headers["Date"] = "2024.01.02"
    game.headers["White"] = "Alice"
    game.headers["Black"] = "Bob"
    game.headers["Result"] = "1-0"

    board = game.board()
    node = game
    for san in ("e4", "e5", "Nf3"):
        move = board.parse_san(san)
        node = node.add_variation(move)
        board.push(move)

    return game


def test_repository_creates_games_table(tmp_path: Path) -> None:
    database_path = tmp_path / "games.sqlite3"

    GameRepository(database_path)

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "games" in table_names


def test_save_game_persists_headers_and_pgn_text(repository: GameRepository) -> None:
    game_id = repository.save_game(make_game())

    record = repository.get_game_by_id(game_id)

    assert record is not None
    assert record.id == game_id
    assert record.white_player == "Alice"
    assert record.black_player == "Bob"
    assert record.result == "1-0"
    assert record.date == "2024.01.02"
    assert record.event == "Repository Test"
    assert '[White "Alice"]' in record.pgn_text
    assert "1. e4 e5 2. Nf3" in record.pgn_text


def test_repository_persists_valid_ratings_and_defaults_invalid_ones(
    repository: GameRepository,
) -> None:
    game = make_game()
    game.headers["WhiteElo"] = "1842"
    game.headers["BlackElo"] = "?"

    record_id = repository.save_game(game)
    record = repository.get_game_by_id(record_id)

    assert record is not None
    assert record.white_elo == 1842
    assert record.black_elo == 1200


def test_repository_migrates_existing_games_table(tmp_path: Path) -> None:
    database_path = tmp_path / "existing_games.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                white_player TEXT NOT NULL,
                black_player TEXT NOT NULL,
                result TEXT NOT NULL,
                date TEXT NOT NULL,
                event TEXT NOT NULL,
                pgn_text TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO games (
                white_player, black_player, result, date, event, pgn_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("Alice", "Bob", "1-0", "2024.01.02", "Legacy", "1. e4"),
        )

    repository = GameRepository(database_path)
    record = repository.get_game_by_id(1)

    assert record is not None
    assert record.white_player == "Alice"
    assert record.white_elo == 1200
    assert record.black_elo == 1200


def test_get_all_games_returns_saved_records_in_id_order(
    repository: GameRepository,
) -> None:
    first_id = repository.save_game(make_game())
    second_game = make_game()
    second_game.headers["White"] = "Carol"
    second_id = repository.save_game(second_game)

    records = repository.get_all_games()

    assert [record.id for record in records] == [first_id, second_id]
    assert [record.white_player for record in records] == ["Alice", "Carol"]


def test_get_game_by_missing_id_returns_none(repository: GameRepository) -> None:
    assert repository.get_game_by_id(999) is None


def test_delete_game_removes_record(repository: GameRepository) -> None:
    game_id = repository.save_game(make_game())

    assert repository.delete_game(game_id) is True
    assert repository.get_game_by_id(game_id) is None
    assert repository.delete_game(game_id) is False
