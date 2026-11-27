from dataclasses import dataclass
from enum import Enum


class MoveCategory(str, Enum):
    BRILLIANT = "Brilliant"
    GREAT = "Great"
    BEST = "Best"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    BOOK = "Book"
    INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"
    MISS = "Miss"
    BLUNDER = "Blunder"


@dataclass(frozen=True)
class MoveClassification:
    move_path: tuple[str, ...]
    san: str
    category: MoveCategory
    expected_points_loss: float


@dataclass(frozen=True)
class GameAnalysisResult:
    white_elo: int
    black_elo: int
    classifications: tuple[MoveClassification, ...]
    opening_book_warning: str | None = None
