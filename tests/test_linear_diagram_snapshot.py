# -*- coding: utf-8 -*-
"""Instantane de reference des diagrammes de resultats filaires : geometrie,
couleurs, proprietes et etiquettes produites par _build_linear_diagram_actors.

tests/data/linear_diagram_snapshot.json a ete produit par le code d'origine.
Regenerer (changement voulu) : python tests/test_linear_diagram_snapshot.py --regen"""

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import vtk

import viewer_widget
from viewer_widget import VTKViewerWidget

SNAPSHOT = os.path.join(os.path.dirname(__file__), "data", "linear_diagram_snapshot.json")
X_LINE = [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0)]


def _series(values, length=4.0):
    n = len(values)
    return [{"abscissa": length * i / (n - 1), "value": v} for i, v in enumerate(values)]


SCENARIOS = {
    "efforts fy, unite et decimales": dict(line_points=X_LINE, series=_series([-12.5, 3.0, 20.25]), title="Efforts - fy", unit="kN", decimals=2),
    "deplacements dz retourne": dict(line_points=X_LINE, series=_series([0.0, -0.004, -0.0061, 0.0]), title="Déplacements - dz",
                                     line_property={"local_axes": {"z": (0.0, 0.0, 1.0)}}, unit="m", decimals=4),
    "deplacements d sans accent": dict(line_points=X_LINE, series=_series([0.0, 0.01, 0.0]), title="deplacements-d"),
    "axes reconstruits avec angle": dict(line_points=[(1.0, 2.0, 0.5), (1.0, 6.0, 2.5)], series=_series([5.0, -5.0, 2.0], 4.472),
                                         title="Efforts - mz", line_property={"section_orientation_angle_rad": 0.5}),
    "poteau vertical": dict(line_points=[(0.0, 0.0, 0.0), (0.0, 0.0, 3.0)], series=_series([1.0, 2.0], 3.0), title="Efforts - fx"),
    "valeurs constantes": dict(line_points=X_LINE, series=_series([7.0, 7.0, 7.0]), title="Efforts - fx", unit="kN"),
    "valeurs quasi nulles": dict(line_points=X_LINE, series=_series([0.00001, -0.00002, 0.5]), title="Efforts - fz", unit="kN", decimals=3),
    "toutes nulles": dict(line_points=X_LINE, series=_series([0.0, 0.0]), title="Efforts - fz"),
    "abscisses hors poutre": dict(line_points=X_LINE, series=[{"abscissa": -1.0, "value": 2.0}, {"abscissa": 9.0, "value": -1.0}, {}],
                                  title="Efforts - fy", decimals=0),
    "echelle doublee": dict(line_points=X_LINE, series=_series([1.0, -3.0]), title="Efforts - my", scale_factor=2.0),
    "theme sombre": dict(line_points=X_LINE, series=_series([1.0, -3.0]), title="Efforts - my", dark=True),
    "points invalides": dict(line_points=[("a", 0, 0), (1, 0, 0)], series=_series([1.0, 2.0])),
    "entrees refusees": dict(line_points=[(0, 0, 0)], series=_series([1.0, 2.0])),
    "serie trop courte": dict(line_points=X_LINE, series=[{"abscissa": 0.0, "value": 1.0}]),
    "longueur nulle": dict(line_points=[(1, 1, 1), (1, 1, 1)], series=_series([1.0, 2.0])),
}


def _widget(scale_factor=1.0):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.renderer = vtk.vtkRenderer()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(w.renderer)
    w._window = window
    cam = w.renderer.GetActiveCamera()
    cam.SetPosition(2.0, -10.0, 3.0)
    cam.SetFocalPoint(2.0, 0.0, 0.0)
    cam.SetViewUp(0.0, 0.0, 1.0)
    w._actors = []
    w._diagram_label_actors = []
    w._clip = types.SimpleNamespace(apply_to_actor=lambda actor: None)
    w._linear_result_scale_factor = scale_factor
    w.linear_line_width = 2.0
    return w


def _r(values):
    return [round(float(v), 9) for v in values]


def _describe_polydata(pd):
    points = [_r(pd.GetPoint(i)) for i in range(pd.GetNumberOfPoints())]
    cells = []
    for i in range(pd.GetNumberOfCells()):
        ids = pd.GetCell(i).GetPointIds()
        cells.append([ids.GetId(k) for k in range(ids.GetNumberOfIds())])
    out = {"points": points, "cells": cells}
    for where, data in (("point_scalars", pd.GetPointData()), ("cell_scalars", pd.GetCellData())):
        scalars = data.GetScalars()
        if scalars is not None:
            out[where] = [list(scalars.GetTuple(i)) for i in range(scalars.GetNumberOfTuples())]
    return out


def _describe(actor):
    prop = actor.GetProperty() if hasattr(actor, "GetProperty") else None
    if isinstance(actor, viewer_widget.vtkBillboardTextActor3D):
        tp = actor.GetTextProperty()
        return {
            "label": actor.GetInput(), "position": _r(actor.GetPosition()), "color": _r(tp.GetColor()),
            "font": tp.GetFontSize(), "bold": tp.GetBold(), "original_color": _r(actor._diagram_original_color),
            "outward": _r(actor._diagram_outward), "tangent": _r(actor._diagram_tangent),
            "justify": [tp.GetJustificationAsString(), tp.GetVerticalJustificationAsString()],
            "pickable": actor.GetPickable(),
        }
    mapper = actor.GetMapper()
    return {
        "polydata": _describe_polydata(mapper.GetInput()),
        "scalar_mode": mapper.GetScalarModeAsString(), "scalar_visibility": mapper.GetScalarVisibility(),
        "color": _r(prop.GetColor()), "opacity": round(prop.GetOpacity(), 9), "line_width": round(prop.GetLineWidth(), 9),
        "representation": prop.GetRepresentation(), "lighting": prop.GetLighting(), "pickable": actor.GetPickable(),
    }


def _run(scenario):
    args = dict(scenario)
    dark = args.pop("dark", False)
    w = _widget(args.pop("scale_factor", 1.0))
    original_bg = viewer_widget._cfg.VTK_BG
    if dark:
        viewer_widget._cfg.VTK_BG = viewer_widget._cfg._DARK_VTK_BG
    try:
        actors = w._build_linear_diagram_actors(**args)
    finally:
        viewer_widget._cfg.VTK_BG = original_bg
    return {
        "actors": [_describe(a) for a in actors],
        "registered_labels": len(w._diagram_label_actors),
        "renderer_actors": w.renderer.GetActors().GetNumberOfItems() + w.renderer.GetViewProps().GetNumberOfItems(),
    }


def _snapshot():
    return {name: _run(scenario) for name, scenario in SCENARIOS.items()}


@pytest.fixture(scope="module")
def reference():
    with open(SNAPSHOT, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("name", SCENARIOS)
def test_linear_diagram_matches_reference(reference, name):
    assert json.loads(json.dumps(_run(SCENARIOS[name]))) == reference[name]


if __name__ == "__main__" and "--regen" in sys.argv:
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
        json.dump(_snapshot(), fh, ensure_ascii=False, indent=1)
    print("ecrit", SNAPSHOT)
