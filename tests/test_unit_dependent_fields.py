# -*- coding: utf-8 -*-
"""Recalcul des Proprietes et du Metre apres un changement d'unites : memes
filtres d'acceptation que le chargement, pour rester aligne sur lines/planars."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd


@pytest.fixture(autouse=True)
def _tagged_extractors(monkeypatch):
    def tag(name):
        return lambda el, *maps: (name, el["id"], *[sorted(m) for m in maps])

    for name in ("linear_element", "planar_element", "load_area", "punctual_support",
                 "linear_support", "planar_support"):
        monkeypatch.setattr(amd, f"extract_{name}_properties", tag(name))
    monkeypatch.setattr(amd, "extract_planar_geometry", lambda el: el.get("ok"))
    monkeypatch.setattr(amd, "extract_load_area_geometry", lambda el: el.get("ok"))
    for name in ("linear_takeoff", "linear_material_takeoff", "planar_takeoff",
                 "planar_material_takeoff", "load_area_takeoff"):
        monkeypatch.setattr(amd, f"_build_{name}", lambda els, *maps, name=name: (name, [e["id"] for e in els], *maps))


def test_keeps_only_the_elements_the_model_load_keeps():
    seg = {"geomPtStart": 1, "geomPtEnd": 2}
    cache = {
        "linear_elements": [{"id": "L1", **seg}, {"id": "L2", "geomPtStart": 1}],
        "planar_elements": [{"id": "P1", "ok": True}, {"id": "P2"}, {"id": "P3", "ok": True}],
        "planar_ids": [1, 2],   # zip : P3 sans id est ignore
        "load_area_elements": [{"id": "A1", "ok": True}, {"id": "A2"}],
        "punctual_support_elements": [{"id": "S1", "geomPt": 1}, {"id": "S2"}],
        "punctual_support_ids": [1, 2],
        "linear_support_elements": [{"id": "LS1", **seg}, {"id": "LS2", "geomPtEnd": 2}],
        "linear_support_ids": [1, 2],
        "planar_support_elements": [{"id": "PS1", "geomPtsList": [1, 2, 3]}, {"id": "PS2", "geomPtsList": [1, 2]}],
        "planar_support_ids": [1, 2],
        "linear_material_by_eid": {5: "S235"},
        "linear_section_by_eid": {6: "IPE"},
        "planar_material_by_eid": {7: "C25"},
    }
    out = amd.recompute_unit_dependent_fields(cache)
    assert out["line_properties"] == [("linear_element", "L1", [5], [6])]
    assert out["planar_properties"] == [("planar_element", "P1", [7])]
    assert out["load_area_properties"] == [("load_area", "A1")]
    assert out["punctual_support_properties"] == [("punctual_support", "S1")]
    assert out["linear_support_properties"] == [("linear_support", "LS1")]
    assert out["planar_support_properties"] == [("planar_support", "PS1")]
    assert out["linear_takeoff"] == ("linear_takeoff", ["L1", "L2"], {6: "IPE"})
    assert out["linear_material_takeoff"] == ("linear_material_takeoff", ["L1", "L2"], {5: "S235"})
    assert out["planar_takeoff"] == ("planar_takeoff", ["P1", "P2", "P3"])
    assert out["planar_material_takeoff"] == ("planar_material_takeoff", ["P1", "P2", "P3"], {7: "C25"})
    assert out["load_area_takeoff"] == ("load_area_takeoff", ["A1", "A2"])


def test_empty_or_missing_cache_gives_empty_lists():
    out = amd.recompute_unit_dependent_fields(None)
    assert out["line_properties"] == [] and out["planar_support_properties"] == []
    assert out["linear_takeoff"] == ("linear_takeoff", [], {})


def test_rebuild_updates_the_model_in_place_only_with_a_cache():
    model = {"_unit_refresh_cache": {"linear_elements": [{"id": "L1", "geomPtStart": 1, "geomPtEnd": 2}]}}
    assert amd.rebuild_properties_and_takeoff(model) is True
    assert model["line_properties"] == [("linear_element", "L1", [], [])]
    assert amd.rebuild_properties_and_takeoff({"_unit_refresh_cache": {}}) is False
    assert amd.rebuild_properties_and_takeoff("pas un modele") is False
