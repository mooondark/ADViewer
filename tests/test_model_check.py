# -*- coding: utf-8 -*-
"""Controle du modele 3D : moteur de detection pur (model_check.py)."""

import copy
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_check as mc


def test_aligned_line_eids_skip_elements_without_geometry():
    import ad_model_data

    elements = [
        {"geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 1, "y": 0, "z": 0}},
        {"geomPtStart": None, "geomPtEnd": {"x": 1, "y": 0, "z": 0}},
        {"geomPtStart": {"x": 0, "y": 1, "z": 0}, "geomPtEnd": {"x": 1, "y": 1, "z": 0}},
    ]
    assert ad_model_data._aligned_line_eids([10, 11, 12], elements) == [10, 12]
    assert ad_model_data._aligned_line_eids([10, None, 12], [elements[0], elements[0], elements[2]]) == [10, None, 12]
