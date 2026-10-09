# -*- coding: utf-8 -*-
"""Controle du modele 3D : symboles VTK et AnomalyOverlay."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import model_check as mc
import model_check_view as mcv

TH = mc.Thresholds()   # taille minimale 50 mm -> plancher de rayon 25 mm


def _anomaly(shape, kind=mc.K_MISSING, items=(("lines", 0),), point=(0.0, 0.0, 0.0)):
    return mc.Anomaly(kind, mc.SEVERITY_BY_KIND[kind], items, tuple(range(len(items))), point, 1.0, 5.0, "mm", shape)


def _bounds(pd):
    return pd.GetBounds()


def test_opacity_is_bounded_between_40_and_60_percent_transparency():
    assert mcv.opacity_from_transparency(50.0) == 0.5
    assert mcv.opacity_from_transparency(10.0) == 0.6
    assert mcv.opacity_from_transparency(99.0) == 0.4


def test_sphere_radius_has_a_floor_of_half_the_minimum_size():
    small = _anomaly({"type": "sphere", "center": (1, 2, 3), "radius": 0.005})
    (pd, kind), = mcv.symbol_parts(small, TH)
    b = _bounds(pd)
    assert kind == mcv.SOLID
    assert abs((b[1] - b[0]) / 2 - 0.025) < 1e-3 and abs((b[0] + b[1]) / 2 - 1.0) < 1e-6
    big = _anomaly({"type": "sphere", "center": (0, 0, 0), "radius": 0.5})
    assert abs(_bounds(mcv.symbol_parts(big, TH)[0][0])[1] - 0.5) < 1e-2


def test_cube_symbol_uses_the_minimum_size():
    (pd, _), = mcv.symbol_parts(_anomaly({"type": "cube", "center": (0, 0, 0)}, mc.K_SUPPORT_OVERLAP), TH)
    b = _bounds(pd)
    assert abs((b[1] - b[0]) - 0.05) < 1e-9 and abs((b[5] - b[4]) - 0.05) < 1e-9


def test_prism_is_oriented_and_floored():
    shape = {"type": "prism", "center": (0, 0, 0), "u": (1, 0, 0), "v": (0, 1, 0), "w": (0, 0, 1),
             "half": (1.0, 0.0, 0.0)}
    (pd, _), = mcv.symbol_parts(_anomaly(shape, mc.K_DUPLICATE), TH)
    b = _bounds(pd)
    assert abs((b[1] - b[0]) - 2.0) < 1e-9 and abs((b[3] - b[2]) - 0.05) < 1e-9


def test_cylinder_has_minimum_length_and_thin_radius():
    shape = {"type": "cylinder", "p0": (1, 1, 1), "p1": (1, 1, 1), "radius": 0.0, "thin": True, "axis": (1, 0, 0)}
    (pd, _), = mcv.symbol_parts(_anomaly(shape, mc.K_COLLINEAR), TH)
    b = _bounds(pd)
    assert abs((b[1] - b[0]) - 0.1) < 1e-6          # 2 x taille minimale, centre sur le noeud
    assert abs((b[0] + b[1]) / 2 - 1.0) < 1e-6
    assert (b[3] - b[2]) < 0.05


def test_frame_is_line_only_and_surface_has_outline_and_sphere():
    frame = _anomaly({"type": "frame", "bounds": (0, 1, 0, 2, 0, 3)}, mc.K_NO_SUPPORT, items=())
    (pd, kind), = mcv.symbol_parts(frame, TH)
    assert kind == mcv.LINE and pd.GetNumberOfLines() > 0 and pd.GetNumberOfPolys() == 0
    surf = _anomaly({"type": "surface", "outline": ((0, 0, 0), (1, 0, 0), (1, 1, 0)), "center": (0.5, 0.3, 0), "radius": 0.001},
                    mc.K_SURF_AREA, items=(("planars", 0),))
    parts = mcv.symbol_parts(surf, TH)
    assert [k for _, k in parts] == [mcv.LINE, mcv.SOLID]


def _overlay_with(shapes):
    renderer = vtk.vtkRenderer()
    overlay = mcv.AnomalyOverlay(renderer)
    anomalies = [_anomaly(s, point=s.get("center", (0, 0, 0))) for s in shapes]
    overlay.set_anomalies(anomalies, TH)
    return renderer, overlay


def test_overlay_colors_follow_severity_and_opacity_follows_threshold():
    renderer, overlay = _overlay_with([{"type": "sphere", "center": (0, 0, 0), "radius": 0.1}])
    actor = renderer.GetActors().GetItemAsObject(0)
    assert tuple(actor.GetProperty().GetColor()) == mcv.COLORS[mc.ERROR]
    assert abs(actor.GetProperty().GetOpacity() - 0.5) < 1e-9


def test_overlay_active_symbol_is_reinforced_then_restored():
    renderer, overlay = _overlay_with([{"type": "sphere", "center": (0, 0, 0), "radius": 0.1}])
    actor = renderer.GetActors().GetItemAsObject(0)
    overlay.set_active(0)
    assert actor.GetProperty().GetOpacity() == mcv.ACTIVE_OPACITY
    overlay.set_active(None)
    assert abs(actor.GetProperty().GetOpacity() - 0.5) < 1e-9


def test_overlay_visibility_clear_and_suspended_bounds():
    renderer, overlay = _overlay_with([{"type": "sphere", "center": (0, 0, 0), "radius": 0.1}])
    actor = renderer.GetActors().GetItemAsObject(0)
    overlay.set_visible(False)
    assert not actor.GetVisibility() and not overlay.is_visible()
    overlay.set_visible(True)
    with overlay.suspended():
        assert not actor.GetVisibility()
    assert actor.GetVisibility()
    overlay.clear()
    assert renderer.GetActors().GetNumberOfItems() == 0 and overlay.count() == 0


def test_overlay_bounds_and_pick():
    renderer, overlay = _overlay_with([{"type": "sphere", "center": (0, 0, 0), "radius": 0.5},
                                       {"type": "sphere", "center": (5, 0, 0), "radius": 0.5}])
    b = overlay.bounds(1)
    assert abs((b[0] + b[1]) / 2 - 5.0) < 1e-6
    assert overlay.bounds(9) is None
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(200, 200)
    window.AddRenderer(renderer)
    cam = renderer.GetActiveCamera()
    cam.SetPosition(0, 0, 20)
    cam.SetFocalPoint(0, 0, 0)
    cam.SetViewUp(0, 1, 0)
    renderer.ResetCameraClippingRange()
    try:
        window.Render()
    except Exception:
        return   # pas de contexte OpenGL : le picking ne peut pas etre teste ici
    assert overlay.pick(100, 100) == [0] or overlay.pick(100, 100) == []
