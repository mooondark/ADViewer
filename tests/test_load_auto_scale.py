# -*- coding: utf-8 -*-
"""
test_load_auto_scale.py
Echelle automatique des charges : la plus forte charge de chaque type mesure
une fraction de la taille du modele ; sinon l'echelle manuelle (m) s'applique.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_config import AUTO_LOAD_SCALE_RATIO
from viewer_widget import VTKViewerWidget


def _widget(lines=(), planars=()):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._model_data = {"lines": list(lines), "planars": list(planars)}
    w.punctual_load_scale = 1.0
    w.linear_load_scale = 2.5
    w.planar_load_scale = 1.0
    w.load_auto_scale = True
    w._update_model_extent()
    return w


def test_extent_is_largest_dimension_of_lines_and_planars():
    w = _widget(lines=[((0, 0, 0), (11, 0, 0)), ((0, 0, 0), (0, 0, 5))],
                planars=[{"outer": [(0, 0, 5), (11, 0, 5), (11, 20, 5)]}])
    assert w._model_extent == pytest.approx(20.0)


def test_auto_scale_is_ratio_of_model_size():
    w = _widget(lines=[((0, 0, 0), (11, 0, 0))])
    assert w.effective_load_scale("linear") == pytest.approx(AUTO_LOAD_SCALE_RATIO * 11.0)
    assert w.effective_load_scale("punctual") == w.effective_load_scale("planar")


def test_manual_scale_when_auto_disabled():
    w = _widget(lines=[((0, 0, 0), (11, 0, 0))])
    w.load_auto_scale = False
    assert w.effective_load_scale("linear") == pytest.approx(2.5)


def test_empty_model_falls_back_to_manual_scale():
    w = _widget()
    assert w.effective_load_scale("linear") == pytest.approx(2.5)
