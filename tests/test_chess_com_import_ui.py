from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.database.game_repository import GameRepository
from app.services.chess_com_service import (
    ChessComImportSummary,
    ImportCancelledError,
    PlayerNotFoundError,
)
from app.services.pgn_service import parse_first_game
from app.ui.my_games_page import MyGamesPage


GAME_PGN = """\
[Event "Chess.com Test"]
[Date "2024.01.02"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 e5 1-0
"""


@pytest.fixture
def qapp():
    application = QApplication.instance() or QApplication([])
    return application


@pytest.fixture
def repository(tmp_path: Path) -> GameRepository:
    return GameRepository(tmp_path / "import_ui.sqlite3")


def wait_for_worker(page: MyGamesPage, qapp: QApplication) -> None:
    worker = page._import_worker
    assert worker is not None
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    qapp.processEvents()


def install_import_service(monkeypatch, service_class) -> None:
    monkeypatch.setattr(
        "app.workers.chess_com_import_worker.ChessComService",
        service_class,
    )


def test_import_panel_has_required_controls(
    qapp: QApplication,
    repository: GameRepository,
) -> None:
    page = MyGamesPage(lambda pgn_text: None, repository=repository)

    assert page.chess_com_username.placeholderText() == "Ник Chess.com"
    assert page.chess_com_import_button.text() == "Импортировать"
    assert [
        page.chess_com_period.itemText(index)
        for index in range(page.chess_com_period.count())
    ] == ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев", "Вся история"]
    assert page.chess_com_progress.isHidden()


def test_empty_username_does_not_start_worker(
    qapp: QApplication,
    repository: GameRepository,
) -> None:
    page = MyGamesPage(lambda pgn_text: None, repository=repository)

    page.chess_com_import_button.click()

    assert "Введите ник" in page.chess_com_status.text()
    assert page._import_worker is None
    assert page.chess_com_import_button.isEnabled()


def test_import_starts_in_background_and_uses_selected_period(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()
    release = Event()
    calls = []

    class WaitingService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(
            self,
            username,
            months,
            all_history,
            cancellation_check,
            progress_callback,
        ):
            calls.append((username, months, all_history))
            progress_callback("Загрузка тестового архива...")
            started.set()
            release.wait(3)
            return ChessComImportSummary(found_count=0, imported_games=[])

    install_import_service(monkeypatch, WaitingService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("  alice  ")
    page.chess_com_period.setCurrentIndex(2)

    page.chess_com_import_button.click()
    try:
        assert started.wait(1)
        qapp.processEvents()
        assert page._import_worker is not None
        assert page._import_worker.isRunning()
        assert not page.chess_com_import_button.isEnabled()
        assert not page.chess_com_progress.isHidden()
        assert page.chess_com_status.text() == "Загрузка тестового архива..."
        assert calls == [("alice", 6, False)]
    finally:
        release.set()

    wait_for_worker(page, qapp)
    assert page.chess_com_import_button.isEnabled()
    assert page.chess_com_progress.isHidden()


def test_successful_import_updates_list_and_count(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported_game = parse_first_game(GAME_PGN)

    class SuccessfulService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(self, username, **kwargs):
            self.repository.save_game(imported_game)
            return ChessComImportSummary(
                found_count=1,
                imported_games=[imported_game],
            )

    install_import_service(monkeypatch, SuccessfulService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("alice")

    page.chess_com_import_button.click()
    wait_for_worker(page, qapp)

    assert len(page.game_cards) == 1
    assert page.count_label.text() == "Всего партий: 1"
    assert "Добавлено партий: 1 из 1" in page.chess_com_status.text()
    assert page.chess_com_import_button.isEnabled()
    assert page.chess_com_progress.isHidden()


def test_import_reports_api_error_and_restores_controls(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingPlayerService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(self, username, **kwargs):
            raise PlayerNotFoundError("missing")

    install_import_service(monkeypatch, MissingPlayerService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("not-a-player")

    page.chess_com_import_button.click()
    wait_for_worker(page, qapp)

    assert "не найден" in page.chess_com_status.text()
    assert page.chess_com_import_button.isEnabled()
    assert page.chess_com_username.isEnabled()
    assert page.chess_com_period.isEnabled()
    assert not page.chess_com_progress.isVisible()


def test_import_reports_existing_games_without_duplicates(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExistingGamesService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(self, username, **kwargs):
            return ChessComImportSummary(
                found_count=2,
                imported_games=[],
            )

    install_import_service(monkeypatch, ExistingGamesService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("alice")

    page.chess_com_import_button.click()
    wait_for_worker(page, qapp)

    assert "все 2 уже есть в базе" in page.chess_com_status.text()
    assert page.chess_com_import_button.isEnabled()


def test_import_reports_database_error_and_restores_controls(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DatabaseErrorService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(self, username, **kwargs):
            raise sqlite3.OperationalError("database unavailable")

    install_import_service(monkeypatch, DatabaseErrorService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("alice")

    page.chess_com_import_button.click()
    wait_for_worker(page, qapp)

    assert "Не удалось сохранить партии" in page.chess_com_status.text()
    assert page.chess_com_import_button.isEnabled()
    assert page.chess_com_username.isEnabled()
    assert page.chess_com_period.isEnabled()
    assert page.chess_com_progress.isHidden()


def test_stopping_import_waits_for_worker_to_exit(
    qapp: QApplication,
    repository: GameRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()

    class CancellableService:
        def __init__(self, repository):
            self.repository = repository

        def import_games_with_summary(
            self,
            username,
            months,
            all_history,
            cancellation_check,
            progress_callback,
        ):
            started.set()
            while not cancellation_check():
                Event().wait(0.01)
            raise ImportCancelledError("cancelled")

    install_import_service(monkeypatch, CancellableService)
    page = MyGamesPage(lambda pgn_text: None, repository=repository)
    page.chess_com_username.setText("alice")

    page.chess_com_import_button.click()
    assert started.wait(1)

    page.stop_import()
    qapp.processEvents()

    assert page._import_worker is None
    assert page.chess_com_import_button.isEnabled()
    assert page.chess_com_progress.isHidden()
