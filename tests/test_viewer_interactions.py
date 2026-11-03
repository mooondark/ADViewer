# -*- coding: utf-8 -*-
"""Interactions de la vue 3D : selection (clic, Ctrl, Tab), Echap, clic droit,
rectangle de selection, cadrages, projection, orbite et panoramique."""

import math
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

from viewer_widget import ConstrainedOrbitStyle, VTKViewerWidget


def _viewer():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    log = []
    w.log = log
    w._selected_items = []
    w._selected_item = None
    w._selection_candidates = []
    w._selection_candidate_keys = []
    w._selection_cycle_index = -1
    w._window_select_mode = False
    w._zoom_window_mode = False
    w._win_pt1 = None
    w._zoom_win_pt1 = None
    w._flight = types.SimpleNamespace(active=False, on_key_press=lambda k: log.append(("flight key", k)),
                                      on_right_button_press=lambda: log.append("flight look"))
    w.interactor = types.SimpleNamespace(GetEventPosition=lambda: (40, 30), GetKeySym=lambda: "Escape")
    w.selectionChanged = types.SimpleNamespace(emit=lambda items: log.append(("changed", [(i["role"], i["index"]) for i in items])))
    w.contextMenuRequested = types.SimpleNamespace(emit=lambda: log.append("menu"))
    w.vtk_widget = types.SimpleNamespace(setFocus=lambda: log.append("focus"))
    w._refresh_selection_overlay = lambda: log.append("overlay")
    w.set_window_select_mode = lambda active: log.append(("select mode", active))
    w.set_zoom_window_mode = lambda active: log.append(("zoom mode", active))
    w.clear_selection = lambda: log.append("clear")
    return w


def _keys(w):
    return [(i["role"], i["index"]) for i in w._selected_items]


def test_click_replaces_and_ctrl_click_toggles_the_selection():
    w = _viewer()
    assert w._select_item("lines", "2") is True
    w._select_item("planars", 0, additive=True)
    assert _keys(w) == [("lines", 2), ("planars", 0)] and w._selected_item == {"role": "lines", "index": 2}
    w._select_item("lines", 2, additive=True)
    assert _keys(w) == [("planars", 0)] and w._selected_item == {"role": "planars", "index": 0}
    w._select_item("planars", 0, additive=True)
    assert _keys(w) == [] and w._selected_item is None
    assert w.log.count("overlay") == 4 and w.log[-2] == ("changed", [])


def test_selecting_an_anomaly_delegates_to_the_anomaly_selection():
    w = _viewer()
    w.select_anomaly = lambda index: ("anomaly", index)
    assert w._select_item("anomaly", "3") == ("anomaly", 3)
    assert w._selected_items == []


def test_tab_cycles_through_the_elements_under_the_cursor():
    w = _viewer()
    candidates = [{"role": "lines", "index": 1}, {"role": "planars", "index": 4}]
    w._pick_selection_candidates = lambda x, y: list(candidates)
    w._cycle_selection()
    assert _keys(w) == [("lines", 1)]
    w._cycle_selection()
    assert _keys(w) == [("planars", 4)]
    w._cycle_selection()
    assert _keys(w) == [("lines", 1)]
    candidates.reverse()
    w._cycle_selection()   # autres elements sous le curseur : on repart du premier
    assert _keys(w) == [("planars", 4)]
    w._cycle_selection(additive=True)   # Ctrl+Tab repart du premier candidat, deja selectionne : il est retire
    assert _keys(w) == []


def test_tab_does_nothing_in_rectangle_modes_or_on_empty_space():
    w = _viewer()
    w._pick_selection_candidates = lambda x, y: []
    w._cycle_selection()
    w._window_select_mode = True
    w._pick_selection_candidates = lambda x, y: pytest.fail("pas de picking en mode fenetre")
    w._cycle_selection()
    assert w._selected_items == []


def test_escape_cancels_the_rectangle_mode_first_then_clears_the_selection():
    w = _viewer()
    w._window_select_mode = True
    w._on_key_press(None, None)
    w._window_select_mode, w._zoom_window_mode = False, True
    w._on_key_press(None, None)
    w._zoom_window_mode = False
    w._on_key_press(None, None)
    assert w.log == [("select mode", False), ("zoom mode", False), "clear"]
    w.log.clear()
    w._flight.active = True
    w._on_key_press(None, None)
    assert w.log == [("flight key", "Escape")]


def test_right_click_cancels_a_mode_or_opens_the_context_menu():
    w = _viewer()
    w._on_right_button_press(None, None)
    assert w.log == ["focus", "menu"]
    for attr, expected in (("_window_select_mode", ("select mode", False)), ("_zoom_window_mode", ("zoom mode", False))):
        w.log.clear()
        setattr(w, attr, True)
        w._on_right_button_press(None, None)
        assert w.log == [expected]
        setattr(w, attr, False)
    w.log.clear()
    w._flight.active = True
    w._on_right_button_press(None, None)
    assert w.log == ["flight look"]


