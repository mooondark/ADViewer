# -*- coding: utf-8 -*-
"""Appels HTTP du client API : chemin, corps, delai et libelle d'erreur de chaque requete de lecture/fermeture."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import ad_api_client
from ad_api_client import AdvanceDesignApiClient

HOST = "http://h:1"
OK = {"details": {"success": True}, "data": ["x"]}
FAIL = {"details": {"success": False, "diagnostics": [{"message": "boom"}]}}


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Posts(list):
    """Requetes POST enregistrees ; `payload` est la reponse que renvoie l'API simulee."""
    payload = OK


@pytest.fixture
def posts(monkeypatch):
    calls = _Posts()

    def fake_post(url, json=None, params=None, timeout=None):
        calls.append({"url": url, "json": json, "params": params, "timeout": timeout})
        return _Resp(calls.payload)

    monkeypatch.setattr(ad_api_client.requests, "post", fake_post)
    return calls


def _client():
    return AdvanceDesignApiClient(HOST)


# (appel, chemin, corps attendu, delai, libelle d'erreur)
LISTS = [
    (lambda c: c.get_elements_objects([1, 2]), "/api/Model/elements/GetElementsObject", [1, 2], 60, "GetElementsObject"),
    (lambda c: c.get_materials([1, 2]), "/api/Model/materials/GetMaterials", [1, 2], 30, "GetMaterials"),
    (lambda c: c.get_sections([1, 2]), "/api/Model/sections/GetSections", [1, 2], 30, "GetSections"),
    (lambda c: c.get_informational_elements_objects([1, 2]), "/api/Model/elements/GetInformationalElementsObject",
     [1, 2], 60, "GetInformationalElementsObject"),
]
IDS = [
    (lambda c: c.get_element_ids("BEAM"), [{"$type": "QueryElementsModel", "elementType": "BEAM"}], "GetElementsID(BEAM)"),
    (lambda c: c.get_informational_ids("GRID"), [{"$type": "QueryInfoModel", "informationalElementType": "GRID"}],
     "GetElementsID(GRID)"),
    (lambda c: c.get_element_ids_for_types(["A", "B"]),
     [{"$type": "QueryElementsModel", "elementType": "A"}, {"$type": "QueryElementsModel", "elementType": "B"}],
     "GetElementsID(A, B)"),
]


@pytest.mark.parametrize("call, path, body, timeout, label", LISTS)
def test_list_requests_post_the_ids_and_return_the_data(posts, call, path, body, timeout, label):
    assert call(_client()) == ["x"]
    assert posts == [{"url": HOST + path, "json": body, "params": None, "timeout": timeout}]


@pytest.mark.parametrize("method", ["get_elements_objects", "get_materials", "get_sections",
                                    "get_informational_elements_objects"])
def test_list_requests_skip_the_network_for_no_ids(posts, method):
    assert getattr(_client(), method)([]) == [] and posts == []


@pytest.mark.parametrize("call, path, body, timeout, label", LISTS)
def test_list_requests_name_themselves_in_api_errors(posts, call, path, body, timeout, label):
    posts.payload = FAIL
    with pytest.raises(RuntimeError, match=label):
        call(_client())


@pytest.mark.parametrize("call, body, label", IDS)
def test_id_requests_query_elements_id_and_return_the_data(posts, call, body, label):
    assert call(_client()) == ["x"]
    assert posts == [{"url": HOST + "/api/Model/elements/GetElementsID", "json": body, "params": None, "timeout": 30}]


@pytest.mark.parametrize("call, body, label", IDS)
def test_id_requests_name_themselves_in_api_errors(posts, call, body, label):
    posts.payload = FAIL
    with pytest.raises(RuntimeError, match=label.replace("(", r"\(").replace(")", r"\)")):
        call(_client())


@pytest.mark.parametrize("method, path", [("close_project", "/api/Model/management/CloseProject"),
                                          ("close_session", "/api/Model/management/CloseSession")])
def test_close_requests_report_success_and_swallow_failures(posts, monkeypatch, method, path):
    assert getattr(_client(), method)() is True
    assert posts == [{"url": HOST + path, "json": {}, "params": None, "timeout": 15}]
    posts.payload = FAIL
    assert getattr(_client(), method)() is False

    def down(*a, **k):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(ad_api_client.requests, "post", down)
    assert getattr(_client(), method)() is False


def test_one_type_gives_the_same_request_as_get_element_ids(posts):
    client = _client()
    client.get_element_ids("BEAM")
    client.get_element_ids_for_types(["BEAM"])
    assert posts[0] == posts[1]


def test_no_types_means_no_request(posts):
    assert _client().get_element_ids_for_types([]) == [] and posts == []
