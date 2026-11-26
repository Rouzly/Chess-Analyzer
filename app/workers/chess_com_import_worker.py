from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal

from app.database.game_repository import GameRepository
from app.services.chess_com_service import (
    ChessComAPIError,
    ChessComService,
    ImportCancelledError,
    PlayerNotFoundError,
    RateLimitError,
    ChessComConnectionError,
    ChessComTimeoutError,
)

logger = logging.getLogger(__name__)


class ChessComImportWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(int, int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        username: str,
        months: int,
        all_history: bool,
        database_path: str | Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.username = username
        self.months = months
        self.all_history = all_history
        self.database_path = Path(database_path)
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            repository = GameRepository(self.database_path)
            service = ChessComService(repository=repository)
            summary = service.import_games_with_summary(
                self.username,
                months=self.months,
                all_history=self.all_history,
                cancellation_check=self._cancel_event.is_set,
                progress_callback=self.progress.emit,
            )
        except ImportCancelledError:
            self.cancelled.emit()
        except PlayerNotFoundError:
            self.failed.emit("Публичный пользователь Chess.com не найден.")
        except RateLimitError:
            self.failed.emit(
                "Chess.com ограничил частоту запросов. Попробуйте позже."
            )
        except ChessComConnectionError:
            self.failed.emit("Не удалось подключиться к Chess.com.")
        except ChessComTimeoutError:
            self.failed.emit("Истекло время ожидания ответа Chess.com.")
        except ChessComAPIError as error:
            self.failed.emit(str(error))
        except (sqlite3.Error, OSError):
            logger.exception("Chess.com import failed while accessing SQLite")
            self.failed.emit("Не удалось сохранить партии в базе данных.")
        except Exception:
            logger.exception("Unexpected Chess.com import failure")
            self.failed.emit("Не удалось выполнить импорт из Chess.com.")
        else:
            self.succeeded.emit(summary.imported_count, summary.found_count)
