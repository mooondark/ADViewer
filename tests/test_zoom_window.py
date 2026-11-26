# -*- coding: utf-8 -*-
"""Zoom fenetre : le contenu du rectangle doit remplir la vue, en orthogonal comme
en perspective, quelle que soit sa profondeur par rapport au point focal (z = 0)."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import vtk

from test_window_select_rect import _actor, _viewer

# 8 x 2 : plus large que la vue 400 x 300, la largeur fixe donc le facteur de zoom
CORNERS = ((11.0, 5.0), (19.0, 5.0), (19.0, 7.0), (11.0, 7.0))


def _zoomable(parallel, z=None):
    w = _viewer()
    w.render_window = w._window
    w.orientation_widget = None
    w._update_view_overlay = lambda: None
    if z is not None:
        w.renderer.AddActor(_actor([(0, [(x, y, z) for x, y in CORNERS])], "polys"))
    if not parallel:
        w.renderer.GetActiveCamera().ParallelProjectionOff()
    w.renderer.ResetCameraClippingRange()
    w.render_window.Render()
    return w


def _projected(w, z):
    coord = vtk.vtkCoordinate()
    coord.SetCoordinateSystemToWorld()
    points = []
    for x, y in CORNERS:
        coord.SetValue(x, y, z)
        points.append(coord.GetComputedDoubleDisplayValue(w.renderer))
    return [p[0] for p in points], [p[1] for p in points]


def _rect(w, z):
    xs, ys = _projected(w, z)
    return (min(xs), min(ys)), (max(xs), max(ys))


def _assert_framed(w, z):
    xs, ys = _projected(w, z)
    assert (min(xs) + max(xs)) / 2 == pytest.approx(200, abs=3)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(150, abs=3)
    assert max(xs) - min(xs) == pytest.approx(400, abs=6)


@pytest.mark.parametrize("parallel", [True, False], ids=["ortho", "perspective"])
@pytest.mark.parametrize("z", [0.0, 25.0, -50.0])
def test_zoom_window_frames_the_geometry_at_any_depth(parallel, z):
    w = _zoomable(parallel, z)
    w._zoom_to_rect(*_rect(w, z))
    _assert_framed(w, z)


def test_zoom_window_ignores_the_depth_written_by_2d_overlays():
    w = _zoomable(False, 25.0)
    (x0, y0), (x1, y1) = _rect(w, 25.0)
    cover = x0 + 0.7 * (x1 - x0)   # surcouche 2D (profondeur 0) sur 70 % du rectangle
    points = vtk.vtkPoints()
    for x, y in ((x0, y0), (cover, y0), (cover, y1), (x0, y1)):
        points.InsertNextPoint(x, y, 0)
    quad = vtk.vtkCellArray()
    quad.InsertNextCell(4, [0, 1, 2, 3])
    data = vtk.vtkPolyData()
    data.SetPoints(points)
    data.SetPolys(quad)
    mapper = vtk.vtkPolyDataMapper2D()
    mapper.SetInputData(data)
    overlay = vtk.vtkActor2D()
    overlay.SetMapper(mapper)
    w.renderer.AddViewProp(overlay)
    w.render_window.Render()
    w._zoom_to_rect((x0, y0), (x1, y1))
    _assert_framed(w, 25.0)


def test_zoom_window_inside_a_translucent_face_uses_its_depth():
    """Une face translucide n'ecrit pas dans le tampon de profondeur (dalle, voile)."""
    w = _zoomable(False)
    z = 25.0
    slab = _actor([(0, [(5.0, 0.0, z), (25.0, 0.0, z), (25.0, 12.0, z), (5.0, 12.0, z)])], "polys")
    slab.GetProperty().SetOpacity(0.3)
    w.renderer.AddActor(slab)
    w._pickable_actors = {w._actor_key(slab): {"actor": slab, "role": "planars"}}
    w.renderer.ResetCameraClippingRange()
    w.render_window.Render()
    rect = _rect(w, z)
    assert w._rect_depth(*rect[0], *rect[1]) is None
    w._zoom_to_rect(*rect)
    _assert_framed(w, z)


