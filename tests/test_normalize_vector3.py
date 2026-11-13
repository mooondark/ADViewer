# -*- coding: utf-8 -*-
"""_normalize_vector3 (une seule definition, dans ad_model_data) et le repere local d'un polygone qui l'utilise."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ad_model_data import _normalize_vector3
from viewer_widget import VTKViewerWidget


def test_normalizes_to_a_unit_vector():
    assert _normalize_vector3((0.0, 3.0, 4.0)) == pytest.approx((0.0, 0.6, 0.8))
    assert math.isclose(math.sqrt(sum(c * c for c in _normalize_vector3([2, -3, 6]))), 1.0)


@pytest.mark.parametrize("bad", [(0, 0, 0), (1e-13, 0, 0), (1, 2), "abc", None, ("a", 1, 2)])
def test_returns_none_for_a_null_or_unreadable_vector(bad):
    assert _normalize_vector3(bad) is None


def _frame(outer):
    return VTKViewerWidget.__new__(VTKViewerWidget)._polygon_local_frame(outer)


def test_polygon_local_frame_of_a_square_in_the_xy_plane():
    normal, u, v = _frame([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    assert normal == pytest.approx((0, 0, 1)) and u == pytest.approx((1, 0, 0)) and v == pytest.approx((0, 1, 0))


def test_polygon_local_frame_falls_back_when_the_contour_is_degenerate():
    normal, u, v = _frame([(0, 0, 0), (0, 0, 0), (0, 0, 0)])
    assert normal == (0.0, 0.0, 1.0) and u == pytest.approx((1, 0, 0)) and v == pytest.approx((0, 1, 0))
