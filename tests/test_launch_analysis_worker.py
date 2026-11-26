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
