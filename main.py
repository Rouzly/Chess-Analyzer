import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    try:
        app = QApplication(sys.argv)
        app.setOrganizationName("ChessAnalyzer")
        app.setApplicationName("ChessAnalyzer")
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception as error:
        print(f"Не удалось запустить приложение: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
