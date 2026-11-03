# -*- coding: utf-8 -*-
"""Lecture des charges ponctuelles, lineaires et surfaciques depuis les objets
de l'API : geometrie, unites (N -> kN), variation, cas de charge et libelles."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd

CASES = {
    10: {"userID": 4, "userName": "G"},
    11: {"userID": None, "name": "Neige"},
    12: {"userID": 6},
}


@pytest.fixture(autouse=True)
def _fake_api(monkeypatch):
    calls = []

    def fetch(host, eids):
        calls.append(list(eids))
        return [CASES.get(eid) for eid in eids]

    monkeypatch.setattr(amd, "get_informational_elements_objects", fetch)
    return calls


def _payload(kind, elements):
    return amd._build_loads_payload(
        kind, "http://h", {f"{kind}_load_ids": list(range(len(elements)))}, {f"{kind}_load_elements": elements})


def test_load_case_labels_use_user_id_then_name_with_fallbacks():
    labels = amd._resolve_load_case_labels("http://h", [
        {"loadCase": {"value": 10}}, {"loadCase": 11}, {"loadCase": {"value": 12}},
        {"loadCase": None}, {"loadCase": "x"}, "pas un dict", {"loadCase": {"value": 99}},
    ])
    assert labels == {10: "4 : G", 11: "11 : Neige", 12: "6"}


def test_load_case_labels_are_empty_when_the_api_fails(monkeypatch):
    def boom(host, eids):
        raise RuntimeError("down")

    monkeypatch.setattr(amd, "get_informational_elements_objects", boom)
    assert amd._resolve_load_case_labels("http://h", [{"loadCase": 10}]) == {}


def test_load_case_labels_do_not_call_the_api_without_cases(_fake_api):
    assert amd._resolve_load_case_labels("http://h", [{"fx": 1}]) == {}
    assert _fake_api == []


@pytest.mark.parametrize("kind", ["punctual", "linear", "planar"])
def test_no_ids_or_no_elements_gives_an_empty_payload(kind):
    def builder(ids_data, objects_data):
        return amd._build_loads_payload(kind, "h", ids_data, objects_data)

    assert builder({f"{kind}_load_ids": [1, 2]}, {f"{kind}_load_elements": []}) == {
        f"{kind}_loads": [], f"{kind}_load_cases": [], f"{kind}_load_ids_count": 2, f"{kind}_load_count": 0,
    }
    assert builder({}, {f"{kind}_load_elements": [{}]})[f"{kind}_load_ids_count"] == 0


def test_punctual_loads():
    payload = _payload("punctual", [
        {"geomPt": {"x": 1, "y": 2, "z": "3"}, "fx": 1000, "Fy": -2000, "moment": {"mx": 500, "My": 1500},
         "mz": 9000, "userID": 7, "loadCase": {"value": 11}},
        {"geomPt": {"x": 0}, "fz": 3000, "userId": "P2", "loadCase": 10},
        {"geomPt": {"x": 0}, "mx": 4000, "Mz": 6000, "userid": 3, "loadCase": {"value": 99}},
        {"geomPt": {}, "fx": 1},
        {"geomPt": {"x": "abc"}},
        "pas un dict",
        {"geomPt": {"x": 5}, "loadCase": "abc"},
    ])
    assert payload["punctual_loads"] == [
        {"pos": (1.0, 2.0, 3.0), "fx": 1.0, "fy": -2.0, "fz": 0.0, "mx": 0.5, "my": 1.5, "mz": 9.0,
         "user_id": 7, "load_case_eid": 11, "load_case_label": "11 : Neige"},
        {"pos": (0.0, 0.0, 0.0), "fx": 0.0, "fy": 0.0, "fz": 3.0, "mx": 0.0, "my": 0.0, "mz": 0.0,
         "user_id": "P2", "load_case_eid": 10, "load_case_label": "4 : G"},
        {"pos": (0.0, 0.0, 0.0), "fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 4.0, "my": 0.0, "mz": 6.0,
         "user_id": 3, "load_case_eid": 99, "load_case_label": "99"},
        {"pos": (5.0, 0.0, 0.0), "fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0,
         "user_id": None, "load_case_eid": None, "load_case_label": ""},
    ]
    assert payload["punctual_load_cases"] == [
        {"eid": 11, "label": "11 : Neige"}, {"eid": 10, "label": "4 : G"}, {"eid": 99, "label": "99"},
    ]
    assert payload["punctual_load_ids_count"] == 7
    assert payload["punctual_load_count"] == 4


def test_linear_loads():
    payload = _payload("linear", [
        {"geomPtStart": {"x": 0}, "geomPtEnd": {"x": 2, "z": 1}, "fz": -5000, "moment": {"Mx": 100},
         "variation": {"coefficient1": 0.5, "coefficient2": None}, "userID": 1, "loadCase": 10},
        {"geomPtStart": {"x": 0}, "geomPtEnd": {"y": 1}, "fx": 1000, "variation": "aucune", "loadCase": 10},
        {"geomPtStart": {"x": 0}, "geomPtEnd": {}},
        {"geomPtStart": {"x": "?"}, "geomPtEnd": {"x": 1}},
    ])
    assert payload["linear_loads"] == [
        {"pt_start": (0.0, 0.0, 0.0), "pt_end": (2.0, 0.0, 1.0), "fx": 0.0, "fy": 0.0, "fz": -5.0,
         "mx": 0.1, "my": 0.0, "mz": 0.0, "coeff1": 0.5, "coeff2": 1.0,
         "user_id": 1, "load_case_eid": 10, "load_case_label": "4 : G"},
        {"pt_start": (0.0, 0.0, 0.0), "pt_end": (0.0, 1.0, 0.0), "fx": 1.0, "fy": 0.0, "fz": 0.0,
         "mx": 0.0, "my": 0.0, "mz": 0.0, "coeff1": 1.0, "coeff2": 1.0,
         "user_id": None, "load_case_eid": 10, "load_case_label": "4 : G"},
    ]
    assert payload["linear_load_cases"] == [{"eid": 10, "label": "4 : G"}]
    assert payload["linear_load_count"] == 2


def test_planar_loads():
    square = [{"x": 0, "y": 0}, {"x": 1}, {"x": 1, "y": 1}, "bruit", {"y": "?"}]
    payload = _payload("planar", [
        {"geomPtsList": square, "fz": -2000, "variation": {"coefficient1": 2, "coefficient3": 0},
         "userID": 9, "loadCase": {"value": 12}},
        {"geomPtsList": [{"x": 0}, {"x": 1}]},
        {"geomPtsList": [{"x": 0}, {"x": 1}, {"y": 1}], "moment": {"mx": 1000}},
    ])
    assert payload["planar_loads"] == [
        {"pts": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)], "fx": 0.0, "fy": 0.0, "fz": -2.0,
         "coeff1": 2.0, "coeff2": 1.0, "coeff3": 0.0, "user_id": 9, "load_case_eid": 12, "load_case_label": "6"},
        {"pts": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], "fx": 0.0, "fy": 0.0, "fz": 0.0,
         "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0, "user_id": None, "load_case_eid": None, "load_case_label": ""},
    ]
    assert payload["planar_load_cases"] == [{"eid": 12, "label": "6"}]
    assert payload["planar_load_count"] == 2
