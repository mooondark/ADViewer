# -*- coding: utf-8 -*-
"""Selection par fenetre : de gauche a droite, seuls les elements entierement
dans le rectangle ; de droite a gauche, aussi ceux qu'il touche. Projection
ecran reelle (camera VTK hors ecran), boite de coupe prise en compte."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

from test_clip_box import _viewer_stub
from viewer_widget import VTKViewerWidget


def _actor(cells, kind):
    """cells : liste de (index d'element, [points])."""
    pts = vtk.vtkPoints()
    arr = vtk.vtkIntArray()
    arr.SetName(VTKViewerWidget.ELEMENT_INDEX_ARRAY)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    array = vtk.vtkCellArray()
    for index, points in cells:
        ids = [pts.InsertNextPoint(*p) for p in points]
        array.InsertNextCell(len(ids), ids)
        arr.InsertNextValue(index)
    {"polys": pd.SetPolys, "lines": pd.SetLines, "verts": pd.SetVerts}[kind](array)
    pd.GetCellData().AddArray(arr)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def _viewer():
    w = _viewer_stub()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(w.renderer)
    w._window = window
    cam = w.renderer.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetPosition(10.0, 2.0, 50.0)
    cam.SetFocalPoint(10.0, 2.0, 0.0)
    cam.SetViewUp(0.0, 1.0, 0.0)
    cam.SetParallelScale(8.0)
    window.Render()
    faces = _actor([(0, [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]),
                    (1, [(5, 0, 0), (7, 0, 0), (7, 2, 0), (5, 2, 0)])], "polys")
    bars = _actor([(0, [(10, 0, 0), (12, 0, 0)]), (0, [(12, 0, 0), (14, 0, 0)])], "lines")
    point = _actor([(3, [(16, 1, 0)])], "verts")
    hidden = _actor([(9, [(5, 0, 0), (7, 0, 0), (7, 2, 0)])], "polys")
    hidden.SetVisibility(0)
    for actor, role in ((faces, "planars"), (bars, "lines"), (point, "support_punctual"), (hidden, "load_areas")):
        w._pickable_actors[w._actor_key(actor)] = {"actor": actor, "role": role}
    w.emitted = []
    w.selectionChanged = types.SimpleNamespace(emit=lambda items: w.emitted.append(("changed", items)))
    w.windowSelectionDone = types.SimpleNamespace(emit=lambda items: w.emitted.append(("done", items)))
    w._refresh_selection_overlay = lambda: None
    return w


def _screen(w, x, y):
    coord = vtk.vtkCoordinate()
    coord.SetCoordinateSystemToWorld()
    coord.SetValue(x, y, 0.0)
    return coord.GetComputedDoubleDisplayValue(w.renderer)


def _select(w, a, b, additive=False):
    """Rectangle trace de a vers b (coordonnees monde du plan z = 0)."""
    w._window_select_from_rect(_screen(w, *a), _screen(w, *b), additive)
    return sorted((it["role"], it["index"]) for it in w._selected_items)


def test_window_left_to_right_keeps_only_fully_enclosed_elements():
    w = _viewer()
    assert _select(w, (4, -1), (8, 3)) == [("planars", 1)]
    assert _select(w, (6, -1), (17, 3)) == [("lines", 0), ("support_punctual", 3)]   # face 1 seulement touchee
    assert _select(w, (11, -1), (17, 3)) == [("support_punctual", 3)]   # barre a moitie dedans
    assert _select(w, (-1, -1), (15, 3)) == [("lines", 0), ("planars", 0), ("planars", 1)]


def test_window_right_to_left_also_takes_touched_elements():
    w = _viewer()
    assert _select(w, (17, 3), (6, -1)) == [("lines", 0), ("planars", 1), ("support_punctual", 3)]
    assert _select(w, (11, 3), (10.5, -1)) == [("lines", 0)]


def test_crossing_rectangle_inside_a_face_without_touching_its_edges_selects_nothing():
    w = _viewer()
    assert _select(w, (6.5, 1.5), (5.5, 0.5)) == []


def test_point_is_taken_only_when_inside():
    w = _viewer()
    assert _select(w, (18, 3), (16.5, -1)) == []
    assert _select(w, (18, 3), (15.5, -1)) == [("support_punctual", 3)]


def test_additive_selection_appends_without_duplicates_and_emits_both_signals():
    w = _viewer()
    _select(w, (4, -1), (8, 3))
    w.emitted.clear()
    assert _select(w, (-1, -1), (8, 3), additive=True) == [("planars", 0), ("planars", 1)]
    assert [it["index"] for it in w._selected_items] == [1, 0]   # l'ancienne selection garde sa place
    assert w._selected_item == {"role": "planars", "index": 1}
    assert [name for name, _ in w.emitted] == ["changed", "done"]


def test_clip_box_removes_cut_away_parts():
    w = _viewer()
    w._clip.activate([4.0, 6.0, -1.0, 3.0, -1.0, 1.0])   # ne garde que la moitie gauche de la face 1
    assert _select(w, (4.5, -1), (6.5, 3)) == [("planars", 1)]


def test_simple_click_picks_the_first_candidate_or_clears():
    w = _viewer()
    picked = []
    w._pick_selection_candidates = lambda x, y: [{"role": "planars", "index": 1}, {"role": "lines", "index": 0}]
    w._select_item = lambda role, index, additive=False: picked.append((role, index, additive))
    w._window_select_from_rect((100, 100), (101, 101), True)
    assert picked == [("planars", 1, True)]
    w._pick_selection_candidates = lambda x, y: []
    cleared = []
    w.clear_selection = lambda: cleared.append(True)
    w._window_select_from_rect((100, 100), (100, 101), False)
    assert cleared == [True]
    assert [name for name, _ in w.emitted] == ["done", "done"]
