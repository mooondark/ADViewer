# -*- coding: utf-8 -*-
"""Version du service API (GET /api/Service/GetVersion) : reponse = chaine JSON
brute (pas d'enveloppe {data}), conservee dans les donnees du modele."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import ad_api_client
from ad_model_data import build_model_data


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        import json
        return json.loads(self.text)


def _with_get(fake, fn):
    original = ad_api_client.requests.get
    ad_api_client.requests.get = fake
    try:
        return fn()
    finally:
        ad_api_client.requests.get = original


def _client():
    return ad_api_client.AdvanceDesignApiClient("http://localhost:52000")


def test_get_version_returns_the_plain_json_string_and_calls_the_service_route():
    seen = {}

    def fake(url, timeout=None, **kwargs):
        seen["url"] = url
        return _Resp('"1.27.1"')

    assert _with_get(fake, lambda: _client().get_version()) == "1.27.1"
    assert seen["url"] == "http://localhost:52000/api/Service/GetVersion"


def test_get_version_strips_whitespace_and_non_string_gives_empty():
    assert _with_get(lambda url, timeout=None, **k: _Resp('" 1.27.1 "'), lambda: _client().get_version()) == "1.27.1"
    assert _with_get(lambda url, timeout=None, **k: _Resp('{"data": 1}'), lambda: _client().get_version()) == ""


def test_get_version_raises_api_unavailable_when_unreachable():
    def fake(url, timeout=None, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    try:
        _with_get(fake, lambda: _client().get_version())
    except ad_api_client.ApiUnavailableError:
        return
    raise AssertionError("ApiUnavailableError attendue")


def test_module_level_wrapper_exists():
    assert _with_get(lambda url, timeout=None, **k: _Resp('"1.27.1"'),
                     lambda: ad_api_client.get_api_version("http://localhost:52000")) == "1.27.1"


def test_model_data_keeps_api_version_and_defaults_to_empty():
    assert build_model_data({})["api_version"] == ""
    assert build_model_data({"api_version": None})["api_version"] == ""
    assert build_model_data({"api_version": "1.27.1"})["api_version"] == "1.27.1"


def _run_worker_logs(get_version):
    import ad_model_data

    saved = (ad_model_data.check_port, ad_model_data.get_api_version, ad_model_data.extract_model_geometry)
    ad_model_data.check_port = lambda host: None
    ad_model_data.get_api_version = get_version

    def stop(*args, **kwargs):
        raise RuntimeError("stop")

    ad_model_data.extract_model_geometry = stop
    try:
        worker = ad_model_data.LoadModelWorker("http://localhost:52000", r"C:\x.fto")
        logs = []
        worker.log.connect(lambda text, level: logs.append((text, level)))
        worker.run()
        return [t for t, _ in logs]
    finally:
        ad_model_data.check_port, ad_model_data.get_api_version, ad_model_data.extract_model_geometry = saved


def test_loading_logs_the_api_version_right_after_api_accessible():
    from viewer_config import tr_log, tr_ui

    logs = _run_worker_logs(lambda host: "1.27.1")
    i = logs.index(tr_log("api_ok"))
    assert logs[i + 1] == f"{tr_ui('status_section_api_version')} : 1.27.1"
    assert logs[i + 2] == tr_log("normalized_path", path=r"C:\x.fto")


def test_version_is_read_once_and_handed_to_extract_model_geometry():
    import ad_model_data

    calls = []
    seen = {}

    def fake_get_version(host):
        calls.append(host)
        return "1.27.1"

    def fake_extract(*args, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop")

    saved = (ad_model_data.check_port, ad_model_data.get_api_version, ad_model_data.extract_model_geometry)
    ad_model_data.check_port = lambda host: None
    ad_model_data.get_api_version = fake_get_version
    ad_model_data.extract_model_geometry = fake_extract
    try:
        ad_model_data.LoadModelWorker("http://localhost:52000", r"C:\x.fto").run()
    finally:
        ad_model_data.check_port, ad_model_data.get_api_version, ad_model_data.extract_model_geometry = saved
    assert len(calls) == 1
    assert seen.get("api_version") == "1.27.1"


def test_extract_model_geometry_does_not_refetch_a_provided_version():
    import inspect
    import ad_model_data

    params = inspect.signature(ad_model_data.extract_model_geometry).parameters
    assert "api_version" in params and params["api_version"].default is None


def test_loading_continues_without_version_line_when_version_unavailable():
    from viewer_config import tr_log

    def boom(host):
        raise RuntimeError("down")

    logs = _run_worker_logs(boom)
    i = logs.index(tr_log("api_ok"))
    assert logs[i + 1] == tr_log("normalized_path", path=r"C:\x.fto")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
