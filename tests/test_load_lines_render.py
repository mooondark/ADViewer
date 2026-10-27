# -*- coding: utf-8 -*-
"""
test_load_lines_render.py
Charges dessinees en lignes dans VTKViewerWidget : uniquement des lignes,
index global de la charge sur chaque segment (selection), normalisation.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget


def _widget():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._punctual_load_data = []
    w._linear_load_data = []
    w._planar_load_data = []
    return w


def _ids(pd):
    arr = pd.GetCellData().GetArray(VTKViewerWidget.ELEMENT_INDEX_ARRAY)
    return {int(arr.GetTuple1(i)) for i in range(pd.GetNumberOfCells())}


def _linear(fz, eid, c1=1.0, c2=1.0):
    return {"pt_start": (0, 0, 0), "pt_end": (4, 0, 0), "fx": 0.0, "fy": 0.0, "fz": fz,
            "mx": 0.0, "my": 0.0, "mz": 0.0, "coeff1": c1, "coeff2": c2, "load_case_eid": eid}


def test_linear_lines_only_and_global_index_under_case_filter():
    w = _widget()
    loads = [_linear(-1.0, 1), _linear(-2.0, 2)]
    pd = w._build_linear_load_polydata_batch(loads, 1.0, case_filter={2}, global_data=loads)["arrows"]
    assert pd.GetNumberOfPolys() == 0
    assert pd.GetNumberOfLines() == pd.GetNumberOfCells() > 0
    assert _ids(pd) == {1}


def test_linear_sign_change_flips_arrows():
    w = _widget()
    pd = w._build_linear_load_lines([_linear(-1.0, 1, 1.0, -1.0)], 1.0)
    zmin, zmax = pd.GetBounds()[4:6]
    assert zmin < 0 < zmax


def test_linear_moment_only_draws_arcs():
    w = _widget()
    ld = _linear(0.0, 1)
    ld["mx"] = 2.0
    pd = w._build_linear_load_lines([ld], 1.0)
    assert pd is not None and pd.GetNumberOfLines() == pd.GetNumberOfCells() > 0


def test_overlay_normalized_on_norm_loads():
    w = _widget()
    big, small = _linear(-10.0, 1), _linear(-5.0, 1)
    pd = w._build_linear_load_lines([small], 1.0, norm_loads=[big, small])
    assert pd.GetBounds()[5] == pytest.approx(0.5)


def test_punctual_global_index_and_moment_only():
    w = _widget()
    w._punctual_load_data = [
        {"pos": (0, 0, 0), "fx": 0.0, "fy": 0.0, "fz": -3.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
        {"pos": (2, 0, 0), "fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 1.0, "my": 0.0, "mz": 0.0},
    ]
    pd = w._build_punctual_load_polydata_batch(w._punctual_load_data, 1.0)["arrows"]
    assert pd.GetNumberOfLines() == pd.GetNumberOfCells()
    assert _ids(pd) == {0, 1}


def test_planar_returns_lines_and_fill_with_index():
    w = _widget()
    loads = [{"pts": [(0, 0, 0), (1, 0, 0), (1, 1, 0)], "fx": 0.0, "fy": 0.0, "fz": -1.0,
              "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0}]
    batch = w._build_planar_load_polydata_batch(loads, 1.0, global_data=loads)
    assert batch["arrows"].GetNumberOfLines() == batch["arrows"].GetNumberOfCells() > 0
    assert batch["fill"].GetNumberOfPolys() > 0
    assert _ids(batch["arrows"]) == {0} and _ids(batch["fill"]) == {0}
