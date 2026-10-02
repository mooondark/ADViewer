# -*- coding: utf-8 -*-
"""Boutons standards Qt (Oui / Non / Annuler / Fermer...) : traduits via le
catalogue qtbase de la langue de l'application."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication

import main_window

app = QCoreApplication.instance() or QCoreApplication(sys.argv)


def _tr(text):
    return QCoreApplication.translate("QPlatformTheme", text)


def test_french_standard_buttons_are_translated_after_install():
    translators = main_window.install_qt_translators(app, "fr")
    try:
        assert translators
        assert _tr("Cancel") == "Annuler"
        assert _tr("Close") == "Fermer"
        assert _tr("&Yes").replace("&", "") == "Oui"
        assert _tr("&No").replace("&", "") == "Non"
    finally:
        for t in translators:
            app.removeTranslator(t)
    assert _tr("Cancel") == "Cancel"


def test_english_keeps_default_button_texts():
    translators = main_window.install_qt_translators(app, "en")
    try:
        assert _tr("Cancel") == "Cancel"
        assert _tr("Close") == "Close"
    finally:
        for t in translators:
            app.removeTranslator(t)


def test_unknown_language_installs_nothing_and_does_not_fail():
    assert main_window.install_qt_translators(app, "zz") == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
