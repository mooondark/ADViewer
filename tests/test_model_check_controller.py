# -*- coding: utf-8 -*-
"""Controleur du controle modele : lancement de la detection, publication des
anomalies (informations filtrees), reglages, fiche d'anomalie selectionnee."""

import dataclasses
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_check as mc
import model_check_ui as ui
from viewer_config import tr_ui


def _anomaly(severity, kind="duplicate"):
    return mc.Anomaly(kind=kind, severity=severity, items=(("lines", 0),), eids=(1,), point=(0, 0, 0))


class _Action:
    def __init__(self, checked=True):
        self.enabled = None
        self.checked = checked

    def setEnabled(self, value):
        self.enabled = value

    def isChecked(self):
        return self.checked


def _controller(model=True, viewer=True):
    ctrl = ui.ModelCheckController(None)
    log = []
    viewer_ns = types.SimpleNamespace(
        set_anomalies=lambda anomalies, th: log.append(("set", [a.severity for a in anomalies])),
        set_anomalies_visible=lambda visible: log.append(("visible", visible)),
        consume_anomaly_selection=lambda: None,
    )
    ctrl.window = types.SimpleNamespace(
        current_model_data={"lines": []} if model else None,
        viewer=viewer_ns if viewer else None,
        log=lambda text, level: log.append(("log", text)),
        save_config=lambda: log.append("save"),
        current_analysis_selection={"x": 1},
        _update_analysis_results_value_combo=lambda sel: log.append(("combo", sel)),
        _set_properties_message=lambda html: log.append(("card", html)),
    )
    ctrl.log = log
    ctrl.act_run, ctrl.act_report, ctrl.act_toggle, ctrl.act_clear = _Action(), _Action(), _Action(False), _Action()
    return ctrl


def test_publish_filters_info_unless_asked_and_refreshes_view_report_and_actions():
    ctrl = _controller()
    ctrl._all = [_anomaly(mc.ERROR), _anomaly(mc.INFO), _anomaly(mc.WARNING)]
    ctrl._ran = True
    refreshed = []
    ctrl._report = types.SimpleNamespace(refresh=lambda: refreshed.append(1))
    ctrl.thresholds = dataclasses.replace(ctrl.thresholds, include_info=False)
    ctrl._publish()
    assert [a.severity for a in ctrl.anomalies] == [mc.ERROR, mc.WARNING]
    assert ctrl.log[:2] == [("set", [mc.ERROR, mc.WARNING]), ("visible", False)]
    assert ctrl.log[2] == ("log", ui.summary_text(ctrl.anomalies))
    assert refreshed == [1] and ctrl.act_report.enabled is True
    ctrl.thresholds = dataclasses.replace(ctrl.thresholds, include_info=True)
    ctrl._publish()
    assert len(ctrl.anomalies) == 3


def test_publish_without_viewer_still_reports_the_summary():
    ctrl = _controller(viewer=False)
    ctrl._publish()
    assert ctrl.log == [("log", tr_ui("mc_status_none"))]


def test_selected_anomaly_card_is_shown_in_properties():
    ctrl = _controller()
    ctrl.anomalies = [_anomaly(mc.ERROR)]
    assert ctrl.on_selection([]) is False
    ctrl.window.viewer.consume_anomaly_selection = lambda: 0
    assert ctrl.on_selection([]) is True
    assert ctrl.window.current_analysis_selection == {}
    assert ctrl.log == [("combo", {}), ("card", ui.anomaly_card_html(ctrl.anomalies[0]))]
    ctrl.window.viewer.consume_anomaly_selection = lambda: 5
    assert ctrl.on_selection([]) is False


@pytest.fixture
def settings_dialog(monkeypatch):
    chosen = {}

    class Dialog:
        def __init__(self, thresholds, parent):
            chosen["initial"] = thresholds

        def exec(self):
            return chosen["result"]

        def values(self):
            return chosen["values"]

    monkeypatch.setattr(ui, "ModelCheckSettingsDialog", Dialog)
    return chosen


def test_settings_cancelled_change_nothing(settings_dialog):
    ctrl = _controller()
    settings_dialog.update(result=ui.QDialog.Rejected, values=mc.Thresholds(connection_tol_mm=99.0))
    ctrl.open_settings()
    assert ctrl.thresholds == mc.Thresholds() and ctrl.log == []


def test_settings_are_saved_and_republished_with_a_rerun_hint_only_for_detection_changes(settings_dialog):
    ctrl = _controller()
    settings_dialog.update(result=ui.QDialog.Accepted, values=mc.Thresholds(include_info=False))
    ctrl.open_settings()
    assert ctrl.thresholds == mc.Thresholds(include_info=False) and ctrl.log == ["save"]   # pas encore de detection

    ctrl._ran = True
    ctrl.log.clear()
    settings_dialog["values"] = mc.Thresholds(include_info=True)
    ctrl.open_settings()
    assert "save" in ctrl.log and ("log", tr_ui("mc_status_rerun")) not in ctrl.log

    ctrl.log.clear()
    settings_dialog["values"] = mc.Thresholds(include_info=True, connection_tol_mm=99.0)
    ctrl.open_settings()
    assert ctrl.log[-1] == ("log", tr_ui("mc_status_rerun"))


@pytest.mark.parametrize("model, viewer, busy", [(False, True, False), (True, False, False), (True, True, True)])
def test_run_is_refused_without_model_or_viewer_or_while_running(monkeypatch, model, viewer, busy):
    monkeypatch.setattr(ui, "ModelCheckWorker", lambda *a: pytest.fail("aucune detection attendue"))
    ctrl = _controller(model, viewer)
    ctrl._worker = object() if busy else None
    ctrl.run()


def test_run_starts_the_detection_with_a_progress_dialog(monkeypatch):
    events = []

    class Signal:
        def connect(self, slot):
            events.append("connect")

    class Worker:
        def __init__(self, view, thresholds, parent):
            events.append(("worker", sorted(view), thresholds))
            self.progress = self.done = self.cancelled = self.failed = Signal()

        def request_cancel(self):
            pass

        def start(self):
            events.append("start")

    class Dialog:
        def __init__(self, *args):
            self.canceled = Signal()

        def __getattr__(self, name):
            return lambda *a: events.append(name) if name == "show" else None

    monkeypatch.setattr(ui, "ModelCheckWorker", Worker)
    monkeypatch.setattr(ui, "QProgressDialog", Dialog)
    ctrl = _controller()
    ctrl.run()
    assert events[0] == ("worker", sorted(ui.ENGINE_KEYS), ctrl.thresholds)
    assert events[-2:] == ["show", "start"]
    assert ctrl._worker is not None and ctrl.act_run.enabled is False
