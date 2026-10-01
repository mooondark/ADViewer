# -*- coding: utf-8 -*-
"""Etiquettes de valeurs des diagrammes : le texte doit se placer vers
l'exterieur du diagramme (cote ecran), jamais sur lui. Un
vtkBillboardTextActor3D dessine par defaut son texte AU-DESSUS de l'ancre et
centre : une etiquette sous le diagramme le recouvrait."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D

from viewer_widget import VTKViewerWidget


def _widget():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.renderer = vtk.vtkRenderer()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(w.renderer)
    w._window = window
    cam = w.renderer.GetActiveCamera()
    cam.SetPosition(0.0, -10.0, 0.0)   # ecran : droite = +x, haut = +z
    cam.SetFocalPoint(0.0, 0.0, 0.0)
    cam.SetViewUp(0.0, 0.0, 1.0)
    return w


def _label(outward):
    actor = vtkBillboardTextActor3D()
    actor.SetInput("-26.03 kN")
    actor.SetPosition(0.0, 0.0, 0.0)
    actor._diagram_outward = outward
    return actor


def _orientation(outward):
    w = _widget()
    actor = _label(outward)
    w._orient_diagram_label(actor)
    tp = actor.GetTextProperty()
    return tp.GetJustificationAsString(), tp.GetVerticalJustificationAsString()


def test_label_below_the_diagram_hangs_under_the_anchor():
    assert _orientation((0.0, 0.0, -1.0)) == ("Centered", "Top")


def test_label_above_the_diagram_stands_over_the_anchor():
    assert _orientation((0.0, 0.0, 1.0)) == ("Centered", "Bottom")


def test_label_to_the_right_starts_at_the_anchor_and_extends_rightwards():
    assert _orientation((1.0, 0.0, 0.0)) == ("Left", "Centered")


def test_label_to_the_left_ends_at_the_anchor():
    assert _orientation((-1.0, 0.0, 0.0)) == ("Right", "Centered")


def test_label_diagonal_outward_is_anchored_by_its_nearest_corner():
    assert _orientation((1.0, 0.0, -1.0)) == ("Left", "Top")
    assert _orientation((-1.0, 0.0, -1.0)) == ("Right", "Top")
    assert _orientation((1.0, 0.0, 1.0)) == ("Left", "Bottom")
    assert _orientation((-1.0, 0.0, 1.0)) == ("Right", "Bottom")


def test_label_nearly_vertical_outward_stays_centered_horizontally():
    assert _orientation((0.1, 0.0, -1.0)) == ("Centered", "Top")


def _orientation_with_tangent(outward, tangent):
    w = _widget()
    actor = _label(outward)
    actor._diagram_tangent = tangent
    w._orient_diagram_label(actor)
    tp = actor.GetTextProperty()
    return tp.GetJustificationAsString(), tp.GetVerticalJustificationAsString()


def test_flat_tangent_keeps_plain_below_placement():
    assert _orientation_with_tangent((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)) == ("Centered", "Top")


def test_label_below_a_curve_rising_to_the_right_extends_rightwards():
    assert _orientation_with_tangent((0.0, 0.0, -1.0), (1.0, 0.0, 0.4)) == ("Left", "Top")


def test_label_below_a_curve_falling_to_the_right_extends_leftwards():
    assert _orientation_with_tangent((0.0, 0.0, -1.0), (1.0, 0.0, -0.4)) == ("Right", "Top")


def test_label_outward_along_view_axis_falls_back_to_above():
    assert _orientation((0.0, 1.0, 0.0)) == ("Centered", "Bottom")


def test_label_without_outward_direction_is_left_untouched():
    w = _widget()
    actor = vtkBillboardTextActor3D()
    before = actor.GetTextProperty().GetVerticalJustificationAsString()
    w._orient_diagram_label(actor)
    assert actor.GetTextProperty().GetVerticalJustificationAsString() == before


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
