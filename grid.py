# -*- coding: utf-8 -*-
"""Grille horizontale sous le modele : calculs purs et construction VTK.
Sans dependance Qt."""

import math

import vtk

from clip_box import expand_bounds

MAJOR_EVERY = 5
MIN_STEP = 0.1  # m ; en dessous, trop de lignes pour un grand modele


def structural_bounds(model_data):
    """(xmin, xmax, ymin, ymax, zmin, zmax) des elements structuraux
    (filaires, surfaciques, parois, appuis), sans les charges. None si vide."""
    pts = [p for seg in model_data.get("lines", []) for p in seg]
    for key in ("planars", "load_areas", "planar_supports"):
        for item in model_data.get(key, []):
            pts += item.get("outer") or []
    pts += model_data.get("punctual_supports", [])
    pts += [p for seg in model_data.get("linear_supports", []) for p in seg]
    if not pts:
        return None
    return [f(p[k] for p in pts) for k in range(3) for f in (min, max)]


def grid_base(model_data, margin_pct):
    """Etendue XY (avec marge) et Z de la grille ; fixes tant que le modele ne change pas."""
    b = structural_bounds(model_data)
    if b is None:
        return None
    e = expand_bounds(b, margin_pct)
    return {"x": (e[0], e[1]), "y": (e[2], e[3]), "z": b[4]}


def _axis_indexes(lo, hi, step):
    return range(math.floor(lo / step), math.ceil(hi / step) + 1)


def build_polydata(base, step_x, step_y, major):
    """Lignes de la grille alignees sur des multiples du pas (origine du modele).
    major=True : une ligne sur MAJOR_EVERY ; False : les autres."""
    (x0, x1), (y0, y1), z = base["x"], base["y"], base["z"]
    ix = _axis_indexes(x0, x1, step_x)
    iy = _axis_indexes(y0, y1, step_y)
    xs0, xs1 = ix[0] * step_x, ix[-1] * step_x
    ys0, ys1 = iy[0] * step_y, iy[-1] * step_y
    points = vtk.vtkPoints()
    lines = vtk.vtkCellArray()

    def add(p, q):
        i = points.InsertNextPoint(*p)
        points.InsertNextPoint(*q)
        lines.InsertNextCell(2, [i, i + 1])

    for i in ix:
        if (i % MAJOR_EVERY == 0) == major:
            add((i * step_x, ys0, z), (i * step_x, ys1, z))
    for j in iy:
        if (j % MAJOR_EVERY == 0) == major:
            add((xs0, j * step_y, z), (xs1, j * step_y, z))
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetLines(lines)
    return pd
