# -*- coding: utf-8 -*-
"""
load_lines.py
Geometrie des charges dessinees en lignes (style Advance Design) : une seule
vtkPolyData de segments par type de charge, chaque segment portant l'index
de sa charge (selection au clic via vtkCellPicker).
"""

import math
import vtk

TIP_RATIO = 0.12          # longueur max de pointe = TIP_RATIO * echelle
TIP_RADIUS_RATIO = 0.4    # rayon de base du cone = ratio * longueur de pointe
CONE_SIDES = 4
CONE_BASE_SEGS = 8
ARC_SEGS = 24

_AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def resultant(ld, keys) -> float:
    """Norme du vecteur forme par les composantes keys d'une charge (ex. fx, fy, fz)."""
    return math.sqrt(sum(float(ld.get(k) or 0.0) ** 2 for k in keys))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _unit(a):
    n = math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])
    return (a[0]/n, a[1]/n, a[2]/n)


class LoadLines:
    def __init__(self, array_name: str):
        self.array_name = array_name
        self._points = []
        self._segments = []
        self._ids = []

    def _point(self, p):
        self._points.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self._points) - 1

    def add_segment(self, p, q, index: int):
        self._segments.append((self._point(p), self._point(q)))
        self._ids.append(index)

    def add_polyline(self, points, index: int, closed: bool = False):
        if len(points) < 2:
            return
        ids = [self._point(p) for p in points]
        if closed:
            ids.append(ids[0])
        for a, b in zip(ids, ids[1:]):
            self._segments.append((a, b))
            self._ids.append(index)

    def add_arrow(self, tail, direction, length: float, max_tip: float, index: int):
        if length <= 1e-9:
            return
        d = direction
        head = (tail[0] + d[0]*length, tail[1] + d[1]*length, tail[2] + d[2]*length)
        self.add_segment(tail, head, index)
        tip = min(max_tip, 0.5 * length)
        radius = TIP_RADIUS_RATIO * tip
        # axe du repere le moins aligne sur d : base du cone jamais degeneree
        ref = min(_AXES, key=lambda a: abs(a[0]*d[0] + a[1]*d[1] + a[2]*d[2]))
        u = _unit(_cross(d, ref))
        v = _cross(d, u)
        bc = (head[0] - d[0]*tip, head[1] - d[1]*tip, head[2] - d[2]*tip)
        circle = []
        for k in range(CONE_BASE_SEGS):
            a = 2.0 * math.pi * k / CONE_BASE_SEGS
            c, s = math.cos(a) * radius, math.sin(a) * radius
            circle.append((bc[0] + u[0]*c + v[0]*s, bc[1] + u[1]*c + v[1]*s, bc[2] + u[2]*c + v[2]*s))
        step = CONE_BASE_SEGS // CONE_SIDES
        for k in range(CONE_SIDES):
            self.add_segment(head, circle[k * step], index)
        self.add_polyline(circle, index, closed=True)

    def add_moment_arc(self, center, axis: int, radius: float, sign: int, index: int):
        cx, cy, cz = center
        norm_ax = _AXES[axis]
        u, v = [a for i, a in enumerate(_AXES) if i != axis]
        if sign < 0:
            v = (-v[0], -v[1], -v[2])
        start, span = math.radians(45.0), math.radians(270.0)

        def at(t):
            c, s = math.cos(t), math.sin(t)
            return (cx + radius*(u[0]*c + v[0]*s), cy + radius*(u[1]*c + v[1]*s), cz + radius*(u[2]*c + v[2]*s))

        self.add_polyline([at(start + span * i / ARC_SEGS) for i in range(ARC_SEGS + 1)], index)
        end, pen = at(start + span), at(start + span - math.radians(5.0))
        tang = _unit((end[0]-pen[0], end[1]-pen[1], end[2]-pen[2]))
        tip_len = radius * 0.18
        b = _cross(tang, norm_ax)
        b = (b[0]*tip_len, b[1]*tip_len, b[2]*tip_len)
        back = (end[0] - tang[0]*tip_len, end[1] - tang[1]*tip_len, end[2] - tang[2]*tip_len)
        for sgn in (1.0, -1.0):
            self.add_segment(end, (back[0] + sgn*b[0], back[1] + sgn*b[1], back[2] + sgn*b[2]), index)

    def to_polydata(self):
        if not self._segments:
            return None
        pts = vtk.vtkPoints()
        pts.SetNumberOfPoints(len(self._points))
        for i, p in enumerate(self._points):
            pts.SetPoint(i, p)
        lines = vtk.vtkCellArray()
        ids = vtk.vtkIntArray()
        ids.SetName(self.array_name)
        ids.SetNumberOfValues(len(self._ids))
        for i, (seg, idx) in enumerate(zip(self._segments, self._ids)):
            lines.InsertNextCell(2, seg)
            ids.SetValue(i, idx)
        pd = vtk.vtkPolyData()
        pd.SetPoints(pts)
        pd.SetLines(lines)
        pd.GetCellData().AddArray(ids)
        return pd
