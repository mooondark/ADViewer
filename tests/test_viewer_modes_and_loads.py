# -*- coding: utf-8 -*-
"""Reconstruction des acteurs de charges, modes "selection par fenetre" et
"zoom fenetre" (exclusifs), reglages de transparence."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_structural_visibility import _viewer as _loads_viewer
from viewer_widget import VTKViewerWidget


@pytest.mark.parametrize("kind", ["punctual", "linear", "planar"])
def test_rebuild_load_actors_draws_all_loads_with_the_case_filter(kind):
    w = _loads_viewer()
    renders = []
    w.render_window = types.SimpleNamespace(Render=lambda: renders.append(1))
    setattr(w, f"_{kind}_load_case_filter", {1, 2})
    getattr(VTKViewerWidget, f"_rebuild_{kind}_load_actors")(w)
    data = getattr(w, f"_{kind}_load_data")
    assert w.log.removed == [f"old-{kind}"]
    assert w.log.loads == {kind: ([ld["id"] for ld in data], {1, 2}, kind != "punctual")}
    assert getattr(w, f"_{kind}_load_actors") == [(kind, ld["id"]) for ld in data]
    assert w.log.added == [(f"{kind}_load", (kind, ld["id"])) for ld in data]
    assert renders == [1]


@pytest.mark.parametrize("kind", ["punctual", "linear", "planar"])
def test_rebuild_load_actors_only_clears_when_hidden_or_empty(kind):
    for hide in (True, False):
        w = _loads_viewer()
        renders = []
        w.render_window = types.SimpleNamespace(Render=lambda: renders.append(1))
        if hide:
            setattr(w, f"_show_{kind}_loads", False)
        else:
            setattr(w, f"_{kind}_load_data", [])
        getattr(VTKViewerWidget, f"_rebuild_{kind}_load_actors")(w)
        assert w.log.removed == [f"old-{kind}"]
        assert w.log.loads == {} and getattr(w, f"_{kind}_load_actors") == []
        assert renders == [1]


def _modes_viewer():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    log = []
    w.log = log
    w._window_select_mode = False
    w._zoom_window_mode = False
    w._win_pt1 = w._zoom_win_pt1 = (1, 1)
    w._flight = types.SimpleNamespace(active=False)
    w.set_flight_mode = lambda active: (log.append(("flight", active)), setattr(w._flight, "active", active))
    w.interactor_style = "orbit"
    w._ensure_plain_style = lambda: "plain"
    w.interactor = types.SimpleNamespace(SetInteractorStyle=lambda style: log.append(("style", style)))
    w.vtk_widget = types.SimpleNamespace(setCursor=lambda c: log.append("cross"), unsetCursor=lambda: log.append("arrow"))
    w._hide_window_rect = lambda: log.append("hide rect")
    w.windowSelectModeChanged = types.SimpleNamespace(emit=lambda a: log.append(("select", a)))
    w.zoomWindowModeChanged = types.SimpleNamespace(emit=lambda a: log.append(("zoom", a)))
    return w


def test_window_select_and_zoom_window_modes_exclude_each_other_and_flight():
    w = _modes_viewer()
    w._flight.active = True
    w.set_window_select_mode(1)
    assert w._window_select_mode is True and w._win_pt1 is None
    assert w.log == [("flight", False), ("style", "plain"), "cross", ("select", True)]
    w.log.clear()
    w.set_window_select_mode(True)
    assert w.log == []
    w.set_zoom_window_mode(True)
    assert w._zoom_window_mode is True and w._window_select_mode is False and w._zoom_win_pt1 is None
    assert w.log == [("style", "orbit"), "arrow", "hide rect", ("select", False), ("style", "plain"), "cross", ("zoom", True)]
    w.log.clear()
    w.set_window_select_mode(True)
    assert w.log == [("style", "orbit"), "arrow", "hide rect", ("zoom", False), ("style", "plain"), "cross", ("select", True)]
    w.log.clear()
    w.set_window_select_mode(False)
    assert w.log == [("style", "orbit"), "arrow", "hide rect", ("select", False)]


@pytest.mark.parametrize("setter, attr", [("set_faces_transparency", "_transparency_percent"),
                                          ("set_profiles_transparency", "_profiles_transparency_percent")])
def test_transparency_setters_clamp_apply_and_render(setter, attr):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    calls = []
    w._apply_face_opacity_state = lambda: calls.append("apply")
    w.render_window = types.SimpleNamespace(Render=lambda: calls.append("render"))
    for value, expected in ((150, 100), (-5, 0), ("42", 42)):
        getattr(w, setter)(value)
        assert getattr(w, attr) == expected
    assert calls == ["apply", "render"] * 3
