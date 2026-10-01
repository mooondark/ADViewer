# -*- coding: utf-8 -*-
"""Capuchons des solides de profils : un contour concave (I, H, L, T, U...) ne
doit pas etre envoye comme un polygone unique, sinon l'affichage le decoupe en
eventail depuis le premier sommet et l'extremite apparait deformee. Un contour
convexe reste un polygone unique (optimisation de performance conservee)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget

I_PROFILE = [(-1, -2, 0), (1, -2, 0), (1, -1.8, 0), (0.1, -1.8, 0), (0.1, 1.8, 0), (1, 1.8, 0),
             (1, 2, 0), (-1, 2, 0), (-1, 1.8, 0), (-0.1, 1.8, 0), (-0.1, -1.8, 0), (-1, -1.8, 0)]
L_PROFILE = [(0, 0, 0), (3, 0, 0), (3, 0.5, 0), (0.5, 0.5, 0), (0.5, 3, 0), (0, 3, 0)]
RECTANGLE = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]


def _widget():
    return VTKViewerWidget.__new__(VTKViewerWidget)


def _shoelace(points):
    n = len(points)
    return 0.5 * abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n)))


def _triangle_area(pd, cid):
    cell = pd.GetCell(cid)
    a, b, c = (pd.GetPoint(cell.GetPointId(k)) for k in range(3))
    return 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def _assert_triangulated_exactly(points):
    cap = _widget()._build_surface_polydata_with_openings(points, [])
    assert cap is not None and cap.GetNumberOfCells() > 1
    for cid in range(cap.GetNumberOfCells()):
        assert cap.GetCell(cid).GetNumberOfPoints() == 3
    covered = sum(_triangle_area(cap, cid) for cid in range(cap.GetNumberOfCells()))
    assert abs(covered - _shoelace(points)) < 1e-5  # points VTK en float32


def test_concave_i_profile_cap_is_triangulated_to_its_exact_area():
    _assert_triangulated_exactly(I_PROFILE)


def test_concave_l_profile_cap_is_triangulated_to_its_exact_area():
    _assert_triangulated_exactly(L_PROFILE)


def test_clockwise_concave_profile_is_also_triangulated():
    _assert_triangulated_exactly(list(reversed(I_PROFILE)))


def test_convex_rectangle_cap_stays_a_single_polygon():
    cap = _widget()._build_surface_polydata_with_openings(RECTANGLE, [])
    assert cap.GetNumberOfCells() == 1 and cap.GetCell(0).GetNumberOfPoints() == 4


def test_convex_polygon_with_collinear_points_stays_a_single_polygon():
    pts = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
    cap = _widget()._build_surface_polydata_with_openings(pts, [])
    assert cap.GetNumberOfCells() == 1


def test_concave_vertical_cap_in_a_non_horizontal_plane_is_triangulated():
    pts = [(x, 0.0, z) for (x, z, _y) in I_PROFILE]   # meme contour dans le plan XZ
    cap = _widget()._build_surface_polydata_with_openings(pts, [])
    assert cap.GetNumberOfCells() > 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
