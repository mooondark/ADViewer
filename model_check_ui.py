# -*- coding: utf-8 -*-
"""Controle du modele 3D : worker, controleur, fenetres de rapport et de parametres."""

import csv
import math
import os

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QListView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QProgressDialog, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import display_units as du
import model_check as mc
from viewer_config import tr_ui

ENGINE_KEYS = (
    "lines", "line_eids", "planars", "planar_eids",
    "punctual_supports", "punctual_support_eids", "punctual_support_properties",
    "linear_supports", "planar_supports",
)


def engine_view(model_data):
    """Sous-ensemble en lecture seule transmis au thread de detection."""
    data = model_data or {}
    return {k: data.get(k) for k in ENGINE_KEYS}


def severity_label(severity):
    return tr_ui("mc_sev_" + severity)


def kind_label(kind):
    return tr_ui("mc_kind_" + kind)


def elements_text(a):
    parts = []
    for (_role, index), eid in zip(a.items, a.eids):
        parts.append(str(eid) if eid is not None else f"#{index}")
    return ", ".join(parts)


def coords_text(point):
    dec = du.decimals("length")
    return " ; ".join(f"{du.conv(c, 'length'):.{dec}f}" for c in point)


# unite du moteur -> (grandeur display_units, facteur vers l'unite API : m, rad, m2)
_UNIT_KIND = {"mm": ("tolerance", 1e-3), "deg": ("angle", math.pi / 180.0), "m2": ("area", 1.0)}


def measure_text(value, unit):
    """Mesure ou seuil dans l'unite et la precision de Parametres > Unite et
    precision ; notation scientifique sous la precision (evite un 0 trompeur)."""
    if value is None:
        return ""
    if unit not in _UNIT_KIND:
        return f"{value:.4g} {unit}".strip()
    kind, factor = _UNIT_KIND[unit]
    return du.fmt(value * factor, kind)


def counts(anomalies):
    errors = sum(1 for a in anomalies if a.severity == mc.ERROR)
    warnings = sum(1 for a in anomalies if a.severity == mc.WARNING)
    infos = sum(1 for a in anomalies if a.severity == mc.INFO)
    return errors, warnings, infos


def summary_text(anomalies):
    if not anomalies:
        return tr_ui("mc_status_none")
    e, w, i = counts(anomalies)
    return tr_ui("mc_status_summary", errors=e, warnings=w, infos=i)


def filter_rows(anomalies, severity=None, kind=None):
    return [(i, a) for i, a in enumerate(anomalies)
            if (severity is None or a.severity == severity) and (kind is None or a.kind == kind)]


def row_cells(a):
    return [severity_label(a.severity), kind_label(a.kind), elements_text(a), coords_text(a.point),
            measure_text(a.measured, a.unit), measure_text(a.threshold, a.unit)]


def _headers():
    return [tr_ui("mc_col_severity"), tr_ui("mc_col_type"), tr_ui("mc_col_elements"),
            tr_ui("mc_col_coords", unit=du.unit("length")), tr_ui("mc_col_measure"), tr_ui("mc_col_threshold")]


def export_start_path(fto_path):
    """Chemin propose a l'export : <dossier du .fto>/<nom du .fto>_controle.csv.
    Dossier inexistant : nom seul (Qt choisit le dossier) ; chemin vide : vide."""
    text = str(fto_path or "").strip()
    if not text:
        return ""
    name = os.path.splitext(os.path.basename(text))[0] + "_controle.csv"
    folder = os.path.dirname(text)
    return os.path.join(folder, name) if folder and os.path.isdir(folder) else name


def md_cell(text):
    return str(text).replace("|", "\\|")


def export_rows(rows, path):
    """Exporte les lignes (celles qui passent les filtres) en CSV (;) ou texte."""
    cells = [row_cells(a) for _i, a in rows]
    if str(path).lower().endswith(".csv"):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(_headers())
            writer.writerows(cells)
        return
    if str(path).lower().endswith(".md"):
        header = [md_cell(h) for h in _headers()]
        lines = [f"# {tr_ui('mc_report_title')}", "",
                 "| " + " | ".join(header) + " |",
                 "|" + "|".join(" --- " for _ in header) + "|"]
        lines += ["| " + " | ".join(md_cell(c) for c in row) + " |" for row in cells]
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(_headers()) + "\n")
        for row in cells:
            f.write("\t".join(row) + "\n")


