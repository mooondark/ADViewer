# -*- coding: utf-8 -*-
"""Fonctions de lecture du modele : proprietes des surfaciques, metre par
materiau, densite, sonde de disponibilite des resultats, session projet."""

import os
import sys
import types

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd
import display_units as du
from viewer_config import tr_ui

SQUARE = [{"x": 0, "y": 0}, {"x": 2}, {"x": 2, "y": 3}, {"y": 3}]


@pytest.fixture(autouse=True)
def _units():
    du.reset()
    yield
    du.reset()


def test_planar_properties_rows():
    el = {
        "type": "AD.Model.Shell", "userID": 12, "material": {"value": 5}, "geomPtsList": SQUARE,
        "thickness": 0.2, "slopeX": 1.5, "eccentricityConsideredAlsoForFEM": True,
        "meshProperties": {"automaticMesh": False, "meshType": "triangulation", "meshDensity": "global"},
    }
    props = amd.extract_planar_element_properties(el, {5: "C25/30"})
    assert props["type_label"] == "Coque n°12"
    assert props["base_type_label"] == "Coque" and props["user_id"] == 12
    assert props["material"] == "C25/30" and props["material_eid"] == 5
    rows = {name: (kind, value) for name, kind, value in props["prop_rows"]}
    assert rows[tr_ui("prop_vertices")] == ("text", "4")
    assert rows[tr_ui("prop_material")] == ("text", "C25/30")
    assert rows[tr_ui("prop_eccentricity_fem")] == ("bool", True)
    assert props["mesh_rows"] == [
        (tr_ui("prop_mesh_automatic"), "bool", False),
        (tr_ui("prop_mesh_type"), "text", tr_ui("prop_mesh_type_triangulation")),
        (tr_ui("prop_mesh_density"), "text", tr_ui("prop_mesh_density_global")),
    ]


def test_planar_properties_defaults():
    props = amd.extract_planar_element_properties({"geomPtsList": []}, {})
    assert props["material"] == "N/A" and props["type_label"] == tr_ui("label_element_planar")
    assert props["mesh_rows"][0] == (tr_ui("prop_mesh_automatic"), "bool", True)
    assert [value for _name, _kind, value in props["mesh_rows"][1:]] == ["N/A", "N/A"]
    fallback = amd.extract_planar_element_properties("pas un dict", {})
    assert fallback["thickness"] == "N/A" and fallback["mesh_rows"] == []


@pytest.mark.parametrize("el, label", [
    ({"elementType": "Plate"}, "Plaque"),
    ({"options": {"kind": "ns::membrane"}}, "Membrane"),
    ({"type": "inconnu"}, None),
])
def test_planar_type_label_from_type_fields_or_nested_strings(el, label):
    assert amd._find_planar_type_label(el) == (label or tr_ui("label_element_planar"))


def test_planar_thickness_and_eccentricity_raw_values():
    assert amd.extract_planar_thickness_eccentricity({"thicknessIn1stVertex": "0.25", "eccentricity": -0.1}) == (0.25, -0.1)
    assert amd.extract_planar_thickness_eccentricity({"thickness": "x", "eccentricity": "y"}) == (0.0, 0.0)
    assert amd.extract_planar_thickness_eccentricity(None) == (0.0, 0.0)


def test_planar_material_takeoff_sums_net_areas_by_material():
    hole = {"geomPtsList": SQUARE, "material": 1, "openings": []}
    rows = amd._build_planar_material_takeoff(
        [hole, {"geomPtsList": SQUARE, "material": {"value": 2}}, {"geomPtsList": SQUARE}, {"geomPtsList": SQUARE[:2]}],
        {1: "C25", 2: "acier"},
    )
    assert [(row["name"], row["area"]) for row in rows] == [("acier", 6.0), ("C25", 6.0), ("N/A", 6.0)]
    assert rows[0]["area_text"] == du.fmt(6.0, "area")


