from pathlib import Path

import chess
import chess.engine
from PySide6.QtCore import QThread, Signal

from app.engine.stockfish_engine import StockfishEngine


class StockfishAnalysisWorker(QThread):
    finished_analysis = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        board: chess.Board,
        executable_path: str | Path,
        time_limit: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.board = board.copy()
        self.executable_path = executable_path
        self.time_limit = time_limit

    def run(self) -> None:
        engine = StockfishEngine(self.executable_path)
        result: chess.engine.InfoDict | None = None
        error_message: str | None = None

        try:
            engine.start()
            result = engine.analyze(self.board, self.time_limit)
        except Exception as error:
            error_message = str(error)
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
            self.error.emit("Stockfish не вернул результат анализа.")
