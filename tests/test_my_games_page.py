import sqlite3
from io import StringIO
from pathlib import Path

import chess.pgn
import pytest
from PySide6.QtWidgets import QApplication

from app.database.game_repository import GameRepository
from app.ui.main_window import MainWindow
from app.ui.my_games_page import MyGamesPage


VALID_PGN = """\
[Event "Page Test"]
[Date "2024.01.02"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""


@pytest.fixture
def qapp():
    application = QApplication.instance() or QApplication([])
    return application


@pytest.fixture
def repository(tmp_path: Path) -> GameRepository:
    return GameRepository(tmp_path / "page_test.sqlite3")


def save_game(
    repository: GameRepository,
    white: str,
    black: str,
    result: str,
    event: str,
) -> None:
    game = chess.pgn.Game()
    game.headers["Event"] = event
    game.headers["Date"] = "2024.01.02"
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Result"] = result
    repository.save_game(game)


def test_my_games_page_shows_empty_message_and_opens_selected_game(
    qapp: QApplication,
    repository: GameRepository,
) -> None:
    opened_pgn: list[str] = []
    page = MyGamesPage(opened_pgn.append, repository=repository)

    assert not page.game_cards
    assert "партий пока нет" in page.message_label.text()

    game = chess.pgn.read_game(StringIO(VALID_PGN))
    assert game is not None
    repository.save_game(game)
    page.refresh_games()

    assert len(page.game_cards) == 1
    card = page.game_cards[0]
    assert card.players_label.text() == "Alice  —  Bob"
    assert card.result_label.text() == "1-0"
    assert "2024.01.02" in card.details_label.text()
    assert "Page Test" in card.details_label.text()

    card.clicked.emit(card.game.id)
    assert page.open_button.isEnabled()
    page.open_button.click()
    assert len(opened_pgn) == 1
    assert '[White "Alice"]' in opened_pgn[0]


def test_opening_saved_game_displays_it_on_analysis_page(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = chess.pgn.read_game(StringIO(VALID_PGN))
    assert game is not None
    repository.save_game(game)

    monkeypatch.setattr("app.ui.my_games_page.GameRepository", lambda: repository)
    window = MainWindow()
    window._select_page(1)

    window.my_games_page.game_cards[0].clicked.emit(
        window.my_games_page.game_cards[0].game.id
    )
    window.my_games_page.open_button.click()

    assert window.pages.currentIndex() == 2
    assert window.analysis_page.chess_board.san_history == ["e4", "e5", "Nf3"]
    assert "Alice" in window.analysis_page.info_label.text()
    window.close()


def test_my_games_page_reports_database_read_errors(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MyGamesPage(lambda pgn_text: None, repository=repository)

    def fail_to_read_games():
        raise sqlite3.OperationalError("database is unavailable")

    monkeypatch.setattr(repository, "get_all_games", fail_to_read_games)
    page.refresh_games()

    assert "Не удалось загрузить список партий" in page.message_label.text()
    assert not page.game_cards


def test_search_filters_by_player_names(
    qapp: QApplication,
    repository: GameRepository,
) -> None:
    save_game(repository, "Alice", "Bob", "1-0", "Game One")
    save_game(repository, "Carol", "Dave", "0-1", "Game Two")
    page = MyGamesPage(lambda pgn_text: None, repository=repository)

    page.search_input.setText("car")

    assert len(page.game_cards) == 1
    assert page.game_cards[0].game.white_player == "Carol"
    assert page.count_label.text() == "Всего партий: 2"


def test_result_filters_classify_white_black_wins_and_draws_without_player_selection(
    qapp: QApplication,
    repository: GameRepository,
) -> None:
    save_game(repository, "Alice", "Bob", "1-0", "White Wins")
    save_game(repository, "Bob", "Alice", "0-1", "Black Wins")
    save_game(repository, "Alice", "Carol", "1/2-1/2", "Draw")
    save_game(repository, "Carol", "Dave", "1/2-1/2", "Other Draw")
    page = MyGamesPage(lambda pgn_text: None, repository=repository)

    assert not hasattr(page, "player_filter")
    assert [
        page.result_filter.itemText(index)
        for index in range(page.result_filter.count())
    ] == ["Все результаты", "Победа белых", "Победа чёрных", "Ничья"]

    page.result_filter.setCurrentIndex(
        page.result_filter.findData(MyGamesPage.RESULT_WHITE_WINS)
    )
    assert [card.game.event for card in page.game_cards] == ["White Wins"]
    assert page.game_cards[0].outcome_label.text() == "Победа белых"

    page.result_filter.setCurrentIndex(
        page.result_filter.findData(MyGamesPage.RESULT_BLACK_WINS)
    )
    assert [card.game.event for card in page.game_cards] == ["Black Wins"]
    assert page.game_cards[0].outcome_label.text() == "Победа чёрных"

    page.result_filter.setCurrentIndex(
        page.result_filter.findData(MyGamesPage.RESULT_DRAWS)
    )
    assert [card.game.event for card in page.game_cards] == ["Draw", "Other Draw"]
    assert all(card.outcome_label.text() == "Ничья" for card in page.game_cards)
