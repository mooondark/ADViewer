# -*- coding: utf-8 -*-
"""
test_load_lines.py
Geometrie des charges en lignes : fleche (tige + pointe cone fil de fer),
polyligne, arc de moment. Chaque segment porte l'index de sa charge.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from load_lines import LoadLines


def _ids(pd):
    arr = pd.GetCellData().GetArray("idx")
    return [int(arr.GetTuple1(i)) for i in range(pd.GetNumberOfCells())]


def test_empty_returns_none():
    assert LoadLines("idx").to_polydata() is None


def test_arrow_is_lines_only_with_index():
    b = LoadLines("idx")
    b.add_arrow((0, 0, 0), (0, 0, -1), 2.0, 0.12, 7)
    pd = b.to_polydata()
    assert pd.GetNumberOfLines() == pd.GetNumberOfCells() == 1 + 4 + 8
    assert set(_ids(pd)) == {7}
    xmin, xmax, ymin, ymax, zmin, zmax = pd.GetBounds()
    assert zmin == pytest.approx(-2.0) and zmax == pytest.approx(0.0)
    assert xmax - xmin == pytest.approx(2 * 0.4 * 0.12, abs=1e-6)


@pytest.mark.parametrize("d", [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)])
def test_arrow_along_axes_no_degenerate_cone(d):
    b = LoadLines("idx")
    b.add_arrow((0, 0, 0), d, 1.0, 0.12, 0)
    pd = b.to_polydata()
    assert pd.GetNumberOfCells() == 13
    pts = pd.GetPoints()
    assert all(not math.isnan(c) for i in range(pts.GetNumberOfPoints()) for c in pts.GetPoint(i))
    # cone non degenere : le cercle de base a une extension non nulle
    bounds = pd.GetBounds()
    spans = sorted(bounds[2 * k + 1] - bounds[2 * k] for k in range(3))
    assert spans[0] > 0.05 and spans[1] > 0.05


def test_short_arrow_tip_clamped_to_half_length():
    b = LoadLines("idx")
    b.add_arrow((0, 0, 0), (0, 0, 1), 0.1, 0.12, 0)
    pd = b.to_polydata()
    xmin, xmax = pd.GetBounds()[0:2]
    assert xmax - xmin == pytest.approx(2 * 0.4 * 0.05, abs=1e-6)


def test_zero_length_arrow_ignored():
    b = LoadLines("idx")
    b.add_arrow((0, 0, 0), (0, 0, 1), 0.0, 0.12, 0)
    assert b.to_polydata() is None


def test_closed_polyline():
    b = LoadLines("idx")
    b.add_polyline([(0, 0, 0), (1, 0, 0), (1, 1, 0)], 3, closed=True)
    pd = b.to_polydata()
    assert pd.GetNumberOfCells() == 3 and set(_ids(pd)) == {3}


def test_polyline_with_one_point_ignored():
    b = LoadLines("idx")
    b.add_polyline([(0, 0, 0)], 3)
    assert b.to_polydata() is None


def test_moment_arc_in_plane():
    b = LoadLines("idx")
    b.add_moment_arc((0, 0, 0), 2, 1.0, 1, 5)
    pd = b.to_polydata()
    assert pd.GetNumberOfCells() == 24 + 2 and set(_ids(pd)) == {5}
    zmin, zmax = pd.GetBounds()[4:6]
    assert zmin == pytest.approx(0.0) and zmax == pytest.approx(0.0)
