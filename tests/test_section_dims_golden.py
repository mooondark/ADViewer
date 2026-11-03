# -*- coding: utf-8 -*-
"""Reference figee de parse_section_dims et profile_bounds_from_dims sur un corpus
de sections (noms, types, familles, materiaux) couvrant toutes leurs branches.

tests/data/section_dims_golden.json a ete produit par le code d'origine ; un
ecart signale un changement de comportement, voulu ou non."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from section_geometry import parse_section_dims, profile_bounds_from_dims

with open(os.path.join(os.path.dirname(__file__), "data", "section_dims_golden.json"), encoding="utf-8") as fh:
    GOLDEN = json.load(fh)


def _label(case):
    return json.dumps(case.get("sec", case.get("dims")), ensure_ascii=False)


@pytest.mark.parametrize("case", GOLDEN["sections"], ids=_label)
def test_parse_section_dims_matches_reference(case):
    assert parse_section_dims(case["sec"]) == case["dims"]


@pytest.mark.parametrize("case", GOLDEN["bounds"], ids=_label)
def test_profile_bounds_matches_reference(case):
    bounds = profile_bounds_from_dims(case["dims"])
    assert (list(bounds) if bounds is not None else None) == case["bounds"]
