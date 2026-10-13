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


def test_check_port_unresolvable_host_is_api_unavailable():
    with pytest.raises(ApiUnavailableError):
        ad_api_client.check_port("http://hote-inexistant.invalid:52000")
