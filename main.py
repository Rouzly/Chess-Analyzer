import sys

from PySide6.QtWidgets import QApplication, QMainWindow


class ChessAnalyzerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess Analyzer")
        self.resize(1100, 700)


def main() -> int:
    try:
        app = QApplication(sys.argv)
        window = ChessAnalyzerWindow()
        window.show()
        return app.exec()
    except Exception as error:
        print(f"Не удалось запустить приложение: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
