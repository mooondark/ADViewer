# -*- coding: utf-8 -*-
"""Refus d'une version d'API trop ancienne : journal, boite de dialogue et branchements."""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PySide6")

import main_window as mw
from viewer_config import tr_ui


def test_refusal_is_logged_and_shown_in_a_dialog(monkeypatch):
    shown, logs = [], []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda parent, title, text: shown.append((title, text)))
    host = types.SimpleNamespace(log=lambda text, level="info": logs.append((level, text)))
    mw.MainWindow._on_api_version_refused(host, "ligne 1\nligne 2")
    assert logs == [("error", "ligne 1"), ("error", "ligne 2")]
    assert shown == [(tr_ui("api_version_title"), "ligne 1\nligne 2")]


def test_refused_load_resets_the_state_like_other_load_errors():
    host = MagicMock()
    mw.MainWindow.on_model_version_refused(host, "refus")
    host._reset_after_load_failure.assert_called_once_with()
    host._on_api_version_refused.assert_called_once_with("refus")


def test_load_model_connects_the_refusal(monkeypatch, tmp_path):
    fto = tmp_path / "m.fto"
    fto.write_bytes(b"")
    host = MagicMock(cmb_display_mode=None, viewer=None)
    host.fto_edit.text.return_value = str(fto)
    host.host_edit.text.return_value = "http://h"
    factory = MagicMock()
    monkeypatch.setattr(mw, "LoadModelWorker", factory)
    mw.MainWindow.load_model(host)
    factory.return_value.version_refused.connect.assert_called_once_with(host.on_model_version_refused)


def test_calculation_connects_the_refusal(monkeypatch, tmp_path):
    fto = tmp_path / "m.fto"
    fto.write_bytes(b"")
    host = MagicMock(calc_worker=None, _calc_done=False, project_session=None)
    host.fto_edit.text.return_value = str(fto)
    host.host_edit.text.return_value = "http://h"
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a: mw.QMessageBox.Yes)
    factory = MagicMock()
    monkeypatch.setattr(mw, "LaunchAnalysisWorker", factory)
    mw.MainWindow.launch_analysis_from_viewer(host)
    factory.return_value.version_refused.connect.assert_called_once_with(host._on_api_version_refused)


def _run_ifc_worker():
    exported, done, refusals, errors = [], [], [], []
    worker = mw.IfcExportWorker(lambda logger=None, **kwargs: exported.append(kwargs), {"host": "http://h"})
    worker.success.connect(lambda: done.append(True))
    worker.version_refused.connect(refusals.append)
    worker.error.connect(errors.append)
    worker.run()
    return exported, done, refusals, errors


def test_ifc_export_runs_with_a_supported_version(monkeypatch):
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: "")
    assert _run_ifc_worker() == ([{"host": "http://h"}], [True], [], [])


def test_ifc_export_is_refused_before_exporting(monkeypatch):
    monkeypatch.setattr(mw, "check_port", lambda host: None)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: f"{host} {consequence_key}")
    assert _run_ifc_worker() == ([], [], ["http://h api_version_refused_ifc"], [])


def test_ifc_export_reports_an_unreachable_api_as_such(monkeypatch):
    def down(host):
        raise mw.ApiUnavailableError("API non joignable")

    monkeypatch.setattr(mw, "check_port", down)
    monkeypatch.setattr(mw, "check_api_version", lambda host, consequence_key: "version inconnue")
    assert _run_ifc_worker() == ([], [], [], ["API non joignable"])


def test_ifc_refusal_replaces_the_running_message():
    host = MagicMock()
    mw.MainWindow._on_ifc_version_refused(host, "refus")
    host._set_analysis_results_output_message.assert_called_once_with("refus")
    host._on_api_version_refused.assert_called_once_with("refus")


def test_ifc_export_without_session_uses_the_typed_api_address(monkeypatch, tmp_path):
    host = MagicMock(_ifc_worker=None, project_session=None)
    host.fto_edit.text.return_value = str(tmp_path / "m.fto")
    host.host_edit.text.return_value = "http://autre:1234/"
    host._viewer_selection_export_eids.return_value = []
    monkeypatch.setattr(mw, "ad_ifc_exporter", MagicMock())
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a: (str(tmp_path / "m.ifc"), ""))
    factory = MagicMock()
    monkeypatch.setattr(mw, "IfcExportWorker", factory)
    mw.MainWindow.export_ifc_from_viewer(host)
    assert factory.call_args.args[1]["host"] == "http://autre:1234"
    factory.return_value.version_refused.connect.assert_called_once_with(host._on_ifc_version_refused)
