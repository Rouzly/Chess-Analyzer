from app.models.move_analysis import MoveCategory


MOVE_CATEGORY_LABELS = {
    MoveCategory.BRILLIANT: "Блестящий",
    MoveCategory.GREAT: "Замечательный",
    MoveCategory.BOOK: "Теоретический",
    MoveCategory.BEST: "Лучший",
    MoveCategory.EXCELLENT: "Отличный",
    MoveCategory.GOOD: "Неплохой",
    MoveCategory.INACCURACY: "Неточность",
    MoveCategory.MISTAKE: "Ошибка",
    MoveCategory.MISS: "Упущенный шанс",
    MoveCategory.BLUNDER: "Зевок",
}


def move_category_label(category: MoveCategory) -> str:
    return MOVE_CATEGORY_LABELS[category]
