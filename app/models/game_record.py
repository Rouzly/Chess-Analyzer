from dataclasses import dataclass


@dataclass(frozen=True)
class GameRecord:
    id: int
    white_player: str
    black_player: str
    result: str
    date: str
    event: str
    pgn_text: str
