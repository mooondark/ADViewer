# -*- coding: utf-8 -*-
"""
test_planar_thickness.py
Solide epaissi des elements surfaciques (mode Profiles) :
- repere local (normale/u/v) d'un panneau plat ;
- solide loft (bornes attendues selon epaisseur/excentrement, y compris trous) ;
- cas degeneres (liste vide, panneau a moins de 3 points).

Depend de vtk (PySide6 pas necessaire ici : VTKViewerWidget est instancie via
__new__, sans __init__, meme pattern que tests/test_profile_render.py).
`python test_planar_thickness.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget


def _widget():
    return VTKViewerWidget.__new__(VTKViewerWidget)


_SQUARE_XY = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
_SQUARE_XZ = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)]  # mur vertical


def test_polygon_local_frame_flat_panel_normal_is_vertical():
    w = _widget()
    normal, u_vec, v_vec = w._polygon_local_frame(_SQUARE_XY)
    assert abs(abs(normal[2]) - 1.0) < 1e-9
    assert abs(normal[0]) < 1e-9 and abs(normal[1]) < 1e-9


def test_polygon_local_frame_vectors_are_orthonormal():
    w = _widget()
    normal, u_vec, v_vec = w._polygon_local_frame(_SQUARE_XY)
    for vec in (normal, u_vec, v_vec):
        length = sum(c * c for c in vec) ** 0.5
        assert abs(length - 1.0) < 1e-9
    assert abs(sum(a * b for a, b in zip(normal, u_vec))) < 1e-9
    assert abs(sum(a * b for a, b in zip(normal, v_vec))) < 1e-9
    assert abs(sum(a * b for a, b in zip(u_vec, v_vec))) < 1e-9


def test_polygon_local_frame_vertical_wall_normal_is_horizontal():
    w = _widget()
    normal, _u, _v = w._polygon_local_frame(_SQUARE_XZ)
    assert abs(normal[2]) < 1e-9  # normale d'un mur vertical : pas de composante Z


def test_build_planar_thickness_polydata_returns_none_for_empty_list():
    w = _widget()
    assert w._build_planar_thickness_polydata([], [], []) is None


def test_build_planar_thickness_polydata_skips_degenerate_panel():
    w = _widget()
    pd = w._build_planar_thickness_polydata([{"outer": [(0, 0, 0), (1, 0, 0)]}], [1.0], [0.0])
    assert pd is None


def test_build_planar_thickness_polydata_symmetric_thickness_bounds():
    w = _widget()
    pd = w._build_planar_thickness_polydata(
        [{"outer": _SQUARE_XY, "openings": []}], [1.0], [0.0], element_indexes=[0],
    )
    assert pd is not None
    assert pd.GetNumberOfCells() > 0
    xmin, xmax, ymin, ymax, zmin, zmax = pd.GetBounds()
    assert abs(xmin - 0.0) < 1e-6 and abs(xmax - 1.0) < 1e-6
    assert abs(ymin - 0.0) < 1e-6 and abs(ymax - 1.0) < 1e-6
    # Epaisseur 1.0, excentrement 0.0, normale +-Z -> solide de Z=-0.5 a Z=0.5
    assert abs(zmin - (-0.5)) < 1e-6
    assert abs(zmax - 0.5) < 1e-6


def test_build_planar_thickness_polydata_eccentricity_shifts_solid():
    w = _widget()
    pd = w._build_planar_thickness_polydata(
        [{"outer": _SQUARE_XY, "openings": []}], [1.0], [2.0], element_indexes=[0],
    )
    assert pd is not None
    _xmin, _xmax, _ymin, _ymax, zmin, zmax = pd.GetBounds()
    # excentrement +2.0, epaisseur 1.0 -> Z de 1.5 a 2.5
    assert abs(zmin - 1.5) < 1e-6
    assert abs(zmax - 2.5) < 1e-6


def test_build_planar_thickness_polydata_with_opening_still_builds_solid():
    w = _widget()
    hole = [(0.25, 0.25, 0.0), (0.75, 0.25, 0.0), (0.75, 0.75, 0.0), (0.25, 0.75, 0.0)]
    pd = w._build_planar_thickness_polydata(
        [{"outer": _SQUARE_XY, "openings": [hole]}], [0.2], [0.0], element_indexes=[0],
    )
    assert pd is not None
    assert pd.GetNumberOfCells() > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
