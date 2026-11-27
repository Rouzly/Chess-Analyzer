from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemePalette:
    name: str
    description: str
    window: str
    panel: str
    panel_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    hover: str
    selected: str
    selected_text: str
    input: str
    board_light: str
    board_dark: str
    board_selected: str
    board_last_move: str
    board_check: str
    board_check_pulse: str
    piece_white: str
    piece_black: str
    win_background: str
    win_text: str
    loss_background: str
    loss_text: str
    neutral_background: str
    neutral_text: str
    preview: tuple[str, str, str]


THEMES: dict[str, ThemePalette] = {
    "graphite": ThemePalette(
        name="Graphite",
        description="Сдержанный графит с мягким зелёным акцентом.",
        window="#17191D",
        panel="#252930",
        panel_alt="#202329",
        border="#30343C",
        text="#F3F4F5",
        muted="#9DA2A9",
        accent="#8BC49A",
        accent_text="#17191D",
        hover="#30343C",
        selected="#3A493E",
        selected_text="#F3F4F5",
        input="#252930",
        board_light="#D9CDB8",
        board_dark="#78866B",
        board_selected="#8BC49A",
        board_last_move="#BBAE78",
        board_check="#A94E53",
        board_check_pulse="#C26369",
        piece_white="#F7F4EC",
        piece_black="#17191D",
        win_background="#254431",
        win_text="#A8D8B2",
        loss_background="#492D31",
        loss_text="#E0A4A8",
        neutral_background="#343A42",
        neutral_text="#C8CBD0",
        preview=("#17191D", "#252930", "#8BC49A"),
    ),
    "violet_night": ThemePalette(
        name="Violet Night",
        description="Глубокий сливовый графит и приглушённая лаванда.",
        window="#1B1920",
        panel="#292631",
        panel_alt="#24212B",
        border="#393443",
        text="#F2EFF5",
        muted="#A7A0B1",
        accent="#B7A6CF",
        accent_text="#211C29",
        hover="#373241",
        selected="#42384F",
        selected_text="#F2EFF5",
        input="#292631",
        board_light="#D5CEDC",
        board_dark="#777080",
        board_selected="#B7A6CF",
        board_last_move="#A99BBC",
        board_check="#A6535D",
        board_check_pulse="#C46771",
        piece_white="#F7F4FA",
        piece_black="#211C29",
        win_background="#344039",
        win_text="#B8D0BE",
        loss_background="#48343D",
        loss_text="#DDBBC7",
        neutral_background="#3A3741",
        neutral_text="#D0CBD8",
        preview=("#1B1920", "#292631", "#B7A6CF"),
    ),
    "amber_ember": ThemePalette(
        name="Amber Ember",
        description="Тёплый коричневый графит с медовым оттенком.",
        window="#1D1A18",
        panel="#2B2622",
        panel_alt="#25211E",
        border="#403832",
        text="#F3EFEA",
        muted="#ADA197",
        accent="#D3AE75",
        accent_text="#282117",
        hover="#3A322B",
        selected="#493B2C",
        selected_text="#F3EFEA",
        input="#2B2622",
        board_light="#DDCFB8",
        board_dark="#827260",
        board_selected="#D3AE75",
        board_last_move="#C4A35F",
        board_check="#A9504D",
        board_check_pulse="#C46A62",
        piece_white="#FAF5EB",
        piece_black="#211C18",
        win_background="#41402D",
        win_text="#D7D1A7",
        loss_background="#4B3630",
        loss_text="#E0B8A7",
        neutral_background="#3C3833",
        neutral_text="#D4CCC1",
        preview=("#1D1A18", "#2B2622", "#D3AE75"),
    ),
    "emerald_forest": ThemePalette(
        name="Emerald Forest",
        description="Тёмный хвойный графит и спокойный изумруд.",
        window="#171D1B",
        panel="#242C29",
        panel_alt="#1F2623",
        border="#313B36",
        text="#EEF3F0",
        muted="#9DAAA3",
        accent="#83B99A",
        accent_text="#17231C",
        hover="#303B35",
        selected="#35483D",
        selected_text="#EEF3F0",
        input="#242C29",
        board_light="#D2D7C9",
        board_dark="#687D70",
        board_selected="#83B99A",
        board_last_move="#8EA986",
        board_check="#A64D55",
        board_check_pulse="#C26369",
        piece_white="#F4F7F0",
        piece_black="#17201B",
        win_background="#294537",
        win_text="#A9D1B8",
        loss_background="#453337",
        loss_text="#D5B0B5",
        neutral_background="#333D38",
        neutral_text="#C7D1CB",
        preview=("#171D1B", "#242C29", "#83B99A"),
    ),
}


