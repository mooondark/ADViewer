# -*- coding: utf-8 -*-
"""Chargement d'un modele (LoadModelWorker.run) : journal, progression et signaux
emis selon la reponse de l'API."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("PySide6")

import ad_model_data
from viewer_config import ApiUnavailableError, ProjectAlreadyOpenError, tr_err, tr_log, tr_ui

HOST, PATH = "http://localhost:52000", r"C:\x.fto"


def _run(monkeypatch, extract, licence=None):
    monkeypatch.setattr(ad_model_data, "check_port", lambda host: None)
    monkeypatch.setattr(ad_model_data, "licence_problem", lambda host: licence)
    monkeypatch.setattr(ad_model_data, "get_api_version", lambda host: "1.27.1")
    monkeypatch.setattr(ad_model_data, "extract_model_geometry", extract)
    worker = ad_model_data.LoadModelWorker(HOST, PATH)
    seen = {"log": [], "progress": [], "success": [], "error": []}
    worker.log.connect(lambda text, level: seen["log"].append((text, level)))
    worker.progress.connect(lambda value, message: seen["progress"].append((value, message)))
    worker.success.connect(seen["success"].append)
    worker.error.connect(seen["error"].append)
    worker.run()
    return seen


def _model(**values):
    return {**ad_model_data.build_model_data({}), **values}


_COUNTS = dict(
    linear_ids_count=1, planar_ids_count=2, load_area_ids_count=3, punctual_support_ids_count=4,
    punctual_load_ids_count=5, linear_load_ids_count=6, planar_load_ids_count=7, linear_support_ids_count=8,
    planar_support_ids_count=9, materials_resolved_count=10, materials_eids_count=11,
    linear_sections_resolved_count=12, linear_section_eids_count=13, linear_count=14, planar_count=15,
    load_area_count=16, openings_count=17, punctual_support_count=18, linear_support_count=19, planar_support_count=20,
)


@pytest.mark.parametrize("state, state_logs", [
    ({"project_kept_open": True, "project_closed": True}, ["project_kept_open_for_results"]),
    ({"project_kept_open": False, "project_closed": True}, ["project_closed_after_read"]),
    ({"project_kept_open": False, "project_closed": False}, []),
])
@pytest.mark.parametrize("results", [True, False])
def test_a_loaded_model_is_summed_up_in_the_log_then_handed_over(monkeypatch, state, state_logs, results):
    model = _model(**_COUNTS, **state, has_analysis_results=results)
    seen = _run(monkeypatch, lambda *a, **k: model)
    expected = [(tr_log(key), "ok") for key in state_logs] + [
        (tr_log("ids_linear", count=1), "info"), (tr_log("ids_planar", count=2), "info"),
        (tr_log("ids_load_area", count=3), "info"), (tr_log("ids_support_punctual", count=4), "info"),
        (tr_log("ids_punctual_loads", count=5), "info"), (tr_log("ids_linear_loads", count=6), "info"),
        (tr_log("ids_planar_loads", count=7), "info"), (tr_log("ids_support_linear", count=8), "info"),
        (tr_log("ids_support_planar", count=9), "info"),
        (tr_log("resolved_materials", resolved=10, total=11), "info"),
        (tr_log("resolved_linear_sections", resolved=12, total=13), "info"),
        (tr_log("loaded_geometry", linear=14, planar=15, load_areas=16, openings=17), "ok"),
        (tr_log("loaded_supports", punctual=18, linear=19, planar=20), "ok"),
        (tr_log("results_available"), "ok") if results else (tr_log("results_unavailable"), "error"),
    ]
    start = seen["log"].index((tr_log("opening_project_reading"), "info")) + 1
    assert seen["log"][start:] == expected
    assert seen["log"][:3] == [
        (tr_log("checking_api"), "info"), (tr_log("api_ok"), "ok"),
        (f"{tr_ui('status_section_api_version')} : 1.27.1", "info"),
    ]
    assert seen["progress"] == [
        (2, tr_log("checking_api")), (6, tr_log("api_ok")),
        (97, tr_log("progress_finalizing")), (100, tr_log("progress_load_done")),
    ]
    assert seen["success"] == [model] and seen["error"] == []


def test_a_model_without_project_state_logs_no_state_line(monkeypatch):
    model = _model(**_COUNTS)
    for key in ("project_kept_open", "project_closed"):
        model.pop(key, None)
    seen = _run(monkeypatch, lambda *a, **k: model)
    start = seen["log"].index((tr_log("opening_project_reading"), "info")) + 1
    assert seen["log"][start] == (tr_log("ids_linear", count=1), "info")


@pytest.mark.parametrize("status, line", [
    ({"message": "Aucune licence", "status": "NoLicence"}, "Aucune licence"),
    ({"status": "NoLicence"}, "NoLicence"),
    ({"canRun": False}, ""),
])
def test_a_licence_problem_stops_the_load_before_the_project_is_opened(monkeypatch, status, line):
    opened = []
    seen = _run(monkeypatch, lambda *a, **k: opened.append(a), licence=status)
    assert seen["log"][-1] == (line, "error")
    assert seen["error"] == [tr_err("licence_open_failed")] and seen["success"] == [] and opened == []


@pytest.mark.parametrize("failure", [ApiUnavailableError("api absente"), ProjectAlreadyOpenError("deja ouvert")])
def test_an_expected_failure_reaches_the_error_signal_as_its_message(monkeypatch, failure):
    def extract(*args, **kwargs):
        raise failure

    seen = _run(monkeypatch, extract)
    assert seen["error"] == [str(failure)] and seen["success"] == []


def test_an_unexpected_failure_reaches_the_error_signal_with_its_traceback(monkeypatch):
    def extract(*args, **kwargs):
        raise ValueError("boum")

    seen = _run(monkeypatch, extract)
    assert seen["error"][0].startswith("Traceback") and "ValueError: boum" in seen["error"][0]
