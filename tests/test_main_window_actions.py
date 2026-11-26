# -*- coding: utf-8 -*-
"""Actions de la fenetre principale : export IFC, lancement du calcul EF et message
d'un chargement en echec (hote simule, sans fenetre reelle)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PySide6")

import main_window as mw
from viewer_config import DEFAULT_HOST, tr_err, tr_log, tr_ui


def _file(tmp_path, name="m.fto"):
    path = tmp_path / name
    path.write_bytes(b"")
    return mw.normalize_windows_path(str(path))


def _session(host, fto_path, is_open=True):
    session = mw.ProjectSessionManager(host, fto_path)
    session.is_open = is_open
    return session


def _host(fto="", typed="http://saisi/", session=None, **attributes):
    host = MagicMock(project_session=session, **attributes)
    host.fto_edit.text.return_value = fto
    host.host_edit.text.return_value = typed
    return host


def _logged(host):
    return [c.args for c in host.log.call_args_list]


# --- export IFC -------------------------------------------------------------
def _export(monkeypatch, host, save_to="out.ifc", exporter=True):
    seen = {"dialog": [], "warning": [], "critical": []}
    monkeypatch.setattr(mw, "ad_ifc_exporter", MagicMock(VERSION="9") if exporter else None)
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a: seen["dialog"].append(a[2]) or (save_to, ""))
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda parent, title, text: seen["warning"].append(text))
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda parent, title, text: seen["critical"].append(text))
    seen["factory"] = MagicMock()
    monkeypatch.setattr(mw, "IfcExportWorker", seen["factory"])
    mw.MainWindow.export_ifc_from_viewer(host)
    return seen


def _ifc_host(*args, **kwargs):
    kwargs.setdefault("_ifc_worker", None)
    host = _host(*args, **kwargs)
    host._viewer_selection_export_eids.return_value = []
    return host


def test_no_second_export_starts_while_one_is_running(monkeypatch):
    host = _host()
    host._ifc_worker.isRunning.return_value = True
    seen = _export(monkeypatch, host)
    assert seen["dialog"] == [] and not seen["factory"].called


def test_a_missing_export_module_is_reported(monkeypatch):
    host = _ifc_host()
    seen = _export(monkeypatch, host, exporter=False)
    assert seen["critical"] == [tr_ui("export_ifc_module_missing")] and seen["dialog"] == []
    assert _logged(host) == [(tr_ui("export_ifc_module_missing"), "error")]


@pytest.mark.parametrize("fto, suggested", [
    (r"C:\a\modele.fto", r"C:\a\modele.ifc"),
    (r"C:\modele.v2.fto", r"C:\modele.v2.ifc"),
    ("", "export.ifc"),
])
def test_the_save_dialog_proposes_the_project_name(monkeypatch, fto, suggested):
    host = _ifc_host(fto)
    seen = _export(monkeypatch, host, save_to="")
    assert seen["dialog"] == [suggested] and not seen["factory"].called
    assert _logged(host) == []


def test_export_without_a_project_nor_a_file_is_refused(monkeypatch):
    host = _ifc_host("")
    seen = _export(monkeypatch, host)
    assert seen["warning"] == [tr_ui("export_ifc_no_project")] and not seen["factory"].called
    assert _logged(host) == [(tr_ui("export_ifc_no_project"), "warn")]


@pytest.mark.parametrize("field, project_name", [("same", "m.fto"), ("empty", "ViewerProject")])
def test_an_open_project_is_exported_from_its_session(monkeypatch, tmp_path, field, project_name):
    fto = _file(tmp_path)
    host = _ifc_host(fto if field == "same" else "", session=_session("http://session", fto))
    seen = _export(monkeypatch, host)
    export_fn, kwargs = seen["factory"].call_args.args
    assert export_fn is mw.ad_ifc_exporter.export_ifc_from_open_project
    assert kwargs == dict(host="http://session", out_path="out.ifc", include_loads=False,
                          project_name=project_name, check_api_first=True, element_ids=None)


@pytest.mark.parametrize("is_open, other", [(False, False), (True, True)])
def test_a_closed_or_different_project_is_exported_from_the_file(monkeypatch, tmp_path, is_open, other):
    fto = _file(tmp_path)
    session = _session("http://session", _file(tmp_path, "autre.fto") if other else fto, is_open)
    host = _ifc_host(fto, session=session)
    host._viewer_selection_export_eids.return_value = [4, 5]
    seen = _export(monkeypatch, host)
    export_fn, kwargs = seen["factory"].call_args.args
    assert export_fn is mw.ad_ifc_exporter.export_ifc_from_fto
    assert kwargs == dict(host="http://session", fto_path=fto, out_path="out.ifc", include_loads=False,
                          check_api_first=True, close_project_on_exit=True, element_ids=[4, 5])
    assert _logged(host) == [
        (tr_ui("export_ifc_scope_selection", count=2), "info"),
        (tr_log("ifc_export_module_version", version="9"), "info"),
        (tr_log("ifc_export_started", path="out.ifc"), "info"),
    ]


@pytest.mark.parametrize("typed, expected", [("http://saisi/", "http://saisi"), ("  ", DEFAULT_HOST.rstrip("/"))])
def test_a_started_export_is_announced_and_connected(monkeypatch, tmp_path, typed, expected):
    host = _ifc_host(_file(tmp_path), typed=typed)
    seen = _export(monkeypatch, host)
    worker = seen["factory"].return_value
    assert seen["factory"].call_args.args[1]["host"] == expected
    assert _logged(host)[0] == (tr_ui("export_ifc_scope_full"), "info")
    host._set_analysis_results_output_message.assert_called_once_with(tr_ui("export_ifc_running"))
    worker.log.connect.assert_called_once_with(host.log)
    worker.error.connect.assert_called_once_with(host._on_ifc_export_error)
    worker.success.connect.call_args.args[0]()
    host._on_ifc_export_success.assert_called_once_with("out.ifc")
    worker.start.assert_called_once_with()


# --- calcul elements finis ----------------------------------------------------
def _calculate(monkeypatch, host, answer=True, control=False):
    seen = {"asked": [], "warning": []}
    yes_no = mw.QMessageBox.Yes if answer else mw.QMessageBox.No
    monkeypatch.setattr(mw.QMessageBox, "question", lambda *a: seen["asked"].append(a[2]) or yes_no)
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda parent, title, text: seen["warning"].append(text))
    modifiers = mw.Qt.ControlModifier if control else mw.Qt.NoModifier
    monkeypatch.setattr(mw.QApplication, "keyboardModifiers", lambda: modifiers)
    seen["factory"] = MagicMock()
    monkeypatch.setattr(mw, "LaunchAnalysisWorker", seen["factory"])
    mw.MainWindow.launch_analysis_from_viewer(host)
    return seen


def _calc_host(*args, **kwargs):
    kwargs.setdefault("calc_worker", None)
    kwargs.setdefault("_calc_done", False)
    return _host(*args, calc_ef_timeout=30, **kwargs)


def test_no_second_calculation_starts_while_one_is_running(monkeypatch, tmp_path):
    host = _host(_file(tmp_path), calc_ef_timeout=30, _calc_done=False)
    host.calc_worker.isRunning.return_value = True
    seen = _calculate(monkeypatch, host)
    assert seen["asked"] == [] and not seen["factory"].called


@pytest.mark.parametrize("done, control, asked", [(True, False, False), (True, True, True), (False, False, True)])
def test_an_up_to_date_model_is_recalculated_only_with_control(monkeypatch, tmp_path, done, control, asked):
    host = _calc_host(_file(tmp_path), _calc_done=done)
    seen = _calculate(monkeypatch, host, answer=asked, control=control)
    assert bool(seen["asked"]) == asked and seen["factory"].called == asked


def test_a_declined_confirmation_starts_nothing(monkeypatch, tmp_path):
    seen = _calculate(monkeypatch, _calc_host(_file(tmp_path)), answer=False)
    assert len(seen["asked"]) == 1 and not seen["factory"].called


def test_calculation_without_a_project_nor_a_file_is_refused(monkeypatch):
    host = _calc_host("")
    seen = _calculate(monkeypatch, host)
    assert seen["warning"] == [tr_ui("calc_ef_no_project")] and not seen["factory"].called
    assert _logged(host) == [(tr_ui("calc_ef_no_project"), "warn")]


def test_calculation_of_a_missing_file_is_refused(monkeypatch, tmp_path):
    missing = mw.normalize_windows_path(str(tmp_path / "absent.fto"))
    host = _calc_host(missing)
    seen = _calculate(monkeypatch, host)
    assert _logged(host) == [(tr_err("file_not_found", path=missing), "error")]
    assert seen["warning"] == [] and not seen["factory"].called


@pytest.mark.parametrize("field", ["same", "empty"])
def test_an_open_project_is_calculated_without_being_reopened(monkeypatch, tmp_path, field):
    fto = _file(tmp_path)
    typed_fto = fto if field == "same" else ""
    host = _calc_host(typed_fto, session=_session("http://session", fto))
    seen = _calculate(monkeypatch, host)
    assert seen["factory"].call_args.args == ("http://saisi", typed_fto, 30, True)
    assert host._calc_launch_fto == fto and host._calc_reload_fto == ""


@pytest.mark.parametrize("is_open, other", [(False, False), (True, True)])
def test_a_closed_or_different_project_is_opened_from_the_file(monkeypatch, tmp_path, is_open, other):
    fto = _file(tmp_path)
    session = _session("http://session", _file(tmp_path, "autre.fto") if other else fto, is_open)
    host = _calc_host(fto, typed="", session=session)
    seen = _calculate(monkeypatch, host)
    assert seen["factory"].call_args.args == (DEFAULT_HOST.rstrip("/"), fto, 30, False)


@pytest.mark.parametrize("tabs", [True, False])
def test_a_started_calculation_locks_the_buttons_and_follows_the_worker(monkeypatch, tmp_path, tabs):
    host = _calc_host(_file(tmp_path))
    if not tabs:
        host.side_tabs = None
    seen = _calculate(monkeypatch, host)
    worker = seen["factory"].return_value
    assert [c.args for c in host._activate_side_tab.call_args_list] == ([(0,)] if tabs else [])
    host.calc_btn.setEnabled.assert_called_once_with(False)
    host.load_btn.setEnabled.assert_called_once_with(False)
    host._start_calc_timer.assert_called_once_with()
    worker.log.connect.assert_called_once_with(host.log)
    worker.success.connect.assert_called_once_with(host._on_calc_success)
    worker.error.connect.assert_called_once_with(host._on_calc_error)
    worker.finished.connect.assert_called_once_with(host._on_calc_finished)
    worker.start.assert_called_once_with()


# --- echec d'un chargement -------------------------------------------------------
@pytest.mark.parametrize("text, keys", [
    (tr_err("licence_open_failed"), ["licence_open_failed"]),
    ("API non joignable sur x:1", ["api_no_response", "api_check_advice"]),
    ("Impossible de contacter l'API Advance Design", ["api_no_response", "api_check_advice"]),
    ("L'API Advance Design ne répond pas", ["api_no_response", "api_check_advice"]),
    ("API non joignable, fichier locked", ["api_no_response", "api_check_advice"]),
    ("Projet déjà ouvert", ["file_already_open_short"]),
    ("Projet deja ouvert", ["file_already_open_short"]),
    ("Fichier verrouillé", ["file_already_open_short"]),
    ("Project ALREADY OPEN", ["file_already_open_short"]),
    ("file is locked", ["file_already_open_short"]),
    ("OpenProject échec API : PROJECT_OPEN_FAILED Engine returned failure ENGINE_ERROR", ["api_engine_not_initialized"]),
])
def test_a_known_load_failure_is_explained(text, keys):
    host = MagicMock()
    mw.MainWindow.on_model_error(host, f"  {text}\n")
    host._reset_after_load_failure.assert_called_once_with()
    assert _logged(host) == [(tr_err(key), "error") for key in keys]
    assert not host._populate_results_case_combination_combo.called


@pytest.mark.parametrize("text", [
    "premiere ligne\nseconde ligne",
    "OpenProject échec API : PROJECT_OPEN_FAILED Engine returned failure",   # sans ENGINE_ERROR
])
def test_an_unknown_load_failure_is_logged_line_by_line(text):
    host = MagicMock()
    mw.MainWindow.on_model_error(host, f"  {text}  ")
    host._populate_results_case_combination_combo.assert_called_once_with([])
    assert _logged(host) == [(tr_err("load_error"), "error")] + [(line, "error") for line in text.splitlines()]
