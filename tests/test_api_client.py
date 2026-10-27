# -*- coding: utf-8 -*-
"""Couche HTTP : traduction des reponses en erreurs, detection 'projet deja ouvert',
check_port sur hote non resolu."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import ad_api_client
from viewer_config import ApiUnavailableError, ProjectAlreadyOpenError


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_check_returns_data_on_success():
    assert ad_api_client._check(_Resp({"details": {"success": True}, "data": [1]}), "X")["data"] == [1]


def test_check_raises_on_http_error():
    with pytest.raises(RuntimeError):
        ad_api_client._check(_Resp({"x": 1}, status=500), "X")


def test_check_raises_on_api_failure():
    resp = _Resp({"details": {"success": False, "diagnostics": [{"message": "boom"}]}})
    with pytest.raises(RuntimeError, match="boom"):
        ad_api_client._check(resp, "GetResults")


@pytest.mark.parametrize("message", [
    "The file is already open", "Le fichier est déjà ouvert",
    "being used by another process",
])
def test_check_detects_project_already_open(message):
    resp = _Resp({"details": {"success": False, "diagnostics": [{"message": message}]}})
    with pytest.raises(ProjectAlreadyOpenError):
        ad_api_client._check(resp, "OpenProject")


def test_already_open_only_for_open_project():
    resp = _Resp({"details": {"success": False, "diagnostics": [{"message": "already open"}]}})
    with pytest.raises(RuntimeError) as exc:
        ad_api_client._check(resp, "GetResults")
    assert not isinstance(exc.value, ProjectAlreadyOpenError)


_WARNING = {"severity": "Warning", "code": "ENGINE_WARNING", "message": "Element 217 ignore", "source": "Analysis"}
_ERROR = {"severity": "Error", "code": "ENGINE_ERROR", "message": "Filaire 191 non connecte", "source": "Analysis"}


def test_launch_analysis_returns_diagnostics_instead_of_raising(monkeypatch):
    payload = {"details": {"success": False, "diagnostics": [_WARNING, _ERROR]}, "data": False}
    monkeypatch.setattr(ad_api_client.requests, "post", lambda *a, **k: _Resp(payload))
    ok, diagnostics = ad_api_client.AdvanceDesignApiClient("http://h").launch_analysis()
    assert ok is False
    assert diagnostics == [("warning", "Element 217 ignore"), ("error", "Filaire 191 non connecte")]


def test_launch_analysis_still_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(ad_api_client.requests, "post", lambda *a, **k: _Resp({"x": 1}, status=500))
    with pytest.raises(RuntimeError):
        ad_api_client.AdvanceDesignApiClient("http://h").launch_analysis()


def test_check_port_unresolvable_host_is_api_unavailable():
    with pytest.raises(ApiUnavailableError):
        ad_api_client.check_port("http://hote-inexistant.invalid:52000")
