# -*- coding: utf-8 -*-
"""Controle du modele 3D : helpers de texte, filtres, export et traductions."""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_check as mc
import model_check_ui as ui
from viewer_config import tr_ui


def _a(kind, items=(("lines", 0),), eids=(7,), point=(1.0, 2.0, 3.0), measured=2.0, threshold=5.0, unit="mm"):
    return mc.Anomaly(kind, mc.SEVERITY_BY_KIND[kind], tuple(items), tuple(eids), point, measured, threshold, unit, None)


def test_every_kind_severity_group_and_parameter_is_translated():
    keys = ["mc_kind_" + k for k in mc.KINDS]
    keys += ["mc_sev_" + s for s in (mc.ERROR, mc.WARNING, mc.INFO)]
    keys += ["mc_param_" + name for name in mc.Thresholds.__dataclass_fields__]
    keys += ["mc_group_" + g for g in ("connections", "dup_overlap", "elements", "surfaces", "supports", "report", "display")]
    for key in keys:
        assert tr_ui(key) != key, key


def test_engine_view_exposes_only_the_keys_the_engine_reads():
    out = ui.engine_view({"lines": [1], "line_properties": ["x"], "planars": [2]})
    assert set(out) == set(ui.ENGINE_KEYS) and out["lines"] == [1] and out["planars"] == [2]
    assert ui.engine_view(None)["lines"] is None


def test_counts_and_summary():
    items = [_a(mc.K_DUPLICATE), _a(mc.K_SHORT), _a(mc.K_SHORT), _a(mc.K_COLLINEAR)]
    assert ui.counts(items) == (1, 2, 1)
    assert "1" in ui.summary_text(items) and "2" in ui.summary_text(items)
    assert ui.summary_text([]) == tr_ui("mc_status_none")


def test_filter_rows_keeps_original_indexes():
    items = [_a(mc.K_DUPLICATE), _a(mc.K_SHORT), _a(mc.K_COLLINEAR)]
    assert [i for i, _ in ui.filter_rows(items, None, None)] == [0, 1, 2]
    assert [i for i, _ in ui.filter_rows(items, mc.WARNING, None)] == [1]
    assert [i for i, _ in ui.filter_rows(items, None, mc.K_COLLINEAR)] == [2]
    assert ui.filter_rows(items, mc.ERROR, mc.K_SHORT) == []


def test_text_helpers():
    assert ui.measure_text(None, "mm") == ""
    assert ui.measure_text(2.0, "mm") == "2 mm"
    assert ui.measure_text(0.5, "deg") == "0.5 deg"
    assert ui.measure_text(0.0025, "m2") == "0.0025 m2"
    assert ui.elements_text(_a(mc.K_DUPLICATE, items=(("lines", 0), ("lines", 1)), eids=(5, None))) == "5, #1"
    assert ui.coords_text((1.0, 2.0, 3.0)).count(";") == 2


def test_export_csv_and_text_respect_the_given_rows(tmp_path):
    rows = [(0, _a(mc.K_DUPLICATE)), (2, _a(mc.K_SHORT))]
    csv_path = tmp_path / "r.csv"
    ui.export_rows(rows, str(csv_path))
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f, delimiter=";"))
    assert len(data) == 3 and data[1][1] == tr_ui("mc_kind_duplicate") and data[2][1] == tr_ui("mc_kind_short_element")
    txt_path = tmp_path / "r.txt"
    ui.export_rows(rows, str(txt_path))
    assert len(open(txt_path, encoding="utf-8").read().splitlines()) == 3


def test_anomaly_card_lists_the_six_fields():
    html = ui.anomaly_card_html(_a(mc.K_DUPLICATE, items=(("lines", 0), ("lines", 1)), eids=(5, 6)))
    for key in ("mc_card_type", "mc_card_severity", "mc_card_elements", "mc_card_coords", "mc_card_measure", "mc_card_threshold"):
        assert tr_ui(key) in html
    assert tr_ui("mc_kind_duplicate") in html and "5, 6" in html


def test_settings_dialog_returns_defaults_and_edited_values():
    import pytest
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        # tests/test_qt_translation.py cree un QCoreApplication a l'import : creer un
        # widget dans ce cas ferait planter tout le processus pytest.
        pytest.skip("une QCoreApplication existe deja dans ce processus")
    dlg = ui.ModelCheckSettingsDialog(mc.Thresholds())
    assert dlg.values() == mc.Thresholds()
    dlg.set_values(mc.Thresholds(connection_tol_mm=8.0, check_supports=False))
    assert dlg.values() == mc.Thresholds(connection_tol_mm=8.0, check_supports=False)
    dlg.restore_defaults()
    assert dlg.values() == mc.Thresholds()
    assert app is not None