def test_material_density_takes_the_first_numeric_key():
    assert amd._extract_material_density({"rho": "x", "massDensity": "7850"}) == 7850.0
    assert amd._extract_material_density({"Ro": 2500}) == 2500.0
    assert amd._extract_material_density({"name": "C25"}) is None
    assert amd._extract_material_density(None) is None


@pytest.mark.parametrize("value, expected", [
    ("Traction", tr_ui("label_tc_traction")), ("COMPRESSION", tr_ui("label_tc_compression")),
    ("both", "both"), (None, ""), ("  ", ""),
])
def test_tension_compression_behavior_label(value, expected):
    assert amd._format_tc_behavior(value) == expected


@pytest.mark.parametrize("family, value, kind", [
    ("Déplacements", "dz", "section_length"), ("efforts", "MY", "moment"), ("Forces", "fx", "force"),
    ("contraintes", "sv", "stress"), ("autre", "x", ""),
])
def test_result_kind(family, value, kind):
    assert amd._result_kind(family, value) == kind


@pytest.mark.parametrize("data, expected", [
    (None, False), ({}, False), ([], False), ([None, [], {}], False), ([[{"a": 1}]], True), ({"a": 1}, True), (0, True),
])
def test_non_empty_results_data(data, expected):
    assert amd._has_non_empty_results_data(data) is expected


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.parametrize("response, expected", [
    (_Resp({"data": [{"id": 1}]}), True),
    (_Resp({"data": []}), False),
    (_Resp({"data": [{"id": 1}], "details": {"hasErrors": True}}), False),
    (_Resp({"data": [{"id": 1}]}, status=500), False),
    (_Resp(ValueError("pas du json")), False),
    (requests.ConnectionError("down"), False),
])
def test_probe_results_for_element(monkeypatch, response, expected):
    calls = []

    def post(url, params=None, json=None, timeout=None):
        calls.append((url, params, json))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(amd.requests, "post", post)
    assert amd.probe_results_for_element("http://h", 7, 3) is expected
    assert calls == [("http://h/api/Model/analysis/GetResults", {"eResType": "forces", "IDAnalysisCase": 3}, [7])]


def test_results_availability_retries_with_delay(monkeypatch):
    answers = iter([False, False, True])
    sleeps = []
    monkeypatch.setattr(amd, "_probe_results_once", lambda host: next(answers))
    monkeypatch.setattr(amd.time, "sleep", sleeps.append)
    assert amd.diagnose_results_availability("h", retries=3, delay=0.5) is True
    assert sleeps == [0.5, 0.5]
    monkeypatch.setattr(amd, "_probe_results_once", lambda host: False)
    sleeps.clear()
    assert amd.diagnose_results_availability("h") is False
    assert sleeps == []


def _session(close_result=True):
    session = amd.ProjectSessionManager.__new__(amd.ProjectSessionManager)
    session.api = types.SimpleNamespace(close_project=lambda: close_result)
    session.is_open, session.keep_open, session.has_results, session.fto_path = True, True, True, "C:/m.fto"
    return session


def test_session_close_resets_state_only_when_closed():
    session = _session(True)
    assert session.close() is True
    assert (session.is_open, session.keep_open, session.has_results, session.fto_path) == (False, False, False, "")
    session = _session(False)
    assert session.close() is False
    assert session.is_open and session.fto_path == "C:/m.fto"


def test_session_close_without_project_does_not_call_the_api():
    session = _session()
    session.api = types.SimpleNamespace(close_project=lambda: pytest.fail("pas d'appel API"))
    session.is_open, session.fto_path = False, ""
    assert session.close() is False
    assert not session.keep_open and not session.has_results


def test_load_tree_data_survives_api_errors(monkeypatch):
    def boom(*args):
        raise RuntimeError("down")

    monkeypatch.setattr(amd, "get_informational_ids", boom)
    monkeypatch.setattr(amd, "get_element_ids", boom)
    assert amd._read_load_tree_data("h") == {"load_tree": [], "imposed_displacement_counts": {}}
