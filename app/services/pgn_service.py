from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import TextIO

import chess.pgn


def load_first_game(file_path: str) -> chess.pgn.Game:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError("Файл не найден или недоступен")

    try:
        with path.open("r", encoding="utf-8-sig") as pgn_file:
            if not pgn_file.read().strip():
                raise ValueError("Файл PGN пуст")
            pgn_file.seek(0)
            return _read_first_game(pgn_file)
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("Не удалось прочитать файл PGN") from error


def parse_first_game(pgn_text: str) -> chess.pgn.Game:
    if not pgn_text.strip():
        raise ValueError("Файл PGN пуст")
    return _read_first_game(StringIO(pgn_text))


def _read_first_game(pgn_file: TextIO) -> chess.pgn.Game:
    game = chess.pgn.read_game(pgn_file)
    if game is None:
        raise ValueError("Файл не содержит корректной шахматной PGN-партии")

    if game.errors:
        raise ValueError("Файл содержит некорректные данные PGN")

    if not game.variations and dict(game.headers) == dict(chess.pgn.Headers()):
        raise ValueError("Файл не содержит корректной шахматной PGN-партии")

    return game
