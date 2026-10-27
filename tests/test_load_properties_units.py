# -*- coding: utf-8 -*-
"""
test_load_properties_units.py
Les proprietes des charges (stockees en kN, kN.m) suivent les unites et
decimales reglees dans la boite de dialogue Unites.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PySide6")

import display_units
import main_window as mw


@pytest.fixture(autouse=True)
def _reset_units():
    display_units.reset()
    yield
    display_units.reset()


def test_default_units_unchanged():
    assert mw._load_value_text(-1.5, "force") == "-1.50 kN"
    assert mw._load_value_text(2.0, "moment", "/m") == "2.00 kN.m/m"


def test_force_follows_unit_and_decimals():
    display_units.set_unit("force", "daN")
    display_units.set_decimals("force", 1)
    assert mw._load_value_text(-1.5, "force", "/m") == "-150.0 daN/m"


def test_moment_follows_unit():
    display_units.set_unit("moment", "N.m")
    assert mw._load_value_text(0.25, "moment") == "250.00 N.m"
