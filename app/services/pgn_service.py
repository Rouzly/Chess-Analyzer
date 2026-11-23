from __future__ import annotations

from pathlib import Path

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
            game = chess.pgn.read_game(pgn_file)
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("Не удалось прочитать файл PGN") from error

    if game is None:
        raise ValueError("Файл не содержит корректной шахматной PGN-партии")

    if game.errors:
        raise ValueError("Файл содержит некорректные данные PGN")

    return game
