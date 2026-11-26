from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.pages import ThemeSettingsPage
from app.ui.theme_manager import THEMES, ThemeManager


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    config = QSettings(str(tmp_path / "theme.ini"), QSettings.Format.IniFormat)
    config.clear()
    return config


def test_all_four_themes_are_available(
    qapp: QApplication,
    settings: QSettings,
) -> None:
    manager = ThemeManager(qapp, settings)

    assert set(manager.available_themes) == {
        "graphite",
        "violet_night",
        "amber_ember",
        "emerald_forest",
    }
    assert set(manager.available_themes) == set(THEMES)
    assert manager.current_theme == "graphite"


def test_selected_theme_is_persisted_and_restored(
    qapp: QApplication,
    settings: QSettings,
) -> None:
    first_manager = ThemeManager(qapp, settings)
    first_manager.set_theme("amber_ember")

    restored_manager = ThemeManager(qapp, QSettings(settings.fileName(), QSettings.Format.IniFormat))

    assert restored_manager.current_theme == "amber_ember"
    assert restored_manager.palette.name == "Amber Ember"


def test_theme_selection_updates_styles_and_settings_page_immediately(
    qapp: QApplication,
    settings: QSettings,
) -> None:
    manager = ThemeManager(qapp, settings)
    page = ThemeSettingsPage(manager)
    graphite_stylesheet = qapp.styleSheet()

    page.theme_cards["violet_night"].clicked.emit("violet_night")

    assert manager.current_theme == "violet_night"
    assert qapp.styleSheet() != graphite_stylesheet
    assert "#B7A6CF" in qapp.styleSheet()
    assert page.theme_cards["violet_night"].property("selected") is True
    assert page.theme_cards["graphite"].property("selected") is False
