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
    import display_units as du

    du.reset()
    try:
        assert ui.measure_text(None, "mm") == ""
        assert du.unit("tolerance") == "mm" and du.decimals("tolerance") == 2      # defauts de la grandeur Tolerance
        assert ui.measure_text(2.0, "mm") == "2.00 mm"
        assert ui.measure_text(5.0, "mm") == "5.00 mm"
        assert ui.measure_text(1.766e-06, "mm") == "1.77e-06 mm"      # sous la precision : notation scientifique
        assert ui.measure_text(0.0, "mm") == "0.00 mm"
        du.set_unit("length", "m")                                    # la longueur d'affichage n'influence pas les tolerances
        assert ui.measure_text(2.0, "mm") == "2.00 mm"
        du.set_decimals("tolerance", 3)
        assert ui.measure_text(0.0004, "mm") == "4.00e-04 mm"
        assert ui.measure_text(0.5, "deg") == "0.50 " + du.unit("angle")
        assert ui.measure_text(0.0025, "m2") == "2.50e-03 " + du.unit("area")
        assert ui.measure_text(0.02, "m2") == "0.02 " + du.unit("area")
        du.set_unit("tolerance", "cm")
        assert ui.measure_text(20.0, "mm") == "2.000 cm"
    finally:
        du.reset()
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


def test_main_window_wires_the_controller_in_every_lifecycle_point():
    import inspect
    import main_window

    src = inspect.getsource(main_window.MainWindow)
    assert "self.model_check = ModelCheckController(self)" in src
    assert "self.model_check.build_menu(menu_bar)" in src
    assert "self.model_check.on_selection(selection_list)" in src
    assert src.count("self.model_check.on_model_changed()") >= 2     # chargement + fermeture du projet
    assert "mc.SECTION" in src and "mc.Thresholds.from_section" in src


def test_save_and_load_config_roundtrip_through_a_temporary_file(tmp_path):
    import configparser

    th = mc.Thresholds(connection_tol_mm=9.0, include_info=False)
    cfg = configparser.ConfigParser()
    cfg[mc.SECTION] = th.to_section()
    path = tmp_path / "config.ini"
    with open(path, "w", encoding="utf-8") as f:
        cfg.write(f)
    back = configparser.ConfigParser()
    back.read(path, encoding="utf-8")
    assert mc.Thresholds.from_section(back[mc.SECTION]) == th


def test_results_of_a_cleared_run_are_not_published():
    from PySide6.QtCore import QObject
    import types

    ctl = ui.ModelCheckController(QObject())
    ctl.window = types.SimpleNamespace(viewer=None, current_model_data=None)
    gen = ctl._gen
    ctl.clear()
    ctl._on_done([_a(mc.K_DUPLICATE)], gen)
    assert ctl.anomalies == [] and ctl._ran is False


def test_units_change_redisplays_the_active_anomaly_card_and_refreshes_the_report():
    from PySide6.QtCore import QObject
    import types

    shown, refreshed = [], []
    ctl = ui.ModelCheckController(QObject())
    ctl.window = types.SimpleNamespace(
        viewer=types.SimpleNamespace(active_anomaly_index=lambda: 0),
        _set_properties_message=lambda html: shown.append(html),
    )
    ctl.anomalies = [_a(mc.K_DUPLICATE)]
    ctl._report = types.SimpleNamespace(refresh=lambda: refreshed.append(True))
    assert ctl.on_units_changed() is True
    assert shown and tr_ui("mc_kind_duplicate") in shown[0] and refreshed == [True]
    ctl.window.viewer = types.SimpleNamespace(active_anomaly_index=lambda: None)
    assert ctl.on_units_changed() is False


def test_export_start_path_is_folder_of_the_fto_plus_default_name(tmp_path):
    fto = tmp_path / "modele.fto"
    fto.write_text("x")
    expected = os.path.join(str(tmp_path), "modele_controle.csv")
    assert ui.export_start_path(str(fto)) == expected
    assert ui.export_start_path("  " + str(fto) + " ") == expected
    assert ui.export_start_path(str(tmp_path / "absent" / "m.fto")) == "m_controle.csv"   # dossier inexistant : nom seul
    assert ui.export_start_path("") == "" and ui.export_start_path(None) == ""


def test_export_markdown_table_with_escaped_pipes(tmp_path):
    a = _a(mc.K_DUPLICATE, items=(("lines", 0),), eids=(5,))
    path = tmp_path / "r.md"
    ui.export_rows([(0, a)], str(path))
    lines = open(path, encoding="utf-8").read().splitlines()
    assert lines[0].startswith("# ") and tr_ui("mc_report_title") in lines[0]
    header = [l for l in lines if l.startswith("|")]
    assert len(header) == 3                                   # en-tete, separateur, 1 ligne
    assert header[1].replace("|", "").replace("-", "").replace(" ", "") == ""
    assert tr_ui("mc_kind_duplicate") in header[2] and header[2].count("|") == header[0].count("|")
    assert ui.md_cell("a|b") == "a\|b"
