# -*- coding: utf-8 -*-
"""Inverser la selection : l'element selectionne est deselectionne, tous les
autres elements selectionnables (visibles, hors partie coupee par la boite de
coupe) deviennent selectionnes. Sans selection : ne fait rien."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import viewer_widget
from test_clip_box import _viewer_stub


def _triangles_actor(indexes, x0=0.0):
    pts = vtk.vtkPoints()
    cells = vtk.vtkCellArray()
    arr = vtk.vtkIntArray()
    arr.SetName(viewer_widget.VTKViewerWidget.ELEMENT_INDEX_ARRAY)
    for k, idx in enumerate(indexes):
        base = pts.GetNumberOfPoints()
        x = x0 + 10.0 * k
        pts.InsertNextPoint(x, 0, 0)
        pts.InsertNextPoint(x + 1, 0, 0)
        pts.InsertNextPoint(x, 1, 0)
        tri = vtk.vtkTriangle()
        for j in range(3):
            tri.GetPointIds().SetId(j, base + j)
        cells.InsertNextCell(tri)
        arr.InsertNextValue(idx)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    pd.GetCellData().AddArray(arr)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def _register(w, actor, role):
    w._pickable_actors[w._actor_key(actor)] = {"actor": actor, "role": role}
    w._actors.append(actor)


def test_invert_selection_items_removes_selected_and_adds_all_others_sorted():
    universe = {("lines", 0), ("lines", 1), ("planars", 0)}
    out = viewer_widget._invert_selection_items([{"role": "lines", "index": 1}], universe)
    assert out == [{"role": "lines", "index": 0}, {"role": "planars", "index": 0}]


def test_invert_selection_items_everything_selected_gives_empty():
    universe = {("lines", 0), ("lines", 1)}
    selected = [{"role": "lines", "index": 0}, {"role": "lines", "index": 1}]
    assert viewer_widget._invert_selection_items(selected, universe) == []


def test_selectable_keys_cover_visible_pickable_actors_only():
    w = _viewer_stub()
    visible = _triangles_actor([0, 1, 2])
    hidden = _triangles_actor([0, 1])
    hidden.SetVisibility(0)
    _register(w, visible, "lines")
    _register(w, hidden, "planars")
    assert w._selectable_element_keys() == {("lines", 0), ("lines", 1), ("lines", 2)}


def test_selectable_keys_exclude_elements_fully_cut_by_the_clip_box():
    w = _viewer_stub()
    actor = _triangles_actor([0, 1, 2])  # triangles aux x = 0, 10, 20
    _register(w, actor, "lines")
    w._clip.activate([8.0, 12.0, -1.0, 2.0, -1.0, 1.0])   # ne garde que l'element 1
    assert w._selectable_element_keys() == {("lines", 1)}


def test_invert_selection_does_nothing_without_selection():
    w = _viewer_stub()
    _register(w, _triangles_actor([0, 1]), "lines")
    calls = []
    w.set_selected_items = lambda items: calls.append(items)
    assert w.invert_selection() is None
    assert calls == []


def test_invert_selection_replaces_selection_with_complement():
    w = _viewer_stub()
    _register(w, _triangles_actor([0, 1, 2]), "lines")
    w._selected_items = [{"role": "lines", "index": 1}]
    calls = []
    w.set_selected_items = lambda items: calls.append(items)
    result = w.invert_selection()
    expected = [{"role": "lines", "index": 0}, {"role": "lines", "index": 2}]
    assert result == expected and calls == [expected]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
