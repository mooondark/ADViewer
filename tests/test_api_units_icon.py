# -*- coding: utf-8 -*-
"""Appels de resultats et de maillage de l'API, restauration des unites
depuis config.ini, chargement de l'icone de l'application."""

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_api_client
import display_units as du
from viewer_config import ApiUnavailableError


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Calls(list):
    replies: dict


@pytest.fixture
def posts(monkeypatch):
    calls = _Calls()
    replies = {"payload": {"data": [{"id": 1}]}}

    def post(url, json=None, params=None, timeout=None):
        calls.append({"url": url, "json": json, "params": params, "timeout": timeout})
        return _Resp(replies["payload"])

    monkeypatch.setattr(ad_api_client.requests, "post", post)
    calls.replies = replies
    return calls


def test_get_results_sends_the_valid_ids_with_type_and_case(posts):
    client = ad_api_client.AdvanceDesignApiClient("http://h/")
    assert client.get_results("forces", "3", [5, None, "6"]) == [{"id": 1}]
    assert posts == [{"url": "http://h/api/Model/analysis/GetResults", "json": [5, 6],
                      "params": {"eResType": "forces", "IDAnalysisCase": 3}, "timeout": 60}]


def test_get_results_without_ids_does_not_call_the_api_and_null_data_is_empty(posts):
    client = ad_api_client.AdvanceDesignApiClient("http://h")
    assert client.get_results("forces", 3, [None]) == []
    assert posts == []
    posts.replies["payload"] = {"data": None}
    assert client.get_results("forces", 3, [1]) == []


def test_mesh_connectivity_payload_and_empty_data(posts):
    client = ad_api_client.AdvanceDesignApiClient("http://h")
    assert client.get_mesh_connectivity([7, None]) == [{"id": 1}]
    assert posts[-1]["json"] == [7] and posts[-1]["url"].endswith("/GetMeshConnectivity")
    posts.replies["payload"] = {}
    assert client.get_mesh_connectivity() == []
    assert posts[-1]["json"] == []


def test_module_level_wrappers_use_the_client(posts):
    assert ad_api_client.get_results("http://h", "stresses", 2, [1]) == [{"id": 1}]
    assert ad_api_client.get_mesh_connectivity("http://h", [1]) == [{"id": 1}]
    assert [call["url"].rsplit("/", 1)[-1] for call in posts] == ["GetResults", "GetMeshConnectivity"]


def test_post_turns_a_network_error_into_api_unavailable(monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(ad_api_client.requests, "post", down)
    with pytest.raises(ApiUnavailableError):
        ad_api_client.AdvanceDesignApiClient("http://h").get_results("forces", 1, [1])


def test_post_sends_an_empty_object_without_payload(posts):
    ad_api_client.AdvanceDesignApiClient("http://h")._post("/api/x")
    assert posts[-1]["json"] == {} and posts[-1]["timeout"] == 30


@pytest.fixture
def _units():
    du.reset()
    yield
    du.reset()


def test_units_state_is_restored_from_ini_with_checks(_units):
    other = [u for u in du.units_for("force") if u != du.unit("force")][0]
    length_before = (du.unit("length"), du.decimals("length"))
    du.load_state_ini({"force_unit": other, "force_decimals": "9", "length_unit": "parsec", "length_decimals": "x",
                       "moment_decimals": "-2"})
    assert du.unit("force") == other and du.decimals("force") == 6   # borne haute
    assert (du.unit("length"), du.decimals("length")) == length_before   # unite inconnue, decimales invalides
    assert du.decimals("moment") == 0   # borne basse
    before = du.get_state_ini()
    du.load_state_ini(None)
    assert du.get_state_ini() == before


def test_app_icon_takes_the_first_existing_valid_file(tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    import viewer_config

    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        pytest.skip("une QCoreApplication existe deja dans ce processus")
    png = tmp_path / "icon.png"
    image = QImage(4, 4, QImage.Format_ARGB32)
    image.fill(0xFF00FF00)
    image.save(str(png))
    not_an_image = tmp_path / "bad.png"
    not_an_image.write_text("pas une image")
    assert viewer_config.load_app_icon(None, str(tmp_path / "absent.png"), str(not_an_image)).isNull()
    assert not viewer_config.load_app_icon("", str(not_an_image), str(png)).isNull()
