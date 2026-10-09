# -*- coding: utf-8 -*-
"""Controle du modele 3D : symboles VTK des anomalies et AnomalyOverlay.

Les fonctions `*_polydata` sont pures (testables sans fenetre). Les symboles
sont semi-transparents ; couleur = gravite, forme = type d'anomalie. Les
acteurs sont ajoutes directement au renderer (jamais a `_actors` du viewer) :
ils ne sont donc ni coupes par la boite de coupe ni pris en compte par le
cadrage tant que `suspended()` encadre le calcul d'emprise.
"""

import math
from contextlib import contextmanager

import vtk

import model_check as mc

SOLID = "solid"
LINE = "line"
ACTIVE_OPACITY = 0.85
LINE_WIDTH = 2.0
COLORS = {
    mc.ERROR: (1.0, 0.15, 0.15),
    mc.WARNING: (1.0, 0.6, 0.0),
    mc.INFO: (0.2, 0.5, 1.0),
}


def opacity_from_transparency(pct):
    return 1.0 - min(60.0, max(40.0, float(pct))) / 100.0


def _copy(pd):
    out = vtk.vtkPolyData()
    out.ShallowCopy(pd)
    return out


def sphere_polydata(center, radius):
    src = vtk.vtkSphereSource()
    src.SetCenter(*center)
    src.SetRadius(radius)
    src.SetThetaResolution(16)
    src.SetPhiResolution(16)
    src.Update()
    return _copy(src.GetOutput())


def box_polydata(center, u, v, w, half):
    cube = vtk.vtkCubeSource()
    cube.SetXLength(2.0 * half[0])
    cube.SetYLength(2.0 * half[1])
    cube.SetZLength(2.0 * half[2])
    cube.Update()
    m = vtk.vtkMatrix4x4()
    m.Identity()
    for r in range(3):
        m.SetElement(r, 0, u[r])
        m.SetElement(r, 1, v[r])
        m.SetElement(r, 2, w[r])
        m.SetElement(r, 3, center[r])
    t = vtk.vtkTransform()
    t.SetMatrix(m)
    f = vtk.vtkTransformPolyDataFilter()
    f.SetTransform(t)
    f.SetInputData(cube.GetOutput())
    f.Update()
    return _copy(f.GetOutput())


def cylinder_polydata(p0, p1, radius):
    line = vtk.vtkLineSource()
    line.SetPoint1(*p0)
    line.SetPoint2(*p1)
    line.Update()
    tube = vtk.vtkTubeFilter()
    tube.SetInputConnection(line.GetOutputPort())
    tube.SetRadius(radius)
    tube.SetNumberOfSides(16)
    tube.CappingOn()
    tube.Update()
    return _copy(tube.GetOutput())


def outline_polydata(points):
    pts = vtk.vtkPoints()
    for p in points:
        pts.InsertNextPoint(*p)
    ids = list(range(len(points))) + [0]
    lines = vtk.vtkCellArray()
    lines.InsertNextCell(len(ids))
    for i in ids:
        lines.InsertCellPoint(i)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetLines(lines)
    return pd


def frame_polydata(bounds):
    src = vtk.vtkOutlineSource()
    src.SetBounds(*bounds)
    src.Update()
    return _copy(src.GetOutput())


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return None if n < 1e-12 else tuple(c / n for c in v)


def _cylinder_dims(shape, half_min):
    p0, p1 = shape["p0"], shape["p1"]
    thin = bool(shape.get("thin"))
    radius = half_min / 2.0 if thin else max(shape.get("radius", 0.0), half_min)
    axis = _unit(tuple(b - a for a, b in zip(p0, p1))) or shape.get("axis") or (1.0, 0.0, 0.0)
    min_len = 4.0 * half_min if thin else 2.0 * half_min
    length = math.sqrt(sum((b - a) ** 2 for a, b in zip(p0, p1)))
    if length < min_len:
        mid = tuple((a + b) / 2.0 for a, b in zip(p0, p1))
        p0 = tuple(m - c * min_len / 2.0 for m, c in zip(mid, axis))
        p1 = tuple(m + c * min_len / 2.0 for m, c in zip(mid, axis))
    return p0, p1, radius


