from dataclasses import dataclass


DEFAULT_ELO = 1200
MAX_VALID_ELO = 4000


def parse_elo(value: str | None) -> int:
    if value is None:
        return DEFAULT_ELO
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ELO
    return rating if 0 < rating <= MAX_VALID_ELO else DEFAULT_ELO


@dataclass(frozen=True)
class GameRecord:
    id: int
    white_player: str
    black_player: str
    result: str
    date: str
    event: str
    pgn_text: str
    white_elo: int = DEFAULT_ELO
    black_elo: int = DEFAULT_ELO