class ThemeManager(QObject):
    theme_changed = Signal(str)
    SETTINGS_KEY = "appearance/theme"
    DEFAULT_THEME = "graphite"

    def __init__(
        self,
        application: QApplication,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.application = application
        self.settings = settings if settings is not None else QSettings()
        requested_theme = self.settings.value(self.SETTINGS_KEY, self.DEFAULT_THEME)
        self.current_theme = (
            requested_theme if requested_theme in THEMES else self.DEFAULT_THEME
        )
        self.apply_theme(self.current_theme, persist=False, emit_signal=False)

    @property
    def available_themes(self) -> dict[str, ThemePalette]:
        return THEMES.copy()

    @property
    def palette(self) -> ThemePalette:
        return THEMES[self.current_theme]

    def set_theme(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            raise ValueError(f"Неизвестная цветовая тема: {theme_id}")
        self.apply_theme(theme_id)

    def apply_theme(
        self,
        theme_id: str,
        *,
        persist: bool = True,
        emit_signal: bool = True,
    ) -> None:
        palette = THEMES[theme_id]
        self.current_theme = theme_id
        self.application.setStyleSheet(self._stylesheet(palette))
        if persist:
            self.settings.setValue(self.SETTINGS_KEY, theme_id)
            self.settings.sync()
        if emit_signal:
            self.theme_changed.emit(theme_id)

    @staticmethod
    def _stylesheet(palette: ThemePalette) -> str:
        return f"""
        QWidget {{
            color: {palette.text};
            font-family: "Segoe UI";
            font-size: 14px;
        }}
        QMainWindow, QDialog, QMessageBox {{
            background-color: {palette.window};
            color: {palette.text};
        }}
        QWidget#centralPages, QWidget#placeholderPage, QWidget#analysisPage,
        QWidget#analysisContent,
        QWidget#myGamesPage, QWidget#settingsPage {{
            background-color: {palette.window};
        }}
        QScrollArea#analysisScroll {{
            background-color: {palette.window};
            border: none;
        }}
        QFrame#navigation {{
            background-color: {palette.panel};
            border-right: 1px solid {palette.border};
        }}
        QPushButton {{
            min-height: 38px;
            border: none;
            border-radius: 8px;
            background-color: {palette.hover};
            color: {palette.text};
            padding: 0 14px;
        }}
        QPushButton:hover {{
            background-color: {palette.selected};
        }}
        QPushButton:pressed, QPushButton:checked {{
            background-color: {palette.accent};
            color: {palette.accent_text};
        }}
        QPushButton:disabled {{
            background-color: {palette.panel_alt};
            color: {palette.muted};
        }}
        QPushButton#historyButton {{
            min-height: 38px;
            border: none;
            border-radius: 8px;
            background-color: {palette.hover};
            color: {palette.text};
            padding: 0 14px;
        }}
        QPushButton#historyButton:hover {{
            background-color: {palette.selected};
        }}
        QPushButton#navigationButton {{
            min-height: 42px;
            background-color: transparent;
            color: {palette.muted};
            text-align: left;
        }}
        QPushButton#navigationButton:hover {{
            background-color: {palette.hover};
            color: {palette.text};
        }}
        QPushButton#navigationButton:checked {{
            background-color: {palette.accent};
            color: {palette.accent_text};
            font-weight: 600;
        }}
        QLabel#pageTitle {{
            color: {palette.text};
            font-size: 24px;
            font-weight: 600;
        }}
        QLabel#brand {{
            color: {palette.text};
            font-size: 14px;
            font-weight: 600;
        }}
        QLabel#version {{
            color: {palette.muted};
            font-size: 12px;
        }}
        QLabel#version, QLabel#gameCount, QLabel#gameDetails,
        QLabel#chessComStatus {{
            color: {palette.muted};
        }}
        QLabel#gameInfo, QFrame#chessComImportPanel, QFrame#stockfishPanel,
        QFrame#gameCard, QFrame#themeCard {{
            background-color: {palette.panel};
            color: {palette.text};
            border: 1px solid {palette.border};
            border-radius: 10px;
        }}
        QFrame#chessComImportPanel {{
            background-color: {palette.panel_alt};
        }}
        QFrame#gameCard[selected="true"], QFrame#themeCard[selected="true"] {{
            background-color: {palette.selected};
            border: 1px solid {palette.accent};
        }}
        QLabel#themeDescription {{
            color: {palette.muted};
        }}
        QLabel#themeName {{
            color: {palette.text};
            font-weight: 600;
        }}
        QLabel#settingsSectionTitle {{
            color: {palette.text};
            font-size: 18px;
            font-weight: 600;
        }}
        QLabel#gameCount {{
            color: {palette.muted};
            font-size: 13px;
            padding-left: 8px;
        }}
        QLabel#gamePlayers {{
            color: {palette.text};
            font-size: 16px;
            font-weight: 600;
        }}
        QLabel#gameDetails, QLabel#chessComStatus {{
            color: {palette.muted};
            font-size: 12px;
        }}
        QLabel#stockfishTitle {{
            color: {palette.text};
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#stockfishStatus {{
            color: {palette.muted};
            font-size: 12px;
        }}
        QLabel#stockfishResult {{
            color: {palette.text};
            font-size: 13px;
        }}
        QLabel#stockfishEvaluation {{
            color: {palette.accent};
            font-size: 28px;
            font-weight: 700;
            padding: 6px 0;
        }}
        QLabel#stockfishBestMove {{
            color: {palette.text};
            font-size: 18px;
            font-weight: 600;
            padding: 4px 0;
        }}
        QLabel#stockfishStatus {{
            background-color: {palette.panel_alt};
            border-radius: 6px;
            padding: 8px 10px;
        }}
        QLabel#boardTurn {{
            color: {palette.muted};
            font-size: 12px;
            padding-left: 6px;
        }}
        QLabel#boardCoordinate {{
            color: {palette.muted};
            font-size: 12px;
            font-weight: 600;
        }}
        QWidget#boardContainer {{
            background-color: {palette.panel_alt};
            border: 1px solid {palette.border};
            border-radius: 6px;
        }}
        QLabel#gameOutcome {{
            border-radius: 10px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#gameOutcome[outcome="white_wins"] {{
            background-color: {palette.win_background};
            color: {palette.win_text};
        }}
        QLabel#gameOutcome[outcome="black_wins"] {{
            background-color: {palette.loss_background};
            color: {palette.loss_text};
        }}
        QLabel#gameOutcome[outcome="draw"], QLabel#gameOutcome[outcome="unknown"] {{
            background-color: {palette.neutral_background};
            color: {palette.neutral_text};
        }}
        QLineEdit, QComboBox, QTextEdit, QListWidget {{
            min-height: 36px;
            background-color: {palette.input};
            color: {palette.text};
            border: 1px solid {palette.border};
            border-radius: 8px;
            padding: 0 10px;
            selection-background-color: {palette.selected};
            selection-color: {palette.selected_text};
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border: 1px solid {palette.accent};
        }}
        QTextEdit#moveHistory {{
            padding: 10px 12px;
        }}
        QComboBox QAbstractItemView, QListWidget {{
            background-color: {palette.panel};
            color: {palette.text};
            selection-background-color: {palette.selected};
            selection-color: {palette.selected_text};
        }}
        QScrollArea {{
            background-color: {palette.window};
            border: none;
        }}
        QLabel#gamesMessage {{
            color: {palette.muted};
            padding: 6px 2px;
        }}
        QProgressBar {{
            background-color: {palette.border};
            border: none;
            border-radius: 2px;
        }}
        QProgressBar::chunk {{
            background-color: {palette.accent};
            border-radius: 2px;
        }}
        QLabel#historyTitle {{
            color: {palette.text};
            font-size: 16px;
            font-weight: 600;
        }}
        QLabel#gameInfo {{
            padding: 10px 12px;
        }}
        QLabel#gamesMessage {{
            color: {palette.muted};
            padding: 6px 2px;
        }}
        QPushButton[boardSquare="true"][squareTone="light"] {{
            background-color: {palette.board_light};
        }}
        QPushButton[boardSquare="true"][squareTone="dark"] {{
            background-color: {palette.board_dark};
        }}
        QPushButton[boardSquare="true"][pieceColor="white"] {{
            color: {palette.piece_white};
        }}
        QPushButton[boardSquare="true"][pieceColor="black"] {{
            color: {palette.piece_black};
        }}
        QPushButton[boardSquare="true"][selected="true"] {{
            background-color: {palette.board_selected};
        }}
        QPushButton[boardSquare="true"][lastMove="true"] {{
            background-color: {palette.board_last_move};
        }}
        QPushButton[boardSquare="true"][inCheck="true"] {{
            background-color: {palette.board_check};
        }}
        QPushButton[boardSquare="true"][inCheck="true"][checkPulse="true"] {{
            background-color: {palette.board_check_pulse};
        }}
        QPushButton[boardSquare="true"] {{
            min-width: 64px;
            max-width: 64px;
            min-height: 64px;
            max-height: 64px;
            border: none;
            border-radius: 0;
            padding: 0;
            font-family: "Segoe UI Symbol";
            font-size: 38px;
        }}
        QLabel#legalMoveMarker {{
            background-color: {palette.accent};
            border-radius: 8px;
        }}
        QLabel#legalCaptureMarker {{
            background-color: transparent;
            border: 4px solid {palette.accent};
            border-radius: 24px;
        }}
        QFrame#themePreview {{
            border: 1px solid {palette.border};
            border-radius: 6px;
        }}
        """
