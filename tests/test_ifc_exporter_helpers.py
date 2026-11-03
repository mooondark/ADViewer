# -*- coding: utf-8 -*-
"""Export IFC : verifications d'entree (API, fichier .fto), lecture des
materiaux et sections, appuis exportes, solides par sections successives."""

import os
import sys
import types

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_ifc_exporter as ifc
from ad_ifc_exporter import IfcWriter


@pytest.mark.parametrize("v", [(0, 0, 1), (1, 0, 0), (0, 1, 0), (1, 2, 3), (-3, 0.5, 0.2)])
def test_any_perp_is_a_unit_vector_orthogonal_to_v(v):
    p = ifc.any_perp(list(v))
    assert sum(a * b for a, b in zip(p, v)) == pytest.approx(0.0, abs=1e-12)
    assert sum(c * c for c in p) == pytest.approx(1.0)


@pytest.mark.parametrize("ad_type, name", [
    ("ElementRigidPunctualSupport", "PunctualSupport"), ("ElementElasticLinearSupport", "LinearSupport"),
    ("ElementRigidPlanarSupport", "PlanarSupport"), ("Autre", "Support"),
])
def test_support_kind_name(ad_type, name):
    assert ifc.support_kind_name(ad_type) == name


def test_fto_path_is_cleaned_and_must_be_a_readable_file(tmp_path):
    fto = tmp_path / "modele.fto"
    fto.write_text("x")
    assert ifc.check_fto_path(f'  "{fto}" ') == os.path.abspath(str(fto))
    with pytest.raises(FileNotFoundError):
        ifc.check_fto_path(str(tmp_path / "absent.fto"))
    with pytest.raises(FileNotFoundError):
        ifc.check_fto_path(str(tmp_path))


def test_check_port_uses_the_scheme_default_port(monkeypatch):
    opened = []
    monkeypatch.setattr(ifc.socket, "create_connection",
                        lambda addr, timeout: opened.append(addr) or types.SimpleNamespace(close=lambda: None))
    ifc.check_port("http://localhost:52000")
    ifc.check_port("https://serveur")
    ifc.check_port("http://serveur")
    assert opened == [("localhost", 52000), ("serveur", 443), ("serveur", 80)]


def test_check_port_reports_invalid_or_unreachable_api(monkeypatch):
    with pytest.raises(ifc.ApiUnavailableError):
        ifc.check_port("pas une url")

    def refused(addr, timeout):
        raise OSError("refused")

    monkeypatch.setattr(ifc.socket, "create_connection", refused)
    with pytest.raises(ifc.ApiUnavailableError):
        ifc.check_port("http://localhost:1")


def test_api_post_turns_network_errors_into_api_unavailable(monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(ifc.requests, "post", down)
    with pytest.raises(ifc.ApiUnavailableError):
        ifc.api_post("http://h", "/api/x")


@pytest.mark.parametrize("reader, list_endpoint", [("get_materials", "GetListMaterials"), ("get_sections", "GetListSections")])
def test_materials_and_sections_are_keyed_by_eid_without_empty_items(monkeypatch, reader, list_endpoint):
    posted = []
    monkeypatch.setattr(ifc, "api_get", lambda host, endpoint: {"data": [1, 2, 3]} if endpoint.endswith(list_endpoint) else {})
    monkeypatch.setattr(ifc, "api_post", lambda host, endpoint, ids: posted.append(ids) or {"data": [{"n": "a"}, None, {"n": "c"}]})
    assert getattr(ifc, reader)("h") == {1: {"n": "a"}, 3: {"n": "c"}}
    assert posted == [[1, 2, 3]]
    monkeypatch.setattr(ifc, "api_get", lambda host, endpoint: {"data": None})
    assert getattr(ifc, reader)("h") == {}


def test_emit_log_accepts_one_or_two_argument_loggers_and_ignores_failures():
    two, one = [], []
    ifc.emit_log(lambda message, level: two.append((message, level)), "a", "ok")
    ifc.emit_log(lambda message: one.append(message), "b")
    ifc.emit_log(lambda message, level: 1 / 0, "c")
    ifc.emit_log(None, "d")
    assert two == [("a", "ok")] and one == ["b"]


def test_export_from_fto_checks_opens_exports_and_closes(monkeypatch, tmp_path):
    fto = tmp_path / "m.fto"
    fto.write_text("x")
    steps = []
    monkeypatch.setattr(ifc, "check_port", lambda host: steps.append(("check", host)))
    monkeypatch.setattr(ifc, "open_project", lambda host, path: steps.append(("open", path)))
    monkeypatch.setattr(ifc, "close_project", lambda host: steps.append(("close", host)))

    def core(host, out_path, **kwargs):
        steps.append(("export", out_path, kwargs["project_name"]))
        raise RuntimeError("export rate")

    monkeypatch.setattr(ifc, "export_ifc_core", core)
    with pytest.raises(RuntimeError):
        ifc.export_ifc_from_fto("http://h/", str(fto), "out.ifc")
    assert steps == [("check", "http://h"), ("open", str(fto)), ("export", "out.ifc", "m.fto"), ("close", "http://h")]

    steps.clear()
    monkeypatch.setattr(ifc, "export_ifc_core", lambda host, out_path, **kwargs: {"ok": True})
    assert ifc.export_ifc_from_fto("http://h", str(fto), "o.ifc", check_api_first=False, close_project_on_exit=False) == {"ok": True}
    assert steps == [("open", str(fto))]


def _pset(w, product):
    for rel in w.model.by_type("IfcRelDefinesByProperties"):
        if product in rel.RelatedObjects:
            props = rel.RelatingPropertyDefinition.HasProperties
            return {p.Name: (p.NominalValue.wrappedValue if p.NominalValue is not None else None) for p in props}
    return None


@pytest.mark.parametrize("add, el", [
    (ifc.add_punctual_support, {"geomPt": {"x": 1, "y": 2}}),
    (ifc.add_linear_support, {"geomPtStart": {"x": 0}, "geomPtEnd": {"x": 2}}),
    (ifc.add_planar_support, {"geomPtsList": [{"x": 0}, {"x": 1}, {"x": 1, "y": 1}]}),
])
def test_supports_are_exported_with_their_restraints(add, el):
    w = IfcWriter()
    w.setup()
    add(w, {**el, "userID": 4, "type": "ElementRigidSupport", "restraints": {"tx": True, "rz": False}})
    product = w.contained[-1]
    assert product.Name == "Support_4" and product.is_a("IfcBuildingElementProxy")
    pset = _pset(w, product)
    assert pset["AD_ConstraintsType"] == "Rigid" and pset["AD_Tx"] is True and pset["AD_Rz"] is False


def test_planar_support_with_less_than_three_points_is_skipped():
    w = IfcWriter()
    ifc.add_planar_support(w, {"geomPtsList": [{"x": 0}, {"x": 1}]})
    assert w.contained == []


def test_material_entities_are_created_once_per_name():
    w = IfcWriter()
    first = w.ensure_material(" S235 ")
    assert w.ensure_material("S235") is first and first.Name == "S235"
    assert w.ensure_material("") is None and w.ensure_material("   ") is None and w.ensure_material(None) is None


def test_loft_brep_closes_the_solid_and_shares_points():
    w = IfcWriter()
    square = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    brep = w.loft_brep_item([square, [(x, y, 2) for x, y, _ in square]])
    faces = brep.Outer.CfsFaces
    assert brep.is_a("IfcFacetedBrep") and len(faces) == 2 + 4
    points = {p.id() for face in faces for p in face.Bounds[0].Bound.Polygon}
    assert len(points) == 8