def anomaly_card_html(a):
    rows = [
        (tr_ui("mc_card_type"), kind_label(a.kind)),
        (tr_ui("mc_card_severity"), severity_label(a.severity)),
        (tr_ui("mc_card_elements"), elements_text(a) or "-"),
        (tr_ui("mc_card_coords"), coords_text(a.point) + " " + du.unit("length")),
        (tr_ui("mc_card_measure"), measure_text(a.measured, a.unit) or "-"),
        (tr_ui("mc_card_threshold"), measure_text(a.threshold, a.unit) or "-"),
    ]
    return "<br>".join(f"<b>{label}</b> : {value}" for label, value in rows)


class ModelCheckWorker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, model_view, thresholds, parent=None):
        super().__init__(parent)
        self._model = model_view
        self._thresholds = thresholds
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = mc.detect(self._model, self._thresholds,
                               progress=lambda d, t: self.progress.emit(d, t),
                               cancelled=lambda: self._cancel)
        except mc.DetectionCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:   # le thread ne doit jamais laisser une exception non rapportee
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


_GROUPS = (
    ("mc_group_connections", (("connection_tol_mm", "mm"),)),
    ("mc_group_dup_overlap", (("duplicate_tol_mm", "mm"), ("duplicate_angle_deg", "deg"),
                              ("overlap_dist_mm", "mm"), ("overlap_min_len_mm", "mm"),
                              ("overlap_angle_deg", "deg"))),
    ("mc_group_elements", (("min_element_len_mm", "mm"), ("merge_tol_mm", "mm"), ("collinear_angle_deg", "deg"))),
    ("mc_group_surfaces", (("min_surface_area_m2", "m2"), ("min_edge_len_mm", "mm"),
                           ("coincident_vertex_tol_mm", "mm"))),
    ("mc_group_supports", (("check_supports", "bool"), ("report_overlapping_supports", "bool"))),
    ("mc_group_report", (("include_info", "bool"),)),
    ("mc_group_display", (("symbol_transparency_pct", "pct"), ("symbol_min_size_mm", "mm"))),
)
_SUFFIX = {"mm": " mm", "deg": " deg", "m2": " m2", "pct": " %"}


