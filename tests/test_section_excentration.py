# -*- coding: utf-8 -*-
"""Excentrement des sections : le decalage calcule depuis les dimensions doit
placer le profil comme son polygone dessine (viewer et export IFC)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from section_geometry import (
    parse_section_dims,
    polygon_bounds,
    profile_polygon,
    section_excentration_translation_from_bounds,
    section_excentration_translation_local,
)

SECTIONS = {
    "tube rectangulaire (mm)": {"name": "RHS 100 50 5", "materialName": "S235"},
    "tube rectangulaire (cm)": {"name": "20 10 1", "type": "ST_RECTANGULAR_TUBE"},
    "tube rond": {"name": "CHS 100 5"},
    "rond plein": {"name": "CIRC 30"},
    "T dissymetrique": {"name": "20 60 10 10 20 10 10 20", "type": "T_DISSYMETRIC"},
    "rectangle": {"name": "RECT 30 20"},
    "I": {"name": "IPE 200"},
    "T": {"name": "T 30 1 20 1.5"},
    "U": {"name": "UPN 120"},
    "corniere": {"name": "L 50X30X4"},
    "omega": {"name": "W14"},
    "Z": {"name": "Z20X6X5X0.2 0.25"},
}
OPTIONS = ["topleft", "gauche_centre", "gauche_bas", "centre_haut", "center_alignment",
           "centre_bas", "droite_haut", "droite_centre", "droite_bas"]


@pytest.mark.parametrize("option", OPTIONS)
@pytest.mark.parametrize("label", SECTIONS)
def test_excentration_places_the_profile_like_its_drawn_polygon(label, option):
    dims = parse_section_dims(SECTIONS[label])
    el = {"sectionExcentration": {"option": option}}
    expected = section_excentration_translation_from_bounds(el, polygon_bounds(profile_polygon(dims)["outer"]))
    assert section_excentration_translation_local(el, dims) == pytest.approx(expected)


def test_top_aligned_rectangular_tube_is_shifted_by_half_its_depth():
    dims = parse_section_dims({"name": "RHS 100 50 5", "materialName": "S235"})
    el = {"sectionExcentration": {"option": "centre_haut"}}
    assert section_excentration_translation_local(el, dims) == pytest.approx((0.0, 0.05))
