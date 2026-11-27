from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import chess.pgn

from app.models.game_record import DEFAULT_ELO, GameRecord, parse_elo


DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "chess_analyzer.sqlite3"
)


class GameRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_table()

    def create_table(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    white_player TEXT NOT NULL,
                    black_player TEXT NOT NULL,
                    result TEXT NOT NULL,
                    date TEXT NOT NULL,
                    event TEXT NOT NULL,
                    pgn_text TEXT NOT NULL,
                    white_elo INTEGER NOT NULL DEFAULT 1200,
                    black_elo INTEGER NOT NULL DEFAULT 1200
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(games)")
            }
            if "white_elo" not in columns:
                connection.execute(
                    "ALTER TABLE games ADD COLUMN white_elo INTEGER "
                    f"NOT NULL DEFAULT {DEFAULT_ELO}"
                )
            if "black_elo" not in columns:
                connection.execute(
                    "ALTER TABLE games ADD COLUMN black_elo INTEGER "
                    f"NOT NULL DEFAULT {DEFAULT_ELO}"
                )

    def save_game(self, game: chess.pgn.Game) -> int:
        headers = game.headers
        pgn_text = game.accept(
            chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        )

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO games (
                    white_player,
                    black_player,
                    result,
                    date,
                    event,
                    pgn_text,
                    white_elo,
                    black_elo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    headers["White"],
                    headers["Black"],
                    headers["Result"],
                    headers["Date"],
                    headers["Event"],
                    pgn_text,
                    parse_elo(headers.get("WhiteElo")),
                    parse_elo(headers.get("BlackElo")),
                ),
            )
            return int(cursor.lastrowid)

    def get_all_games(self) -> list[GameRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, white_player, black_player, result, date, event,
                       pgn_text, white_elo, black_elo
                FROM games
                ORDER BY id
                """
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def get_game_by_id(self, game_id: int) -> GameRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, white_player, black_player, result, date, event,
                       pgn_text, white_elo, black_elo
                FROM games
                WHERE id = ?
                """,
                (game_id,),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def delete_game(self, game_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM games WHERE id = ?",
                (game_id,),
            )
            return cursor.rowcount > 0

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> GameRecord:
        return GameRecord(
            id=row["id"],
            white_player=row["white_player"],
            black_player=row["black_player"],
            result=row["result"],
            date=row["date"],
            event=row["event"],
            pgn_text=row["pgn_text"],
            white_elo=row["white_elo"],
            black_elo=row["black_elo"],
        )
