# -*- coding: utf-8 -*-
"""Normalisation de analysis_status dans build_model_data."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data
from ad_model_data import build_model_data


def test_analysis_status_absent_gives_empty_dict():
    assert build_model_data({})["analysis_status"] == {}
    assert build_model_data({"analysis_status": None})["analysis_status"] == {}


def test_analysis_status_kept():
    status = {"overallState": "Calculated", "design": [{"family": "Steel", "isCalculated": True}]}
    assert build_model_data({"analysis_status": status})["analysis_status"] == status


def _with_probe(result, fn):
    calls = []
    original = ad_model_data.diagnose_results_availability
    ad_model_data.diagnose_results_availability = lambda host, retries=0, delay=1.0: calls.append(retries) or result
    try:
        return fn(), calls
    finally:
        ad_model_data.diagnose_results_availability = original


def test_has_results_uses_status_without_probe():
    r = ad_model_data._resolve_has_results
    assert _with_probe(False, lambda: r("h", {"femIsCalculated": True}, False)) == (True, [])
    assert _with_probe(True, lambda: r("h", {"femIsCalculated": False}, False)) == (False, [])


def test_has_results_probes_when_status_missing():
    r = ad_model_data._resolve_has_results
    assert _with_probe(True, lambda: r("h", {}, False)) == (True, [0])


def test_has_results_probes_with_retries_after_calc():
    r = ad_model_data._resolve_has_results
    assert _with_probe(True, lambda: r("h", {"femIsCalculated": True}, True)) == (True, [15])
    assert _with_probe(False, lambda: r("h", {}, True)) == (False, [15])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")


def _results_buttons_host(has_results):
    import types
    import pytest
    pytest.importorskip("PySide6")
    import main_window as mw

    def button():
        state = {"enabled": None}
        return types.SimpleNamespace(setEnabled=lambda v: state.update(enabled=v), state=state)

    host = types.SimpleNamespace(
        current_model_has_analysis_results=has_results,
        analysis_results_apply_btn=button(),
        analysis_results_export_btn=button(),
        analysis_results_value_combo=object(),
        analysis_results_component_combo=object(),
        _get_current_selected_support_info=lambda: {"role": "lines", "index": 0, "eid": 1},
        _get_selected_analysis_case_entry=lambda: {"id": 1},
        _get_selected_analysis_result_family_key=lambda: "efforts",
        _get_selected_analysis_result_component_key=lambda: "fx",
    )
    mw.MainWindow._update_analysis_results_apply_button(host)
    return host.analysis_results_apply_btn.state["enabled"], host.analysis_results_export_btn.state["enabled"]


def test_results_buttons_disabled_when_model_not_calculated():
    assert _results_buttons_host(False) == (False, False)


def test_results_buttons_enabled_when_model_calculated():
    assert _results_buttons_host(True) == (True, True)