def test_rect_depth_ignores_the_corner_axes_viewport():
    w = _zoomable(False, 25.0)
    (x0, y0), (x1, y1) = _rect(w, 25.0)
    assert 0.0 < w._rect_depth(x0, y0, x1, y1) < 1.0
    w.orientation_widget = types.SimpleNamespace(GetEnabled=lambda: 1, GetViewport=lambda: (0.0, 0.0, 1.0, 1.0))
    assert w._rect_depth(x0, y0, x1, y1) is None


def test_repeated_tiny_zoom_windows_never_clip_the_aimed_geometry():
    w = _zoomable(False, 25.0)
    # geometrie lointaine : le plan proche suit alors le plan lointain (~0,1 %)
    w.renderer.AddActor(_actor([(0, [(100.0, 0.0, -1000.0), (108.0, 0.0, -1000.0), (108.0, 8.0, -1000.0)])], "polys"))
    w.renderer.ResetCameraClippingRange()
    w.render_window.Render()
    (x0, y0), (x1, y1) = _rect(w, 25.0)
    aim = ((x0 + x1) / 2, (y0 + y1) / 2)
    for _ in range(3):
        w._zoom_to_rect((aim[0] - 4, aim[1] - 4), (aim[0] + 4, aim[1] + 4))
        w.render_window.Render()
        assert w._rect_depth(190, 140, 210, 160) is not None
        aim = (200, 150)


def test_zoom_window_on_an_empty_area_zooms_on_the_focal_plane():
    w = _zoomable(False)
    w._pickable_actors = {}
    cam = w.renderer.GetActiveCamera()
    before = cam.GetDistance()
    w._zoom_to_rect((100, 100), (300, 150))
    assert cam.GetDistance() == pytest.approx(before / 2.0)


def _at_focal_depth(w, x, y):
    """Point monde sous le pixel (x, y), a la profondeur du point focal."""
    ren = w.renderer
    ren.SetWorldPoint(*ren.GetActiveCamera().GetFocalPoint(), 1.0)
    ren.WorldToDisplay()
    ren.SetDisplayPoint(float(x), float(y), ren.GetDisplayPoint()[2])
    ren.DisplayToWorld()
    wx, wy, wz, ww = ren.GetWorldPoint()
    return wx / ww, wy / ww, wz / ww


@pytest.mark.parametrize("parallel", [True, False], ids=["ortho", "perspective"])
@pytest.mark.parametrize("view, rect", [
    ((400, 300), (200, 190)),   # un peu plus large que haut, moins allonge que la vue
    ((300, 400), (190, 200)),   # vue en hauteur, cas symetrique
    ((400, 300), (300, 20)),    # tres allonge
    ((400, 300), (20, 200)),    # tres haut
    ((400, 300), (100, 0)),     # hauteur nulle
])
def test_zoom_window_keeps_the_whole_rectangle_in_view(parallel, view, rect):
    w = _zoomable(parallel)
    w._pickable_actors = {}
    w._window.SetSize(*view)
    w._window.Render()
    (width, height), (rw, rh) = view, rect
    x0, y0 = (width - rw) // 2 + 20, (height - rh) // 2 + 10
    corners = [_at_focal_depth(w, x, y) for x, y in ((x0, y0), (x0 + rw, y0), (x0 + rw, y0 + rh), (x0, y0 + rh))]
    w._zoom_to_rect((x0, y0), (x0 + rw, y0 + rh))
    coord = vtk.vtkCoordinate()
    coord.SetCoordinateSystemToWorld()
    points = []
    for corner in corners:
        coord.SetValue(*corner)
        points.append(coord.GetComputedDoubleDisplayValue(w.renderer))
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    assert min(xs) >= -2 and max(xs) <= width + 2 and min(ys) >= -2 and max(ys) <= height + 2
    # le rectangle remplit la vue dans sa dimension la plus contraignante
    assert max((max(xs) - min(xs)) / width, (max(ys) - min(ys)) / height) == pytest.approx(1.0, abs=0.02)
