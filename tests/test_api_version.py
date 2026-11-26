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
from viewer_config import tr_err


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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")


def test_licence_problem_only_when_can_run_is_false():
    bad = lambda url, timeout=None, **k: _Resp('{"canRun": false, "status": "Licence_Unavailable", "message": "No seat"}')
    ok = lambda url, timeout=None, **k: _Resp('{"canRun": true, "status": "Ok"}')
    assert _with_get(bad, lambda: _client().licence_problem())["message"] == "No seat"
    assert _with_get(ok, lambda: _client().licence_problem()) is None

    def down(url, timeout=None, **kwargs):
        raise requests.exceptions.ConnectionError("down")

    assert _with_get(down, lambda: _client().licence_problem()) is None


def _refusal(version_text):
    return tr_err("api_version_refused", version=version_text, minimum="1.27.1",
                  consequence=tr_err("api_version_refused_load"))


def test_supported_api_versions_are_accepted():
    for version in ("1.27.1", "1.27.1.0", "1.27.10", "1.28", "2.0"):
        assert ad_api_client.api_version_refusal(version, "api_version_refused_load") == "", version


def test_old_api_version_is_refused_with_detected_and_minimum_version():
    for version in ("1.27", "1.27.0", "1.27.0.9", "1.9.9"):
        assert ad_api_client.api_version_refusal(version, "api_version_refused_load") == _refusal(version), version


def test_missing_or_unreadable_api_version_is_refused_as_unknown():
    for version in ("", None, "1.27.1-beta", "v1.28", "1..28", "abc"):
        message = ad_api_client.api_version_refusal(version, "api_version_refused_load")
        assert message == _refusal(tr_err("api_version_unknown")), version


def test_api_without_get_version_route_is_refused_as_unknown():
    message = _with_get(lambda url, timeout=None, **k: _Resp("Not Found", 404),
                        lambda: ad_api_client.check_api_version("http://localhost:52000", "api_version_refused_load"))
    assert message == _refusal(tr_err("api_version_unknown"))


def test_loading_is_refused_before_opening_the_project(monkeypatch):
    import ad_model_data

    def down(host):
        raise RuntimeError("down")

    opened = []
    monkeypatch.setattr(ad_model_data, "check_port", lambda host: None)
    monkeypatch.setattr(ad_model_data, "licence_problem", lambda host: None)
    monkeypatch.setattr(ad_model_data, "extract_model_geometry", lambda *a, **k: opened.append(a))
    for get_version in (lambda host: "1.27.0", lambda host: "", down):
        monkeypatch.setattr(ad_model_data, "get_api_version", get_version)
        worker = ad_model_data.LoadModelWorker("http://localhost:52000", r"C:\x.fto")
        refusals, errors = [], []
        worker.version_refused.connect(refusals.append)
        worker.error.connect(errors.append)
        worker.run()
        assert len(refusals) == 1 and errors == [] and opened == []
