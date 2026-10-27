# -*- coding: utf-8 -*-
"""
test_settings_load_width.py
Le reglage d'epaisseur des charges est une epaisseur de trait en pixels
(meme plage que les barres), sous de nouvelles cles *_load_line_width.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _settings_dialog(punctual, linear, planar):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])
    import main_window as mw
    c = (0.5, 0.5, 0.5)
    return mw.SettingsDialog(
        2.0, 2.0, 2.5, 1.8, 0.35, 2.0, 2.5, 2.5,
        c, c, c, c, c, c, c,
        3.0, c, 1.0, c,
        punctual, c, linear, c, planar, c,
        c, c, 2.0,
    )


def test_settings_load_widths_are_pixel_spins():
    dlg = _settings_dialog(1.5, 2.0, 3.0)
    assert dlg.spin_linear_load_line_width.minimum() == pytest.approx(0.1)
    assert dlg.spin_linear_load_line_width.maximum() == pytest.approx(20.0)
    v = dlg.get_values()
    assert (v["punctual_load_line_width"], v["linear_load_line_width"], v["planar_load_line_width"]) == (1.5, 2.0, 3.0)
    assert not any(k.endswith("_arrow_width") for k in v)
