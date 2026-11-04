# -*- coding: utf-8 -*-
"""Grille sous le modele : etendue, Z minimum, alignement, visibilite."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import grid

MODEL = {
    "lines": [[(0.0, 0.0, 3.0), (10.0, 0.0, 3.0)]],
    "planars": [{"outer": [(0, 0, 2.5), (10, 0, 2.5), (10, 5, 2.5)]}],
    "load_areas": [{"outer": [(0, 0, 1.5), (4, 0, 1.5), (4, 4, 1.5)]}],
    "punctual_supports": [(0.0, 0.0, 0.0)],
    "linear_supports": [],
    "planar_supports": [],
    "punctual_loads": [(100.0, 100.0, -50.0)],
}


def test_bounds_cover_structure_only_and_min_z():
    b = grid.structural_bounds(MODEL)
    assert b[0] == 0.0 and b[1] == 10.0 and b[2] == 0.0 and b[3] == 5.0
    assert b[4] == 0.0


def test_empty_model_has_no_grid():
    assert grid.grid_base({"lines": []}, 2.0) is None


def test_base_has_margin_and_lowest_z():
    base = grid.grid_base(MODEL, 10.0)
    assert base["x"] == (-1.0, 11.0)
    assert base["z"] == 0.0


def test_lines_aligned_on_step_and_cover_extent():
    base = {"x": (-0.4, 10.2), "y": (0.0, 2.0), "z": 7.0}
    pd = grid.build_polydata(base, 1.0, 1.0, major=False)
    xs = sorted({round(pd.GetPoint(i)[0], 6) for i in range(pd.GetNumberOfPoints())})
    assert xs[0] == -1.0 and xs[-1] == 11.0
    assert all(abs(x - round(x)) < 1e-9 for x in xs)
    assert all(pd.GetPoint(i)[2] == 7.0 for i in range(pd.GetNumberOfPoints()))


def test_major_lines_every_five_steps():
    base = {"x": (0.0, 10.0), "y": (0.0, 10.0), "z": 0.0}
    major = grid.build_polydata(base, 1.0, 1.0, major=True)
    minor = grid.build_polydata(base, 1.0, 1.0, major=False)
    assert major.GetNumberOfCells() == 3 * 2   # x et y : 0, 5, 10
    assert minor.GetNumberOfCells() == 8 * 2
    assert isinstance(major, vtk.vtkPolyData)


def test_viewer_grid_fixed_after_load_and_toggles():
    from tests.test_clip_box import _viewer_stub
    w = _viewer_stub()
    w._grid_actors, w._grid_step, w._show_grid = [], (1.0, 1.0), True
    w._model_data = MODEL
    w._clip = type("C", (), {"margin_pct": 2.0})()
    w._grid_base = grid.grid_base(MODEL, 2.0)
    w._rebuild_grid()
    assert len(w._grid_actors) == 2
    before = w._grid_base
    w.set_show_grid(False)
    assert not any(a.GetVisibility() for a in w._grid_actors)
    w.set_grid_step(2.0, 5.0)
    assert w.get_grid_step() == (2.0, 5.0) and w._grid_base is before
    w._update_grid_extent({"lines": [[(0.0, 0.0, 9.0), (2.0, 0.0, 9.0)]]})
    assert w._grid_base["x"][1] < 5.0 and w._grid_base["z"] == before["z"]
    assert not any(a.GetVisibility() for a in w._grid_actors)
