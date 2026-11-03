# -*- coding: utf-8 -*-
"""Controleurs de la vue 3D : glisser des poignees de la boite de coupe, theme
et nettoyage de la minicarte, entree / sortie du mode Navigation."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

from flight_navigation import FlightController
from minimap import MinimapController
from test_clip_box import _controller_with_camera


# --- Boite de coupe ------------------------------------------------------------

def _display(renderer, point):
    coord = vtk.vtkCoordinate()
    coord.SetCoordinateSystemToWorld()
    coord.SetValue(*point)
    return coord.GetComputedDoubleDisplayValue(renderer)


def _front_view():
    # Vue de face (depuis -y) : x vers la droite, z vers le haut
    return _controller_with_camera((5, -50, 5), (5, 5, 5), up=(0, 0, 1))


def test_dragging_a_face_handle_moves_only_that_face_under_the_mouse():
    host, ctrl = _front_view()
    before = list(ctrl.box)   # boite du modele avec sa marge
    start = ctrl._screen_points()[1]   # face x max
    assert ctrl.on_left_press(*start) is True
    assert ctrl.on_mouse_move(*_display(host.renderer, (12, 5, 5))) is True
    assert ctrl.box[1] == pytest.approx(12.0, abs=1e-6)
    assert ctrl.box[0] == before[0] and ctrl.box[2:] == before[2:]
    assert ctrl.on_left_release() is True
    assert ctrl.on_left_release() is False


def test_dragging_the_center_handle_moves_the_whole_box_in_the_view_plane():
    host, ctrl = _front_view()
    before = list(ctrl.box)
    start = ctrl._screen_points()["center"]   # en (5, 5, 5)
    assert ctrl.on_left_press(*start) is True
    ctrl.on_mouse_move(*_display(host.renderer, (7, 5, 6)))
    delta = (2, 2, 0, 0, 1, 1)
    assert ctrl.box == pytest.approx([b + d for b, d in zip(before, delta)], abs=1e-6)


def test_press_outside_handles_or_while_another_mode_is_active_does_nothing():
    host, ctrl = _front_view()
    assert ctrl.on_left_press(1, 1) is False
    host._window_select_mode = True
    assert ctrl.on_left_press(*ctrl._screen_points()[1]) is False
    assert ctrl._drag is None


# --- Minicarte -------------------------------------------------------------------

_MINIMAP_ACTORS = ("lines_actor", "planar_actor", "planar_faces_actor", "support_punctual_actor",
                   "support_linear_actor", "support_planar_actor", "support_planar_faces_actor")


def _minimap():
    mm = MinimapController(types.SimpleNamespace())
    mm.renderer = vtk.vtkRenderer()
    for attr in _MINIMAP_ACTORS + ("frame_actor", "backdrop_actor"):
        actor = vtk.vtkActor()
        setattr(mm, attr, actor)
        mm.renderer.AddActor(actor)
    return mm


def test_minimap_theme_colors_geometry_and_follows_the_view_background():
    import viewer_config

    mm = _minimap()
    mm.planar_actor = None
    mm.apply_theme((0.2, 0.4, 0.6))
    for attr in _MINIMAP_ACTORS + ("frame_actor",):
        if getattr(mm, attr) is not None:
            assert getattr(mm, attr).GetProperty().GetColor() == pytest.approx((0.2, 0.4, 0.6))
    assert mm.renderer.GetBackground() == pytest.approx(tuple(viewer_config.VTK_BG))
    assert mm.backdrop_actor.GetProperty().GetColor() == pytest.approx(tuple(viewer_config.VTK_BG))


def test_minimap_clear_geometry_removes_model_actors_only():
    mm = _minimap()
    mm.clear_geometry()
    assert all(getattr(mm, attr) is None for attr in _MINIMAP_ACTORS)
    assert mm.renderer.GetActors().GetNumberOfItems() == 2   # cadre et fond conserves


def test_minimap_viewport_refits_and_renders_only_when_visible():
    renders, fits, viewports = [], [], []
    host = types.SimpleNamespace(width=lambda: 0, height=lambda: 300,
                                 render_window=types.SimpleNamespace(Render=lambda: renders.append(1)))
    mm = MinimapController(host)
    mm.update_viewport()   # pas encore de renderer : rien
    mm.renderer = vtk.vtkRenderer()
    mm._apply_viewport = lambda w, h: viewports.append((w, h))
    mm._fit_camera_to_model = lambda: fits.append(1)
    mm.update_viewport()
    assert viewports == [(1, 300)] and fits == [] and renders == []
    mm.visible = True
    mm._last_camera_mtime = 42
    mm.update_viewport()
    assert fits == [1] and renders == [1] and mm._last_camera_mtime == -1


# --- Mode Navigation ---------------------------------------------------------------

def _flight_host(bounds=(0, 10, 0, 10, 0, 10)):
    log = []
    renderer = vtk.vtkRenderer()
    camera = renderer.GetActiveCamera()
    camera.ParallelProjectionOn()
    camera.SetPosition(5, -20, 5)
    camera.SetFocalPoint(5, 5, 5)
    host = types.SimpleNamespace(
        log=log, renderer=renderer, render_window=None, interactor_style="orbit",
        _window_select_mode=True, _zoom_window_mode=True,
        set_window_select_mode=lambda a: log.append(("select", a)),
        set_zoom_window_mode=lambda a: log.append(("zoom", a)),
        _get_visible_bounds=lambda: bounds,
        _ensure_plain_style=lambda: "plain",
        interactor=types.SimpleNamespace(SetInteractorStyle=lambda s: log.append(("style", s))),
        vtk_widget=types.SimpleNamespace(setFocus=lambda: log.append("focus")),
        _update_view_overlay=lambda render=True: log.append(("overlay", render)),
    )
    return host


def _flight(host):
    flight = FlightController(host)
    flight.timer = types.SimpleNamespace(start=lambda: host.log.append("timer start"),
                                         stop=lambda: host.log.append("timer stop"))
    return flight


def test_flight_activation_switches_to_free_perspective_camera_and_back():
    host = _flight_host()
    camera = host.renderer.GetActiveCamera()
    flight = _flight(host)
    flight.activate()
    assert flight.active and camera.GetParallelProjection() == 0
    assert ("select", False) in host.log and ("zoom", False) in host.log
    assert ("style", "plain") in host.log and "focus" in host.log and host.log[-1] == "timer start"
    assert flight.key_bindings and flight.keys_held == set()
    host.log.clear()
    flight.activate()
    assert host.log == []

    camera.SetPosition(1, 2, 3)
    flight.deactivate()
    assert not flight.active and camera.GetParallelProjection() == 1
    assert camera.GetPosition() == pytest.approx((1, 2, 3))   # on reste ou l'on est
    assert host.log[:2] == ["timer stop", ("style", "orbit")] and host.log[-1] == ("overlay", True)
    host.log.clear()
    flight.deactivate()
    assert host.log == []


def test_flight_activation_inside_the_model_moves_the_camera_out_keeping_its_aim():
    host = _flight_host()
    camera = host.renderer.GetActiveCamera()
    camera.SetPosition(5, 5, 5)
    camera.SetFocalPoint(5, 8, 5)
    _flight(host).activate()
    px, py, pz = camera.GetPosition()
    fx, fy, fz = camera.GetFocalPoint()
    assert not (0 <= px <= 10 and 0 <= py <= 10 and 0 <= pz <= 10)
    assert (fx - px, fy - py, fz - pz) == pytest.approx((0, 3, 0))