def test_rectangle_follows_the_mouse_from_the_first_point_of_the_active_mode():
    w = _viewer()
    drawn = []
    w._update_window_rect = lambda p0, p1: drawn.append((p0, p1))
    w._on_window_select_mouse_move(None, None)
    w._window_select_mode = True
    w._on_window_select_mouse_move(None, None)   # premier point pas encore pose
    w._win_pt1 = (5, 5)
    w._on_window_select_mouse_move(None, None)
    w._window_select_mode, w._zoom_window_mode, w._zoom_win_pt1 = False, True, (1, 2)
    w._on_window_select_mouse_move(None, None)
    assert drawn == [((5, 5), (40, 30)), ((1, 2), (40, 30))]


def _bounded_actor(bounds):
    src = vtk.vtkCubeSource()
    src.SetBounds(*bounds)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def test_zoom_to_selection_frames_the_union_of_the_selection_overlays():
    w = _viewer()
    framed = []
    w.focus_bounds = framed.append
    w._selection_overlay_actors = []
    w.zoom_to_selection()
    w._selection_overlay_actors = [_bounded_actor((0, 1, 0, 1, 0, 1)), _bounded_actor((2, 5, -1, 0, 3, 4))]
    w.zoom_to_selection()
    assert framed == [[0, 5, -1, 1, 0, 4]]


def _camera_viewer():
    w = _viewer()
    w.renderer = vtk.vtkRenderer()
    renders = []
    w.render_window = types.SimpleNamespace(Render=lambda: renders.append(1))
    w.renders = renders
    return w


@pytest.mark.parametrize("mode, parallel, stored", [
    ("Orthogonal", 1, "orthogonal"), ("perspective", 0, "perspective"), ("autre", None, None),
])
def test_projection_mode_is_normalised(mode, parallel, stored):
    import viewer_widget

    w = _camera_viewer()
    w.set_projection_mode(mode)
    expected = stored or viewer_widget.DEFAULT_VIEW_PROJECTION
    assert w._projection_mode == expected
    assert w.renderer.GetActiveCamera().GetParallelProjection() == int(expected == "orthogonal")
    assert w.renders == [1]


def test_fit_view_fixes_a_view_up_parallel_to_the_view_direction():
    w = _camera_viewer()
    framed = []
    w._reset_camera_to_framing = lambda: framed.append(1)
    w._update_view_overlay = lambda: w.log.append("view overlay")
    cam = w.renderer.GetActiveCamera()
    cam.SetPosition(0, 0, 10)
    cam.SetFocalPoint(0, 0, 0)
    cam.SetViewUp(0, 0, 1)   # vue de dessus, "haut" degenere
    w.fit_view()
    assert cam.GetViewUp() == pytest.approx((0, 1, 0))
    cam.SetPosition(10, 0, 0)
    cam.SetViewUp(1, 0, 0)   # vue laterale degeneree
    w.fit_view()
    assert cam.GetViewUp() == pytest.approx((0, 0, 1))
    assert framed == [1, 1] and w.renders == [1, 1] and w.log.count("view overlay") == 2


def _orbit_style():
    style = ConstrainedOrbitStyle()
    renderer = vtk.vtkRenderer()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(renderer)
    renders = []
    style._renderer = lambda: renderer
    style._interactor = lambda: types.SimpleNamespace(Render=lambda: renders.append(1), GetEventPosition=lambda: (110, 90))
    cam = renderer.GetActiveCamera()
    cam.SetFocalPoint(0, 0, 0)
    cam.SetPosition(10, 0, 0)
    cam.SetViewUp(0, 0, 1)
    window.Render()
    style._window = window
    return style, cam, renders


def test_orbit_turns_around_the_focal_point_and_clamps_the_elevation():
    style, cam, renders = _orbit_style()
    style._orbit(-100, 0)   # 100 px * 0.35 deg vers la gauche
    x, y, z = cam.GetPosition()
    assert math.hypot(x, y) == pytest.approx(10.0)
    assert math.degrees(math.atan2(y, x)) == pytest.approx(35.0)
    assert cam.GetFocalPoint() == pytest.approx((0, 0, 0))
    style._orbit(0, -1000)   # tres haut : limite a 85 degres
    x, y, z = cam.GetPosition()
    assert math.degrees(math.atan2(z, math.hypot(x, y))) == pytest.approx(85.0)
    assert renders == [1, 1]


def test_pan_moves_position_and_focal_point_together():
    style, cam, renders = _orbit_style()
    before = (cam.GetPosition(), cam.GetFocalPoint())
    style._pan(120, 100, 100, 100)
    shift = [p - q for p, q in zip(cam.GetFocalPoint(), before[1])]
    assert shift == pytest.approx([p - q for p, q in zip(cam.GetPosition(), before[0])])
    assert abs(shift[1]) > 0 and shift[0] == pytest.approx(0, abs=1e-9)   # glisse dans le plan de vue
    assert renders == [1]


def test_mouse_move_dispatches_to_the_current_mode():
    style, cam, renders = _orbit_style()
    calls = []
    style._orbit = lambda dx, dy: calls.append(("orbit", dx, dy))
    style._pan = lambda x, y, lx, ly: calls.append(("pan", x, y, lx, ly))
    style._mode = None
    style._on_mouse_move(None, None)
    style._mode, style._last_pos = "orbit", (100, 100)
    style._on_mouse_move(None, None)
    style._mode = "pan"
    style._on_mouse_move(None, None)
    assert calls == [("orbit", 10, -10), ("pan", 110, 90, 110, 90)]
    assert style._last_pos == (110, 90)
