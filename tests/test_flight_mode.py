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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