class ModelCheckSettingsDialog(QDialog):
    def __init__(self, thresholds, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("mc_settings_title"))
        self.setModal(True)
        self.resize(520, 640)
        self._widgets = {}
        layout = QVBoxLayout(self)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        for group_key, params in _GROUPS:
            box = QGroupBox(tr_ui(group_key))
            form = QFormLayout(box)
            for name, kind in params:
                if kind == "bool":
                    widget = QCheckBox()
                else:
                    widget = QDoubleSpinBox()
                    lo, hi = mc.BOUNDS[name]
                    widget.setRange(lo, hi)
                    widget.setDecimals(4 if kind == "m2" else 3)
                    widget.setSuffix(_SUFFIX[kind])
                self._widgets[name] = widget
                form.addRow(tr_ui("mc_param_" + name), widget)
            body_layout.addWidget(box)
        body_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.button(QDialogButtonBox.RestoreDefaults).setText(tr_ui("mc_defaults"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.restore_defaults)
        layout.addWidget(buttons)
        self._widgets["check_supports"].toggled.connect(self._sync_enabled)
        self.set_values(thresholds)

    def _sync_enabled(self, *_):
        self._widgets["report_overlapping_supports"].setEnabled(self._widgets["check_supports"].isChecked())

    def set_values(self, th):
        for name, widget in self._widgets.items():
            value = getattr(th, name)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            else:
                widget.setValue(float(value))
        self._sync_enabled()

    def restore_defaults(self):
        self.set_values(mc.Thresholds())

    def values(self):
        out = {}
        for name, widget in self._widgets.items():
            out[name] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value()
        return mc.Thresholds(**out).clamped()


def _fit_popup(combo):
    """Liste deroulante au rendu de l'application : vue QListView (sinon le style
    decale la liste) et largeur de liste au moins egale au texte le plus long."""
    combo.setView(QListView())
    fm = combo.fontMetrics()
    widest = max(fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
    combo.view().setMinimumWidth(widest + 48)
    combo.setMinimumWidth(widest + 48)


class AnomalyReportDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle(tr_ui("mc_report_title"))
        self.setModal(False)
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        self._counts = QLabel()
        layout.addWidget(self._counts)
        filters = QHBoxLayout()
        filters.addWidget(QLabel(tr_ui("mc_filter_severity")))
        self._severity = QComboBox()
        self._severity.addItem(tr_ui("mc_filter_all"), None)
        for sev in (mc.ERROR, mc.WARNING, mc.INFO):
            self._severity.addItem(severity_label(sev), sev)
        filters.addWidget(self._severity)
        filters.addWidget(QLabel(tr_ui("mc_filter_type")))
        self._kind = QComboBox()
        self._kind.addItem(tr_ui("mc_filter_all_types"), None)
        for kind in mc.KINDS:
            self._kind.addItem(kind_label(kind), kind)
        for combo in (self._severity, self._kind):
            _fit_popup(combo)
        filters.addWidget(self._kind)
        filters.addStretch(1)
        layout.addLayout(filters)
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(_headers() + [""])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)
        bottom = QHBoxLayout()
        export = QPushButton(tr_ui("mc_export"))
        export.clicked.connect(self._export)
        bottom.addWidget(export)
        bottom.addStretch(1)
        close = QPushButton(tr_ui("mc_close"))
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self._severity.currentIndexChanged.connect(self.refresh)
        self._kind.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _rows(self):
        return filter_rows(self._controller.anomalies, self._severity.currentData(), self._kind.currentData())

    def refresh(self):
        anomalies = self._controller.anomalies
        e, w, i = counts(anomalies)
        text = f"{tr_ui('mc_count_errors', n=e)}    {tr_ui('mc_count_warnings', n=w)}"
        if self._controller.thresholds.include_info:
            text += f"    {tr_ui('mc_count_infos', n=i)}"
        self._counts.setText(text)
        rows = self._rows()
        self._table.setHorizontalHeaderLabels(_headers() + [""])
        self._table.setRowCount(len(rows))
        for r, (index, a) in enumerate(rows):
            for c, cell in enumerate(row_cells(a)):
                self._table.setItem(r, c, QTableWidgetItem(cell))
            button = QPushButton(tr_ui("mc_view"))
            button.clicked.connect(lambda _=False, idx=index: self._controller.view(idx))
            self._table.setCellWidget(r, 6, button)
        self._table.resizeColumnsToContents()
        if rows:
            width = self._table.cellWidget(0, 6).sizeHint().width() + 16
            self._table.setColumnWidth(6, max(width, 90))

    def _export(self):
        fto_edit = getattr(self._controller.window, "fto_edit", None)
        start = export_start_path(fto_edit.text() if fto_edit is not None else "")
        path, _ = QFileDialog.getSaveFileName(self, tr_ui("mc_export_title"), start, tr_ui("mc_export_filter"))
        if path:
            export_rows(self._rows(), path)


class ModelCheckController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.thresholds = mc.Thresholds()
        self.anomalies = []     # anomalies visibles (informations filtrees selon le parametre)
        self._all = []
        self._ran = False
        self._worker = None
        self._progress = None
        self._report = None
        self._gen = 0    # incremente par clear() : les resultats d'une detection perimee sont ignores
        self.act_run = self.act_report = self.act_toggle = self.act_clear = self.act_settings = None

    # --- menu ---
    def build_menu(self, menu_bar):
        w = self.window
        menu = menu_bar.addMenu(tr_ui("mc_menu"))
        self.act_run = QAction(tr_ui("mc_action_run"), w)
        self.act_run.triggered.connect(self.run)
        self.act_report = QAction(tr_ui("mc_action_report"), w)
        self.act_report.triggered.connect(self.show_report)
        self.act_toggle = QAction(tr_ui("mc_action_toggle"), w, checkable=True)
        self.act_toggle.setChecked(True)
        self.act_toggle.toggled.connect(self.set_symbols_visible)
        self.act_clear = QAction(tr_ui("mc_action_clear"), w)
        self.act_clear.triggered.connect(self.clear)
        self.act_settings = QAction(tr_ui("mc_action_settings"), w)
        self.act_settings.triggered.connect(self.open_settings)
        for act in (self.act_run, self.act_report, self.act_toggle, self.act_clear):
            menu.addAction(act)
        menu.addSeparator()
        menu.addAction(self.act_settings)
        self.update_actions()

    def update_actions(self):
        if self.act_run is None:
            return
        has_model = self.window.current_model_data is not None
        self.act_run.setEnabled(has_model and self._worker is None)
        for act in (self.act_report, self.act_toggle, self.act_clear):
            act.setEnabled(has_model and self._ran)

    # --- execution ---
    def run(self):
        w = self.window
        if w.current_model_data is None or self._worker is not None or w.viewer is None:
            return
        worker = ModelCheckWorker(engine_view(w.current_model_data), self.thresholds, self)
        dialog = QProgressDialog(tr_ui("mc_progress_text"), tr_ui("mc_progress_cancel"), 0, 0, w)
        dialog.setWindowTitle(tr_ui("mc_progress_title"))
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.canceled.connect(worker.request_cancel)
        worker.progress.connect(lambda d, t: (dialog.setMaximum(t), dialog.setValue(d)))
        gen = self._gen
        worker.done.connect(lambda result, g=gen: self._on_done(result, g))
        worker.cancelled.connect(lambda g=gen: self._on_cancelled(g))
        worker.failed.connect(lambda message, g=gen: self._on_failed(message, g))
        self._worker, self._progress = worker, dialog
        self.update_actions()
        dialog.show()
        worker.start()

    def _finish(self):
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
        worker = self._worker
        self._progress = None
        self._worker = None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.update_actions()

    def _status(self, text):
        self.window.statusBar().showMessage(text)
        self.window.log(text, "info")

    def _on_done(self, result, gen=None):
        self._finish()
        if gen is not None and gen != self._gen:
            return
        self._all = list(result)
        self._ran = True
        self._publish()

    def _on_cancelled(self, gen=None):
        self._finish()
        if gen is not None and gen != self._gen:
            return
        self._status(tr_ui("mc_status_cancelled"))

    def _on_failed(self, message, gen=None):
        self._finish()
        if gen is not None and gen != self._gen:
            return
        self._status(tr_ui("mc_status_failed", message=message))

    def _publish(self):
        th = self.thresholds
        self.anomalies = [a for a in self._all if th.include_info or a.severity != mc.INFO]
        viewer = self.window.viewer
        if viewer is not None:
            viewer.set_anomalies(self.anomalies, th)
            viewer.set_anomalies_visible(self.act_toggle.isChecked() if self.act_toggle is not None else True)
        self._status(summary_text(self.anomalies))
        if self._report is not None:
            self._report.refresh()
        self.update_actions()

    # --- actions de menu ---
    def show_report(self):
        if not self._ran:
            self._status(tr_ui("mc_report_no_results"))
            return
        if self._report is None:
            self._report = AnomalyReportDialog(self, self.window)
            self._report.setAttribute(Qt.WA_DeleteOnClose)
            self._report.finished.connect(lambda _=0: setattr(self, "_report", None))
        self._report.show()
        self._report.raise_()

    def set_symbols_visible(self, visible):
        if self.window.viewer is not None:
            self.window.viewer.set_anomalies_visible(bool(visible))

    def clear(self):
        self._gen += 1
        if self._worker is not None:
            self._worker.request_cancel()
        self._all, self.anomalies, self._ran = [], [], False
        viewer = self.window.viewer
        if viewer is not None:
            viewer.clear_anomalies()
            viewer.clear_selection()
        if self._report is not None:
            self._report.close()
        self.update_actions()

    def open_settings(self):
        dialog = ModelCheckSettingsDialog(self.thresholds, self.window)
        if dialog.exec() != QDialog.Accepted:
            return
        old, new = self.thresholds, dialog.values()
        self.thresholds = new
        self.window.save_config()
        if not self._ran:
            return
        detection_changed = any(getattr(old, f) != getattr(new, f) for f in new.__dataclass_fields__
                                if f not in ("include_info", "symbol_transparency_pct", "symbol_min_size_mm"))
        self._publish()
        if detection_changed:
            self.window.statusBar().showMessage(tr_ui("mc_status_rerun"))

    def view(self, index):
        viewer = self.window.viewer
        if viewer is None or not (0 <= index < len(self.anomalies)):
            return
        viewer.select_anomaly(index)
        viewer.focus_anomaly(index)

    def on_units_changed(self):
        """Apres un changement d'unite : rapport et fiche de l'anomalie active
        reaffiches dans la nouvelle unite. Renvoie True si la fiche l'a ete."""
        if self._report is not None:
            self._report.refresh()
        viewer = self.window.viewer
        index = viewer.active_anomaly_index() if viewer is not None else None
        if index is None or not (0 <= index < len(self.anomalies)):
            return False
        self.window._set_properties_message(anomaly_card_html(self.anomalies[index]))
        return True

    def on_model_changed(self):
        self.clear()

    def on_selection(self, selection_list):
        """Appele en tete de on_viewer_selection_changed. Renvoie True si la
        fiche de l'anomalie a ete affichee dans le panneau Proprietes."""
        viewer = self.window.viewer
        index = viewer.consume_anomaly_selection() if viewer is not None else None
        if index is None or not (0 <= index < len(self.anomalies)):
            return False
        self.window.current_analysis_selection = {}
        self.window._update_analysis_results_value_combo({})
        self.window._set_properties_message(anomaly_card_html(self.anomalies[index]))
        return True
