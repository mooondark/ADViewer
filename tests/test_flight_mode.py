# -*- coding: utf-8 -*-
"""Mode Navigation (camera libre) : fonctions pures testables sans VTK reel."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import viewer_config as cfg


def test_flight_key_bindings_fr_is_azerty():
    cfg.set_language("fr")
    bindings = cfg.get_flight_key_bindings()
    assert bindings == {
        "forward": "z", "backward": "s",
        "left": "q", "right": "d",
        "up": "a", "down": "e",
    }


def test_flight_key_bindings_en_is_qwerty():
    cfg.set_language("en")
    bindings = cfg.get_flight_key_bindings()
    assert bindings == {
        "forward": "w", "backward": "s",
        "left": "a", "right": "d",
        "up": "q", "down": "e",
    }
    cfg.set_language("fr")  # restore default for other tests in the process


import math

from viewer_widget import VTKViewerWidget


def test_flight_direction_vectors_yaw_zero_points_along_y():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(0.0)
    assert forward == (0.0, 1.0, 0.0)
    assert right == (1.0, 0.0, 0.0)
    assert up == (0.0, 0.0, 1.0)


def test_flight_direction_vectors_are_orthogonal_and_horizontal():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(math.radians(37.0))
    assert abs(forward[2]) < 1e-9 and abs(right[2]) < 1e-9
    dot = forward[0] * right[0] + forward[1] * right[1]
    assert abs(dot) < 1e-9
    assert up == (0.0, 0.0, 1.0)


def test_flight_look_direction_matches_azimuth_elevation_convention():
    # Meme convention que VTKViewerWidget._azimuth_elevation_to_position :
    # x = cos(pitch) * sin(yaw), y = cos(pitch) * cos(yaw), z = sin(pitch).
    dx, dy, dz = VTKViewerWidget._flight_look_direction(0.0, 0.0)
    assert (round(dx, 9), round(dy, 9), round(dz, 9)) == (0.0, 1.0, 0.0)
    dx, dy, dz = VTKViewerWidget._flight_look_direction(0.0, math.radians(90.0))
    assert round(dz, 9) == 1.0


def test_flight_movement_vector_no_keys_is_zero():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(0.0)
    bindings = {"forward": "z", "backward": "s", "left": "q", "right": "d", "up": "a", "down": "e"}
    result = VTKViewerWidget._flight_movement_vector(set(), forward, right, up, bindings)
    assert result == (0.0, 0.0, 0.0)


def test_flight_movement_vector_single_key_forward():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(0.0)
    bindings = {"forward": "z", "backward": "s", "left": "q", "right": "d", "up": "a", "down": "e"}
    result = VTKViewerWidget._flight_movement_vector({"z"}, forward, right, up, bindings)
    assert result == (0.0, 1.0, 0.0)


def test_flight_movement_vector_diagonal_is_normalized():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(0.0)
    bindings = {"forward": "z", "backward": "s", "left": "q", "right": "d", "up": "a", "down": "e"}
    result = VTKViewerWidget._flight_movement_vector({"z", "d"}, forward, right, up, bindings)
    length = math.sqrt(sum(c * c for c in result))
    assert abs(length - 1.0) < 1e-9


def test_flight_movement_vector_opposite_keys_cancel():
    forward, right, up = VTKViewerWidget._flight_direction_vectors(0.0)
    bindings = {"forward": "z", "backward": "s", "left": "q", "right": "d", "up": "a", "down": "e"}
    result = VTKViewerWidget._flight_movement_vector({"z", "s"}, forward, right, up, bindings)
    assert result == (0.0, 0.0, 0.0)


def test_flight_safe_position_returns_unchanged_when_bounds_none():
    pos = (5.0, 5.0, 5.0)
    result = VTKViewerWidget._flight_safe_position(pos, None, (0.0, 1.0, 0.0))
    assert result == pos


def test_flight_safe_position_leaves_outside_position_unchanged():
    bounds = (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
    pos = (100.0, 100.0, 100.0)
    result = VTKViewerWidget._flight_safe_position(pos, bounds, (0.0, 1.0, 0.0))
    assert result == pos


def test_flight_safe_position_pushes_camera_out_of_bounds():
    bounds = (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
    pos = (0.0, 0.0, 0.0)  # centre exact -> cas degenere, repli sur -view_direction
    result = VTKViewerWidget._flight_safe_position(pos, bounds, (0.0, 1.0, 0.0))
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    assert not (xmin <= result[0] <= xmax and ymin <= result[1] <= ymax and zmin <= result[2] <= zmax)
    assert result[1] < 0.0  # repousse dans -y, oppose a view_direction=(0,1,0)


def test_flight_controls_overlay_text_contains_bound_keys():
    import viewer_config as cfg
    cfg.set_language("fr")
    bindings = {"forward": "z", "backward": "s", "left": "q", "right": "d", "up": "a", "down": "e"}
    text = VTKViewerWidget._flight_controls_overlay_text(bindings)
    assert "Z/S" in text
    assert "Q/D" in text
    assert "A/E" in text


def test_flight_clamp_pitch_within_range_is_unchanged():
    limit = math.radians(89.0)
    assert VTKViewerWidget._flight_clamp_pitch(0.1, limit) == 0.1


def test_flight_clamp_pitch_clamps_above_limit():
    limit = math.radians(89.0)
    result = VTKViewerWidget._flight_clamp_pitch(math.radians(120.0), limit)
    assert abs(result - limit) < 1e-9


def test_flight_clamp_pitch_clamps_below_limit():
    limit = math.radians(89.0)
    result = VTKViewerWidget._flight_clamp_pitch(math.radians(-120.0), limit)
    assert abs(result + limit) < 1e-9


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
