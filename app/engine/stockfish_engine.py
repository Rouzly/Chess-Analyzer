from pathlib import Path

import chess
import chess.engine


class StockfishEngine:
    def __init__(self, executable_path: str | Path) -> None:
        self.executable_path = str(executable_path)
        self._engine: chess.engine.SimpleEngine | None = None

    def start(self) -> None:
        if self._engine is not None:
            return

        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(
                self.executable_path
            )
            if "UCI_ShowWDL" in self._engine.options:
                self._engine.configure({"UCI_ShowWDL": True})
        except (OSError, chess.engine.EngineError) as error:
            raise RuntimeError(
                f"Не удалось запустить Stockfish: {error}"
            ) from error

    def analyze(
        self,
        board: chess.Board,
        time_limit: float = 1.0,
    ) -> chess.engine.InfoDict:
        self._validate_analysis(time_limit)
        assert self._engine is not None
        return self._engine.analyse(
            board.copy(),
            chess.engine.Limit(time=time_limit),
        )

    def analyze_variations(
        self,
        board: chess.Board,
        time_limit: float = 1.0,
        count: int = 2,
    ) -> list[chess.engine.InfoDict]:
        self._validate_analysis(time_limit)
        if count < 1:
            raise ValueError("Число вариантов должно быть положительным.")
        assert self._engine is not None
        result = self._engine.analyse(
            board.copy(),
            chess.engine.Limit(time=time_limit),
            multipv=count,
        )
        return result if isinstance(result, list) else [result]

    def _validate_analysis(self, time_limit: float) -> None:
        if self._engine is None:
            raise RuntimeError("Stockfish не запущен или уже закрыт.")
        if time_limit <= 0:
            raise ValueError("Ограничение времени должно быть положительным.")

    def close(self) -> None:
        if self._engine is None:
            return

        self._engine.quit()
        self._engine = None
