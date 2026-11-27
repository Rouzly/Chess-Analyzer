from __future__ import annotations

import copy
from pathlib import Path

import chess.pgn
from PySide6.QtCore import QThread, Signal

from app.engine.stockfish_engine import StockfishEngine
from app.models.move_analysis import GameAnalysisResult
from app.services.move_classifier import GameMoveClassifier


class GameAnalysisWorker(QThread):
    progress = Signal(int, int)
    finished_analysis = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        game: chess.pgn.Game,
        executable_path: str | Path,
        time_limit: float,
        white_elo: int,
        black_elo: int,
        opening_book_path: str | Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.game = copy.deepcopy(game)
        self.executable_path = executable_path
        self.time_limit = time_limit
        self.white_elo = white_elo
        self.black_elo = black_elo
        self.opening_book_path = opening_book_path

    def run(self) -> None:
        engine = StockfishEngine(self.executable_path)
        result: GameAnalysisResult | None = None
        error_message: str | None = None
        try:
            engine.start()
            classifier = GameMoveClassifier(
                engine,
                time_limit=self.time_limit,
                opening_book_path=self.opening_book_path,
            )
            result = classifier.classify(
                self.game,
                white_elo=self.white_elo,
                black_elo=self.black_elo,
                progress_callback=self.progress.emit,
            )
        except Exception as error:
            error_message = str(error) or error.__class__.__name__
        finally:
            try:
                engine.close()
            except Exception as error:
                if error_message is None:
                    error_message = f"Не удалось закрыть Stockfish: {error}"

        if error_message is not None:
            self.error.emit(error_message)
        elif result is not None:
            self.finished_analysis.emit(result)
        else:
            self.error.emit("Stockfish не вернул результаты анализа партии.")