def symbol_parts(anomaly, thresholds):
    """[(polydata, SOLID|LINE), ...] pour une anomalie, avec les planchers de
    taille de la specification (taille minimale des symboles)."""
    s = anomaly.shape or {}
    t = s.get("type")
    half_min = thresholds.symbol_min_size_mm * 1e-3 / 2.0
    half_max = thresholds.symbol_max_size_mm * 1e-3 / 2.0

    def ball(r):    # le plancher l'emporte si max < min
        return max(min(r, half_max), half_min)

    if t == "sphere":
        return [(sphere_polydata(s["center"], ball(s["radius"])), SOLID)]
    if t == "cube":
        return [(box_polydata(s["center"], (1, 0, 0), (0, 1, 0), (0, 0, 1), (half_min,) * 3), SOLID)]
    if t == "prism":
        half = tuple(max(h, half_min) for h in s["half"])
        return [(box_polydata(s["center"], s["u"], s["v"], s["w"], half), SOLID)]
    if t == "cylinder":
        p0, p1, radius = _cylinder_dims(s, half_min)
        return [(cylinder_polydata(p0, p1, radius), SOLID)]
    if t == "frame":
        return [(frame_polydata(s["bounds"]), LINE)]
    if t == "surface":
        return [(outline_polydata(s["outline"]), LINE),
                (sphere_polydata(s["center"], ball(s["radius"])), SOLID)]
    return []


def _make_actor(polydata, severity, kind, opacity):
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(polydata)
    mapper.SetResolveCoincidentTopologyToPolygonOffset()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    color = COLORS[severity]
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.LightingOff()
    if kind == SOLID:
        prop.EdgeVisibilityOn()
        prop.SetEdgeColor(*color)
        prop.SetLineWidth(1.0)
    else:
        prop.SetLineWidth(LINE_WIDTH)
    actor.PickableOn()
    return actor


class AnomalyOverlay:
    def __init__(self, renderer):
        self.renderer = renderer
        self._entries = []     # [{"anomaly": a, "actors": [(actor, kind), ...]}]
        self._visible = True
        self._active = None
        self._opacity = 0.5

    def count(self):
        return len(self._entries)

    def anomaly(self, index):
        if index is None or not (0 <= index < len(self._entries)):
            return None
        return self._entries[index]["anomaly"]

    def set_anomalies(self, anomalies, thresholds):
        self.clear()
        self._opacity = opacity_from_transparency(thresholds.symbol_transparency_pct)
        for a in anomalies:
            actors = []
            for pd, kind in symbol_parts(a, thresholds):
                actor = _make_actor(pd, a.severity, kind, self._opacity)
                actor.SetVisibility(1 if self._visible else 0)
                self.renderer.AddActor(actor)
                actors.append((actor, kind))
            self._entries.append({"anomaly": a, "actors": actors})

    def clear(self):
        for entry in self._entries:
            for actor, _ in entry["actors"]:
                self.renderer.RemoveActor(actor)
        self._entries = []
        self._active = None

    def set_visible(self, visible):
        self._visible = bool(visible)
        for entry in self._entries:
            for actor, _ in entry["actors"]:
                actor.SetVisibility(1 if self._visible else 0)

    def is_visible(self):
        return self._visible

    def _style_entry(self, index, active):
        for actor, kind in self._entries[index]["actors"]:
            prop = actor.GetProperty()
            prop.SetOpacity(max(self._opacity, ACTIVE_OPACITY) if active else self._opacity)
            if kind == LINE:
                prop.SetLineWidth(LINE_WIDTH + 1.5 if active else LINE_WIDTH)

    def set_active(self, index):
        if self._active is not None and self._active < len(self._entries):
            self._style_entry(self._active, False)
        self._active = index if (index is not None and 0 <= index < len(self._entries)) else None
        if self._active is not None:
            self._style_entry(self._active, True)

    def bounds(self, index):
        if index is None or not (0 <= index < len(self._entries)):
            return None
        union = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
        for actor, _ in self._entries[index]["actors"]:
            b = actor.GetBounds()
            for k in range(3):
                union[2 * k] = min(union[2 * k], b[2 * k])
                union[2 * k + 1] = max(union[2 * k + 1], b[2 * k + 1])
        return tuple(union)

    @contextmanager
    def suspended(self):
        """Masque les symboles le temps d'un calcul d'emprise (vue etendue, boite de coupe)."""
        was = [(actor, actor.GetVisibility()) for e in self._entries for actor, _ in e["actors"]]
        for actor, _ in was:
            actor.SetVisibility(0)
        try:
            yield
        finally:
            for actor, vis in was:
                actor.SetVisibility(vis)

    def pick(self, x, y, max_layers=6):
        """Indices d'anomalies sous le pixel (x, y), du plus proche au plus lointain."""
        if not self._visible or not self._entries:
            return []
        owner = {}
        for index, entry in enumerate(self._entries):
            for actor, _ in entry["actors"]:
                owner[actor] = index
        left = list(owner)
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.0035)
        found = []
        for _ in range(max_layers):
            if not left:
                break
            picker.InitializePickList()
            picker.PickFromListOn()
            for actor in left:
                picker.AddPickList(actor)
            if not picker.Pick(x, y, 0, self.renderer):
                break
            hit = picker.GetActor()
            if hit is None or hit not in owner:
                break
            index = owner[hit]
            if index not in found:
                found.append(index)
            left = [a for a in left if owner[a] != index]
        return found
