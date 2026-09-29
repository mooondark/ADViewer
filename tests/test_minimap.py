# -*- coding: utf-8 -*-
"""Minicarte : fonctions pures testables sans VTK reel."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import minimap


def test_viewport_rect_bottom_left_default_size():
    rect = minimap.viewport_rect("bottom_left", 1200.0, 900.0, size_px=300.0)
    xmin, ymin, xmax, ymax = rect
    assert xmin == 0.0
    assert ymin == 0.0
    assert abs(xmax - 300.0 / 1200.0) < 1e-9
    assert abs(ymax - 300.0 / 900.0) < 1e-9


def test_viewport_rect_bottom_right_is_mirrored():
    rect = minimap.viewport_rect("bottom_right", 1200.0, 900.0, size_px=300.0)
    xmin, ymin, xmax, ymax = rect
    assert abs(xmax - 1.0) < 1e-9
    assert abs(xmin - (1.0 - 300.0 / 1200.0)) < 1e-9
    assert ymin == 0.0


def test_viewport_rect_clamps_on_small_window():
    rect = minimap.viewport_rect("bottom_left", 150.0, 100.0, size_px=300.0)
    xmin, ymin, xmax, ymax = rect
    assert 0.0 <= xmin < xmax <= 1.0
    assert 0.0 <= ymin < ymax <= 1.0
    assert abs(xmax - 1.0) < 1e-9
    assert abs(ymax - 1.0) < 1e-9


def test_viewport_rect_unknown_corner_falls_back_to_bottom_left():
    rect = minimap.viewport_rect("nonsense", 1200.0, 900.0, size_px=300.0)
    xmin, _ymin, _xmax, _ymax = rect
    assert xmin == 0.0


def test_camera_fov_triangle_apex_is_position():
    points = minimap.camera_fov_triangle((10.0, 20.0), (0.0, 1.0), 30.0, 5.0)
    assert len(points) == 3
    apex = points[0]
    assert abs(apex[0] - 10.0) < 1e-9
    assert abs(apex[1] - 20.0) < 1e-9


def test_camera_fov_triangle_base_points_symmetric_around_axis():
    points = minimap.camera_fov_triangle((0.0, 0.0), (0.0, 1.0), 30.0, 5.0)
    _apex, base_left, base_right = points
    # Direction (0,1) -> base centree en (0, 5), perpendiculaire = axe X.
    assert abs(base_left[1] - 5.0) < 1e-9
    assert abs(base_right[1] - 5.0) < 1e-9
    assert abs(base_left[0] + base_right[0]) < 1e-9
    half_width = 5.0 * math.tan(math.radians(30.0))
    assert abs(base_left[0] - half_width) < 1e-9 or abs(base_left[0] + half_width) < 1e-9


def test_camera_fov_triangle_handles_zero_direction():
    # Direction degeneree (camera verticale) : ne doit pas lever, ni produire de NaN.
    points = minimap.camera_fov_triangle((1.0, 2.0), (0.0, 0.0), 30.0, 5.0)
    assert len(points) == 3
    for x, y in points:
        assert not math.isnan(x)
        assert not math.isnan(y)


def test_horizontal_half_fov_deg_square_aspect_matches_vertical():
    result = minimap.horizontal_half_fov_deg(60.0, 1.0, is_parallel=False)
    assert abs(result - 30.0) < 1e-9


def test_horizontal_half_fov_deg_wide_aspect_widens_fov():
    result = minimap.horizontal_half_fov_deg(60.0, 2.0, is_parallel=False)
    assert result > 30.0


def test_horizontal_half_fov_deg_parallel_projection_is_fixed_25():
    result = minimap.horizontal_half_fov_deg(60.0, 2.0, is_parallel=True)
    assert result == 25.0


def test_point_in_rect_inside_and_outside():
    assert minimap.point_in_rect((1.0, 1.0), (0.0, 0.0), 2.0, 2.0)
    assert minimap.point_in_rect((2.0, -2.0), (0.0, 0.0), 2.0, 2.0)  # bord inclus
    assert not minimap.point_in_rect((2.1, 0.0), (0.0, 0.0), 2.0, 2.0)
    assert not minimap.point_in_rect((0.0, -5.0), (0.0, 0.0), 2.0, 2.0)


def test_clamp_to_rect_edge_lands_on_inset_border_along_ray():
    x, y = minimap.clamp_to_rect_edge((0.0, 0.0), (10.0, 5.0), 4.0, 4.0, 1.0)
    assert abs(x - 3.0) < 1e-9          # bord droit rentre de 1
    assert abs(y - 1.5) < 1e-9          # meme droite : y = x / 2


def test_clamp_to_rect_edge_uses_vertical_border_when_steeper():
    x, y = minimap.clamp_to_rect_edge((1.0, 1.0), (1.0, -9.0), 4.0, 2.0, 0.5)
    assert abs(x - 1.0) < 1e-9
    assert abs(y - (1.0 - 1.5)) < 1e-9


def test_clamp_to_rect_edge_point_at_center_returns_center():
    assert minimap.clamp_to_rect_edge((2.0, 3.0), (2.0, 3.0), 4.0, 4.0, 1.0) == (2.0, 3.0)


def test_arrow_polygon_tip_along_direction_and_no_nan():
    tip, left, notch, right = minimap.arrow_polygon((0.0, 0.0), (0.0, 2.0), 1.0)
    assert abs(tip[0]) < 1e-9 and abs(tip[1] - 1.0) < 1e-9
    assert abs(left[0] + right[0]) < 1e-9  # symetrique autour de l'axe
    degenerate = minimap.arrow_polygon((0.0, 0.0), (0.0, 0.0), 1.0)
    assert all(not math.isnan(c) for pt in degenerate for c in pt)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
