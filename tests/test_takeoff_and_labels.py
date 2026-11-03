# -*- coding: utf-8 -*-
"""Metre des filaires par section / materiau, torseurs des appuis lineaires et
surfaciques, libelles de maillage des surfaciques."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd
from viewer_config import tr_ui


def _bar(length, section=None, material=None):
    return {"geomPtStart": {"x": 0}, "geomPtEnd": {"x": length}, "section": section, "material": material}


def test_linear_takeoff_sums_lengths_by_section_and_by_material():
    bars = [_bar(2, {"value": 1}, 5), _bar(3, 1, {"value": 6}), _bar(4, 2), _bar(1), {"geomPtStart": {"x": 0}}]
    by_section = amd._build_linear_takeoff(bars, {1: "IPE 200", 2: "HEA 100"})
    assert [(row["name"], row["value"]) for row in by_section] == [("HEA 100", 4.0), ("IPE 200", 5.0), ("N/A", 1.0)]
    by_material = amd._build_linear_material_takeoff(bars, {5: "S235"})
    assert [(row["name"], row["value"]) for row in by_material] == [("N/A", 8.0), ("S235", 2.0)]


@pytest.mark.parametrize("reader", ["read_linear_support_results", "read_planar_support_results"])
def test_support_results_read_the_resultant_torsor_only_for_forces(monkeypatch, reader):
    calls = []
    item = {"id": 7, "torsorsFx": 1000.0, "torsorsMz": 2000.0}
    monkeypatch.setattr(amd, "get_results", lambda *args: calls.append(args) or [item])
    read = getattr(amd, reader)

    assert read("h", 7, 3, "Deplacements") == []
    assert calls == []

    rows = read("h", 7, 3, "Efforts")
    assert calls == [("h", "resultantforces", 3, [7])]
    assert rows == amd._build_support_torsor_rows(item)
    assert rows


@pytest.mark.parametrize("label, raw, key", [
    (amd._mesh_type_label, "Triangulation", "prop_mesh_type_triangulation"),
    (amd._mesh_density_label, "ELEMENT_SIZE", "prop_mesh_density_element_size"),
])
def test_mesh_labels_translate_known_values_and_keep_others(label, raw, key):
    assert label(raw) == tr_ui(key)
    assert label("inconnu") == "inconnu"
    assert label(None) == "N/A"
    assert label("") == "N/A"
