# -*- coding: utf-8 -*-
"""Calcul EF : diagnostics de l'API ecrits un par ligne dans le journal, et
verdict de reussite lu dans le statut d'analyse (femIsCalculated) en fin de calcul."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PySide6")

import main_window as mw


def _run(monkeypatch, data, diagnostics, status):
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: "")
    monkeypatch.setattr(mw, "open_project", lambda host, path: None)
    monkeypatch.setattr(mw, "close_project", lambda host: None)
    monkeypatch.setattr(mw, "launch_analysis", lambda host, timeout=None: (data, diagnostics))
    if isinstance(status, Exception):
        def failing(host):
            raise status
        monkeypatch.setattr(mw, "get_analysis_model_status", failing)
    else:
        monkeypatch.setattr(mw, "get_analysis_model_status", lambda host: status)
    worker = mw.LaunchAnalysisWorker("http://h", "", 0, reuse_open_project=True)
    logs, results, errors = [], [], []
    worker.log.connect(lambda msg, level: logs.append((level, msg)))
    worker.success.connect(lambda ok, elapsed: results.append(ok))
    worker.error.connect(errors.append)
    worker.run()
    return logs, results, errors


def test_errors_reported_by_api_but_status_calculated_is_a_success(monkeypatch):
    diagnostics = [("warning", "Element 217 ignore"), ("error", "Filaire 191 non connecte")]
    logs, results, errors = _run(monkeypatch, False, diagnostics, {"femIsCalculated": True})
    assert ("warn", "Element 217 ignore") in logs
    assert ("error", "Filaire 191 non connecte") in logs
    assert results == [True] and errors == []


def test_status_not_calculated_is_a_failure_even_if_api_flag_true(monkeypatch):
    _logs, results, _errors = _run(monkeypatch, True, [], {"femIsCalculated": False})
    assert results == [False]


def test_unreadable_status_falls_back_to_api_flag(monkeypatch):
    _logs, results, _errors = _run(monkeypatch, True, [], RuntimeError("down"))
    assert results == [True]


def _run_closed_project(monkeypatch, launch, close=None):
    """Projet a ouvrir par le worker ; rend les appels, les erreurs et les succes."""
    calls = []
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: "")
    monkeypatch.setattr(mw, "open_project", lambda host, path: calls.append(("open", host, path)))
    monkeypatch.setattr(mw, "close_project", close or (lambda host: calls.append(("close", host))))
    monkeypatch.setattr(mw, "launch_analysis", launch)
    monkeypatch.setattr(mw, "get_analysis_model_status", lambda host: {"femIsCalculated": True})
    worker = mw.LaunchAnalysisWorker("http://h/", r"C:\x.fto", 12, reuse_open_project=False)
    errors, results = [], []
    worker.error.connect(errors.append)
    worker.success.connect(lambda ok, elapsed: results.append(ok))
    worker.run()
    return calls, errors, results


def test_a_closed_project_is_opened_for_the_calculation_then_closed(monkeypatch):
    seen = []
    calls, errors, results = _run_closed_project(
        monkeypatch, lambda host, timeout=None: seen.append(timeout) or (True, []))
    assert calls == [("open", "http://h", r"C:\x.fto"), ("close", "http://h")]
    assert seen == [12] and errors == [] and results == [True]


@pytest.mark.parametrize("failure, expected", [
    (mw.requests.Timeout(), "calc_ef_timeout_exceeded"),
    (mw.requests.ConnectionError("coupee"), "calc_ef_connection_lost"),
    (ValueError("boum"), None),
])
def test_a_failed_calculation_reports_it_and_still_closes_the_project(monkeypatch, failure, expected):
    def launch(host, timeout=None):
        raise failure

    monkeypatch.setattr(mw.time, "monotonic", lambda: 100.0)
    calls, errors, results = _run_closed_project(monkeypatch, launch)
    message = {
        "calc_ef_timeout_exceeded": mw.tr_log("calc_ef_timeout_exceeded", elapsed=mw._fmt_hms(0.0), timeout=12),
        "calc_ef_connection_lost": mw.tr_log("calc_ef_connection_lost", details="coupee"),
        None: "boum",
    }[expected]
    assert errors == [message] and results == []
    assert calls[-1] == ("close", "http://h")


def test_the_elapsed_calculation_time_comes_with_the_result(monkeypatch):
    clock = iter([100.0, 142.5])
    monkeypatch.setattr(mw.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: "")
    monkeypatch.setattr(mw, "launch_analysis", lambda host, timeout=None: (True, []))
    monkeypatch.setattr(mw, "get_analysis_model_status", lambda host: {"femIsCalculated": True})
    worker = mw.LaunchAnalysisWorker("http://h", "", 0, reuse_open_project=True)
    results = []
    worker.success.connect(lambda ok, elapsed: results.append((ok, elapsed)))
    worker.run()
    assert results == [(True, 42.5)]


def test_a_project_that_cannot_be_closed_does_not_hide_the_result(monkeypatch):
    def close(host):
        raise RuntimeError("fermeture impossible")

    _calls, errors, results = _run_closed_project(monkeypatch, lambda host, timeout=None: (True, []), close=close)
    assert errors == [] and results == [True]


def test_refused_api_version_neither_opens_nor_calculates(monkeypatch):
    calls = []
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: consequence_key)
    for name in ("open_project", "close_project", "launch_analysis"):
        monkeypatch.setattr(mw, name, lambda *a, _name=name, **k: calls.append(_name))
    for reuse in (False, True):
        worker = mw.LaunchAnalysisWorker("http://h", r"C:\x.fto", 0, reuse_open_project=reuse)
        refusals, results, errors = [], [], []
        worker.version_refused.connect(refusals.append)
        worker.success.connect(lambda ok, elapsed: results.append(ok))
        worker.error.connect(errors.append)
        worker.run()
        assert refusals == ["api_version_refused_calc"]
        assert calls == [] and results == [] and errors == []
