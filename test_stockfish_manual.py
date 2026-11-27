import chess

from app.engine.stockfish_engine import StockfishEngine


def main() -> None:
    engine = StockfishEngine("engines/stockfish.exe")

    try:
        engine.start()
        board = chess.Board()
        result = engine.analyze(board, time_limit=1.0)

        score = result["score"].white().score()
        if score is not None:
            pawn_score = score / 100
            print(f"Оценка позиции: {pawn_score:+.2f} пешки")
        else:
            print("Обнаружена матовая позиция.")

        principal_variation = result["pv"]
        variation_board = board.copy()
        san_moves = []
        for move in principal_variation:
            san_moves.append(variation_board.san(move))
            variation_board.push(move)

        print(f"Основной вариант (SAN): {' '.join(san_moves)}")
        print(f"Лучший ход: {result['pv'][0]}")
        print(f"Глубина анализа: {result['depth']}")
    finally:
        engine.close()


if __name__ == "__main__":
    main()
