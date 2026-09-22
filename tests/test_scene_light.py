# -*- coding: utf-8 -*-
"""Conversion azimut/elevation <-> position XYZ de la sceneLight."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget


def test_default_position_round_trip():
    az, el = VTKViewerWidget.scene_light_default_azimuth_elevation()
    x, y, z = VTKViewerWidget._azimuth_elevation_to_position(az, el)
    ex, ey, ez = VTKViewerWidget.SCENE_LIGHT_DEFAULT_POSITION
    assert abs(x - ex) < 1e-6 and abs(y - ey) < 1e-6 and abs(z - ez) < 1e-6


def test_straight_up_is_elevation_90():
    az, el = VTKViewerWidget._position_to_azimuth_elevation(0, 0, 100)
    assert abs(el - 90) < 1e-6


def test_azimuth_zero_points_along_y():
    x, y, z = VTKViewerWidget._azimuth_elevation_to_position(0, 0)
    assert abs(x) < 1e-6 and y > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
