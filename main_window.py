# -*- coding: utf-8 -*-
"""
Viewer.py
Viewer 3D basique Advance Design en PySide6 + VTK

"""

import os
import csv
import sys
import math
import random
import time
import html
import hashlib
import socket
import urllib.parse
import traceback
import subprocess
import configparser
try:
    from openpyxl import Workbook
except ImportError as e:
    raise RuntimeError("Le module 'openpyxl' est requis. Installez les dépendances de l'application avant l'exécution.")
import ctypes
from typing import Any, Optional, TypedDict

try:
    import requests
except ImportError as e:
    raise RuntimeError("Le module 'requests' est requis. Installez les dépendances de l'application avant l'exécution.") from e

try:
    from PySide6.QtCore import Qt, QThread, Signal, Slot, QTranslator, QLibraryInfo, QSize, QTimer, QPoint, QRectF
    from PySide6.QtGui import QAction, QActionGroup, QTextCursor, QColor, QIcon, QPixmap, QPainter, QPen, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFileDialog, QFrame, QLabel,
        QPushButton, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout,
        QSplitter, QCheckBox, QComboBox, QMenu, QDialog, QFormLayout,
        QDialogButtonBox, QDoubleSpinBox, QSlider, QColorDialog, QProgressBar, QMessageBox,
        QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QGraphicsDropShadowEffect,
        QScrollArea, QToolButton, QGridLayout, QListView
    )
except ImportError as e:
    raise RuntimeError("Le module 'PySide6' est requis. Installez les dépendances de l'application avant l'exécution.") from e

try:
    import vtk
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D
except ImportError as e:
    raise RuntimeError("Le module 'vtk' est requis. Installez les dépendances de l'application avant l'exécution.") from e

try:
    from qt_material import apply_stylesheet, list_themes
except ImportError as e:
    raise RuntimeError("Le module 'qt_material' est requis. Installez les dépendances de l'application avant l'exécution.") from e

try:
    import ad_ifc_exporter
except ImportError:
    ad_ifc_exporter = None


# ===== Imports depuis viewer_config (étape 1 de la modularisation) =====
from viewer_config import *
from viewer_config import _DARK_VTK_BG
import viewer_config

# --- Wrapper pour synchroniser les globales de couleur mutables ---
# _set_fallback_colors() utilise `global` pour réassigner BG, ACCENT, etc.
# dans l'espace de noms de viewer_config. Comme le monolithe a fait un
# `from viewer_config import *`, ses propres copies locales ne sont PAS
# mises à jour automatiquement. Ce wrapper re-synchronise après chaque
# changement de thème.
_COLOR_GLOBALS = (
    'BG', 'PANEL', 'BORDER', 'ACCENT', 'ACCENT2', 'WARN',
    'ERROR_COL', 'FG', 'FG_DIM', 'INPUT_BG', 'INPUT_FG',
    'BTN_BG', 'VTK_BG',
)

def set_active_theme(theme_name: str):
    result = viewer_config.set_active_theme(theme_name)
    _mod = sys.modules[__name__]
    for name in _COLOR_GLOBALS:
        setattr(_mod, name, getattr(viewer_config, name))
    return result


# ===== Imports depuis ad_api_client (étape 2 de la modularisation) =====
from ad_api_client import *


# ===== Imports depuis ad_model_data (étape 3 de la modularisation) =====
from ad_model_data import *
# Imports explicites des fonctions privées utilisées par le reste du monolithe
from ad_model_data import (
    __init__, _analysis_result_display_label, _build_ad_local_axes, _cross_vector3, _format_fixed_unit,
    _normalize_result_family_key, _normalize_vector3, _rotate_vector_around_axis,
)

# ===== Imports depuis viewer_widget (étape 4 de la modularisation) =====
from viewer_widget import *

class SettingsDialog(QDialog):
    def __init__(
        self,
        linear_width: float,
        planar_width: float,
        opening_width: float,
        load_area_width: float,
        support_punctual_size: float,
        support_punctual_line_width: float,
        support_linear_line_width: float,
        support_planar_line_width: float,
        linear_color,
        planar_color,
        opening_color,
        load_area_color,
        support_punctual_color,
        support_linear_color,
        support_planar_color,
        selection_line_width: float,
        selection_color,
        mesh_width: float,
        mesh_color,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("settings_title"))
        self.setModal(True)
        self.resize(540, 380)

        self.linear_color = linear_color
        self.planar_color = planar_color
        self.opening_color = opening_color
        self.load_area_color = load_area_color
        self.support_punctual_color = support_punctual_color
        self.support_linear_color = support_linear_color
        self.support_planar_color = support_planar_color
        self.selection_color = selection_color
        self.mesh_color = mesh_color

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(12)
        grid.setColumnMinimumWidth(0, 120)
        grid.setColumnMinimumWidth(1, 70)
        grid.setColumnMinimumWidth(2, 110)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)

        self.spin_linear = self._make_width_spin(linear_width)
        self.spin_planar = self._make_width_spin(planar_width)
        self.spin_opening = self._make_width_spin(opening_width)
        self.spin_load_area = self._make_width_spin(load_area_width)

        self.spin_support_punctual_size = QDoubleSpinBox()
        self.spin_support_punctual_size.setRange(0.05, 20.0)
        self.spin_support_punctual_size.setDecimals(2)
        self.spin_support_punctual_size.setSingleStep(0.05)
        self.spin_support_punctual_size.setValue(support_punctual_size)
        self.spin_support_punctual_size.setFixedWidth(110)

        self.spin_support_punctual_width = self._make_width_spin(support_punctual_line_width)
        self.spin_support_linear = self._make_width_spin(support_linear_line_width)
        self.spin_support_planar = self._make_width_spin(support_planar_line_width)
        self.spin_selection = self._make_width_spin(selection_line_width)
        self.spin_mesh = self._make_width_spin(mesh_width)

        self._add_row(grid, 0, tr_ui("settings_label_linear"),            tr_ui("settings_label_thickness"), self.spin_linear,                "linear_color",           self.linear_color)
        self._add_row(grid, 1, tr_ui("settings_label_planar"),            tr_ui("settings_label_thickness"), self.spin_planar,                "planar_color",           self.planar_color)
        self._add_row(grid, 2, tr_ui("settings_label_opening"),           tr_ui("settings_label_thickness"), self.spin_opening,               "opening_color",          self.opening_color)
        self._add_row(grid, 3, tr_ui("settings_label_load_area"),         tr_ui("settings_label_thickness"), self.spin_load_area,             "load_area_color",        self.load_area_color)
        self._add_row(grid, 4, tr_ui("settings_label_support_punctual"),  tr_ui("settings_label_size"),      self.spin_support_punctual_size)
        self._add_row(grid, 5, tr_ui("settings_label_support_punctual"),  tr_ui("settings_label_thickness"), self.spin_support_punctual_width, "support_punctual_color", self.support_punctual_color)
        self._add_row(grid, 6, tr_ui("settings_label_support_linear"),    tr_ui("settings_label_thickness"), self.spin_support_linear,        "support_linear_color",   self.support_linear_color)
        self._add_row(grid, 7, tr_ui("settings_label_support_planar"),    tr_ui("settings_label_thickness"), self.spin_support_planar,        "support_planar_color",   self.support_planar_color)
        self._add_row(grid, 8, tr_ui("settings_selection"),               tr_ui("settings_label_thickness"), self.spin_selection,            "selection_color",        self.selection_color)
        self._add_row(grid, 9, tr_ui("settings_label_mesh"),              tr_ui("settings_label_thickness"), self.spin_mesh,                 "mesh_color",             self.mesh_color)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_width_spin(self, value: float):
        spin = QDoubleSpinBox()
        spin.setRange(0.1, 20.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        spin.setFixedWidth(110)
        return spin

    def _rgb_to_stylesheet(self, color_tuple):
        r = int(round(color_tuple[0] * 255))
        g = int(round(color_tuple[1] * 255))
        b = int(round(color_tuple[2] * 255))
        return (
            f"background-color: rgb({r}, {g}, {b}); "
            f"border: 1px solid {BORDER}; border-radius: 4px; min-height: 24px;"
        )

    def _pick_color(self, current_color):
        qcolor = QColor(
            int(round(current_color[0] * 255)),
            int(round(current_color[1] * 255)),
            int(round(current_color[2] * 255))
        )

        dlg = QColorDialog(qcolor, self)
        dlg.setWindowTitle(tr_ui("choose_color"))
        dlg.setOption(QColorDialog.DontUseNativeDialog, True)

        if dlg.exec() != QDialog.Accepted:
            return current_color

        chosen = dlg.currentColor()
        if not chosen.isValid():
            return current_color

        return (
            chosen.red() / 255.0,
            chosen.green() / 255.0,
            chosen.blue() / 255.0
        )

    def _make_color_controls(self, attr_name, initial_color):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        preview = QLabel()
        preview.setFixedWidth(50)
        preview.setStyleSheet(self._rgb_to_stylesheet(initial_color))

        button = QPushButton(tr_ui("choose_color"))

        def choose():
            color = self._pick_color(getattr(self, attr_name))
            setattr(self, attr_name, color)
            preview.setStyleSheet(self._rgb_to_stylesheet(color))

        button.clicked.connect(choose)

        layout.addWidget(preview)
        layout.addWidget(button)
        return row

    def _add_row(self, grid, row, name, sub_label, spinbox, attr_name=None, color=None):
        name_lbl = QLabel(name)
        sub_lbl = QLabel(sub_label)
        sub_lbl.setStyleSheet(f"color:{FG_DIM};")

        grid.addWidget(name_lbl, row, 0, Qt.AlignVCenter)
        grid.addWidget(sub_lbl,  row, 1, Qt.AlignVCenter)
        grid.addWidget(spinbox,  row, 2, Qt.AlignVCenter)

        if attr_name is not None and color is not None:
            color_controls = self._make_color_controls(attr_name, color)
            grid.addWidget(color_controls, row, 3, Qt.AlignVCenter)

    def get_values(self):
        return {
            "linear_width": self.spin_linear.value(),
            "planar_width": self.spin_planar.value(),
            "opening_width": self.spin_opening.value(),
            "load_area_width": self.spin_load_area.value(),
            "support_punctual_size": self.spin_support_punctual_size.value(),
            "support_punctual_line_width": self.spin_support_punctual_width.value(),
            "support_linear_line_width": self.spin_support_linear.value(),
            "support_planar_line_width": self.spin_support_planar.value(),
            "selection_line_width": self.spin_selection.value(),
            "mesh_width": self.spin_mesh.value(),
            "linear_color": self.linear_color,
            "planar_color": self.planar_color,
            "opening_color": self.opening_color,
            "load_area_color": self.load_area_color,
            "support_punctual_color": self.support_punctual_color,
            "support_linear_color": self.support_linear_color,
            "support_planar_color": self.support_planar_color,
            "selection_color": self.selection_color,
            "mesh_color": self.mesh_color,
        }


class ApiServerConfigDialog(QDialog):
    def __init__(self, api_server_exe: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("menu_configuration"))
        self.setModal(True)
        self.resize(640, 130)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(4)
        form.setHorizontalSpacing(12)
        layout.addLayout(form)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        self.exe_edit = QLineEdit(api_server_exe)
        browse_btn = QPushButton(tr_ui("browse"))
        browse_btn.clicked.connect(self.browse_exe)

        row_layout.addWidget(self.exe_edit, 1)
        row_layout.addWidget(browse_btn)

        form.addRow(tr_ui("api_server_exe"), row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_exe(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            tr_ui("browse_exe_title"),
            self.exe_edit.text().strip() or "",
            tr_ui("browse_exe_filter")
        )
        if filename:
            self.exe_edit.setText(normalize_windows_path(filename))

    def get_value(self):
        return normalize_windows_path(self.exe_edit.text().strip())


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("menu_about"))
        self.setModal(True)
        self.resize(300, 230)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Advance Design Model Viewer")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(False)
        title.setStyleSheet(f"color:{ACCENT}; font-size:16px; font-weight:bold;")
        layout.addWidget(title)

        version = QLabel(f"Version : {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(f"color:{FG};")
        layout.addWidget(version)

        html = """<a href="https://github.com/mooondark/ADViewer">Dépôt GitHub du viewer</a><br>
<a href="https://github.com/Graitec-Group/advance-design-api">Dépôt GitHub de l'API</a><br>
<a href="https://www.graitec.com">Site de Graitec</a>"""
        links = QLabel(html)
        links.setAlignment(Qt.AlignCenter)
        links.setWordWrap(True)
        links.setTextFormat(Qt.RichText)
        links.setTextInteractionFlags(Qt.TextBrowserInteraction)
        links.setOpenExternalLinks(True)
        links.setStyleSheet(f"color:{FG};")
        layout.addWidget(links)

        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, alignment=Qt.AlignHCenter)


class FilterDialog(QDialog):
    def __init__(self, sections, thicknesses, materials, selected_sections, selected_thicknesses, selected_materials, initial_tab=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtre")
        self.setModal(True)
        self.resize(640, 420)
        self._section_checkboxes = []
        self._thickness_checkboxes = []
        self._material_checkboxes = []

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.tabs = tabs
        layout.addWidget(tabs)

        sections_tab = QWidget()
        sections_layout = QVBoxLayout(sections_tab)
        sections_buttons = QHBoxLayout()
        btn_sec_all = QPushButton(tr_ui("filter_select_all"))
        btn_sec_none = QPushButton(tr_ui("filter_select_none"))
        sections_buttons.addWidget(btn_sec_all)
        sections_buttons.addWidget(btn_sec_none)
        sections_buttons.addStretch(1)
        sections_layout.addLayout(sections_buttons)

        sections_scroll = QScrollArea()
        sections_scroll.setWidgetResizable(True)
        sections_container = QWidget()
        sections_grid = QGridLayout(sections_container)
        sections_grid.setContentsMargins(2, 2, 2, 2)
        sections_grid.setHorizontalSpacing(24)
        sections_grid.setVerticalSpacing(6)
        columns = 3
        rows = max(1, math.ceil(max(1, len(sections or [])) / columns))
        for idx, name in enumerate(sections or []):
            cb = QCheckBox(str(name))
            cb.setChecked(str(name) in selected_sections)
            self._section_checkboxes.append(cb)
            row = idx % rows
            col = idx // rows
            sections_grid.addWidget(cb, row, col)
        sections_scroll.setWidget(sections_container)
        sections_layout.addWidget(sections_scroll)
        tabs.addTab(sections_tab, tr_ui("filter_by_section"))

        thickness_tab = QWidget()
        thickness_layout = QVBoxLayout(thickness_tab)
        thickness_buttons = QHBoxLayout()
        btn_thk_all = QPushButton(tr_ui("filter_select_all"))
        btn_thk_none = QPushButton(tr_ui("filter_select_none"))
        thickness_buttons.addWidget(btn_thk_all)
        thickness_buttons.addWidget(btn_thk_none)
        thickness_buttons.addStretch(1)
        thickness_layout.addLayout(thickness_buttons)

        thickness_scroll = QScrollArea()
        thickness_scroll.setWidgetResizable(True)
        thickness_container = QWidget()
        thickness_box = QVBoxLayout(thickness_container)
        thickness_box.setContentsMargins(2, 2, 2, 2)
        thickness_box.setSpacing(3)
        for name in thicknesses or []:
            cb = QCheckBox(str(name))
            cb.setChecked(str(name) in selected_thicknesses)
            self._thickness_checkboxes.append(cb)
            thickness_box.addWidget(cb)
        thickness_box.addStretch(1)
        thickness_scroll.setWidget(thickness_container)
        thickness_layout.addWidget(thickness_scroll)
        tabs.addTab(thickness_tab, tr_ui("filter_by_thickness"))

        materials_tab = QWidget()
        materials_layout = QVBoxLayout(materials_tab)
        materials_buttons = QHBoxLayout()
        btn_mat_all = QPushButton(tr_ui("filter_select_all"))
        btn_mat_none = QPushButton(tr_ui("filter_select_none"))
        materials_buttons.addWidget(btn_mat_all)
        materials_buttons.addWidget(btn_mat_none)
        materials_buttons.addStretch(1)
        materials_layout.addLayout(materials_buttons)

        materials_scroll = QScrollArea()
        materials_scroll.setWidgetResizable(True)
        materials_container = QWidget()
        materials_box = QVBoxLayout(materials_container)
        materials_box.setContentsMargins(2, 2, 2, 2)
        materials_box.setSpacing(3)
        for name in materials or []:
            cb = QCheckBox(str(name))
            cb.setChecked(str(name) in selected_materials)
            self._material_checkboxes.append(cb)
            materials_box.addWidget(cb)
        materials_box.addStretch(1)
        materials_scroll.setWidget(materials_container)
        materials_layout.addWidget(materials_scroll)
        tabs.addTab(materials_tab, tr_ui("filter_by_materials"))
        self.tabs.setCurrentIndex(max(0, min(int(initial_tab), self.tabs.count() - 1)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        btn_sec_all.clicked.connect(lambda: self._set_checked(self._section_checkboxes, True))
        btn_sec_none.clicked.connect(lambda: self._set_checked(self._section_checkboxes, False))
        btn_thk_all.clicked.connect(lambda: self._set_checked(self._thickness_checkboxes, True))
        btn_thk_none.clicked.connect(lambda: self._set_checked(self._thickness_checkboxes, False))
        btn_mat_all.clicked.connect(lambda: self._set_checked(self._material_checkboxes, True))
        btn_mat_none.clicked.connect(lambda: self._set_checked(self._material_checkboxes, False))

    def _set_checked(self, checkboxes, value: bool):
        for cb in checkboxes:
            cb.setChecked(bool(value))

    def get_values(self):
        return (
            [cb.text() for cb in self._section_checkboxes if cb.isChecked()],
            [cb.text() for cb in self._thickness_checkboxes if cb.isChecked()],
            [cb.text() for cb in self._material_checkboxes if cb.isChecked()],
        )

    def get_active_tab_index(self):
        return self.tabs.currentIndex() if hasattr(self, "tabs") and self.tabs is not None else 0


class BoundedComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())

    def showPopup(self):
        view = self.view()

        screen = QApplication.screenAt(self.mapToGlobal(QPoint(0, self.height())))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            super().showPopup()
            return
        bounds = screen.availableGeometry()

        margin = 8
        global_top = self.mapToGlobal(self.rect().topLeft())
        global_bottom = self.mapToGlobal(self.rect().bottomLeft())

        space_below = bounds.bottom() - global_bottom.y() - margin
        space_above = global_top.y() - bounds.top() - margin

        # Ouvre la liste du côté (haut ou bas) qui offre le plus d'espace,
        # sans jamais dépasser la hauteur réellement disponible à l'écran.
        open_below = space_below >= space_above
        available_height = max(min(space_below if open_below else space_above, bounds.height() - 2 * margin), 120)

        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = max(22, self.fontMetrics().height() + 8)
        frame_extra = 8
        max_items = max(1, min(self.count(), (available_height - frame_extra) // row_height)) if self.count() > 0 else 1
        self.setMaxVisibleItems(max_items)
        view.setVerticalScrollMode(QListView.ScrollPerPixel)

        # Largeur : s'adapte au contenu mais reste toujours à l'intérieur de
        # l'écran (jamais plus large que l'espace disponible autour du combo),
        # et bascule sur l'ellipsis + barre de défilement horizontale sinon.
        content_width = view.sizeHintForColumn(0) + 2 * view.frameWidth() + 24
        max_allowed_width = max(bounds.width() - 2 * margin, self.width())
        popup_width = max(self.width(), min(content_width, max_allowed_width))
        if content_width > popup_width:
            view.setTextElideMode(Qt.ElideRight)
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Hauteur réelle de la popup : items visibles + cadre du QListView.
        visible_rows = min(self.count(), max_items) if self.count() > 0 else 1
        popup_height = min(visible_rows * row_height + frame_extra, available_height)

        # Position finale, calculée nous-mêmes plutôt que laissée à Qt : ceci
        # évite les sauts en haut/à droite de l'écran observés avec des
        # contraintes de largeur/hauteur imposées à la vue interne.
        popup_x = global_top.x()
        if popup_x + popup_width > bounds.right() - margin:
            popup_x = bounds.right() - popup_width - margin
        if popup_x < bounds.left() + margin:
            popup_x = bounds.left() + margin

        if open_below:
            popup_y = global_bottom.y()
        else:
            popup_y = global_top.y() - popup_height

        super().showPopup()

        popup = view.window()
        if popup is not None:
            popup.setGeometry(popup_x, popup_y, popup_width, popup_height)


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None, use_shadow: bool = True):
        super().__init__(parent)
        self.use_shadow = bool(use_shadow)
        self.apply_theme()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)

        self.title_label = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("cardTitle")
            self.layout.addWidget(self.title_label)

    def apply_theme(self):
        # qt-material handles most styling; we only add card-specific touches
        self.setStyleSheet(
            f"""
            QFrame {{
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            QLabel#cardTitle {{
                color: {ACCENT};
                font-weight: bold;
                font-size: 12px;
                border: none;
                background: transparent;
            }}
            QLabel, QCheckBox {{
                border: none;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            """
        )
        if not self.use_shadow:
            self.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 55 if self.window() and getattr(self.window(), 'theme_name', DEFAULT_THEME) == 'light' else 80))
        self.setGraphicsEffect(shadow)


class LoadAnalysisResultsWorker(QThread):
    success = Signal(object)
    error = Signal(str)

    def __init__(self, session_manager, support_eid: int, analysis_case_id: int, family_label: str, support_role: str, value_label: str = ""):
        super().__init__()
        self.session_manager = session_manager
        self.host = session_manager.host.rstrip("/") if isinstance(session_manager, ProjectSessionManager) else ""
        self.support_eid = int(support_eid)
        self.analysis_case_id = int(analysis_case_id)
        self.family_label = family_label
        self.support_role = str(support_role or "").strip()
        self.value_label = str(value_label or "").strip()

    def run(self):
        try:
            if not isinstance(self.session_manager, ProjectSessionManager) or not self.session_manager.can_read_results():
                raise RuntimeError("Session projet invalide pour la lecture des résultats.")
            if self.support_role in ("lines", "line", "linear", "element_linear"):
                payload = read_linear_element_diagram_results(
                    self.host,
                    self.support_eid,
                    self.analysis_case_id,
                    self.family_label,
                    self.value_label,
                )
            elif self.support_role in ("planars", "planar", "element_planar"):
                payload = read_planar_element_results(
                    self.host,
                    self.support_eid,
                    self.analysis_case_id,
                    self.family_label,
                )
            elif self.support_role == "support_linear":
                payload = read_linear_support_results(
                    self.host,
                    self.support_eid,
                    self.analysis_case_id,
                    self.family_label,
                )
            elif self.support_role == "support_planar":
                payload = read_planar_support_results(
                    self.host,
                    self.support_eid,
                    self.analysis_case_id,
                    self.family_label,
                )
            else:
                payload = read_punctual_support_results(
                    self.host,
                    self.support_eid,
                    self.analysis_case_id,
                    self.family_label,
                )
            self.success.emit(payload)
        except Exception:
            self.error.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self, app=None):
        super().__init__()
        self.app_ref = app
        self.app_icon = load_app_icon("cube.ico", "cube.png", "icon.ico", "icon.png")
        if not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)
        self.setWindowTitle(f"Advance Design Model Viewer - v{APP_VERSION}")
        self.resize(1550, 1020)
        self.worker = None
        self.viewer = None
        self.view_front_btn = None
        self.view_left_btn = None
        self.view_top_btn = None
        self.view_iso_btn = None
        self.filter_btn = None
        self.clear_filter_btn = None
        self.shortcut_view_front_back = None
        self.shortcut_view_left_right = None
        self.shortcut_view_top_bottom = None
        self.shortcut_view_iso = None
        self._front_is_back = False
        self._left_is_right = False
        self._top_is_bottom = False
        self.cmb_display_mode = None
        self.transparency_slider = None
        self.transparency_value_label = None
        self.theme_name = DEFAULT_THEME
        set_active_theme(self.theme_name)
        self.api_server_exe = DEFAULT_API_SERVER_EXE
        self.start_api_btn = None
        self.api_server_process = None
        self.act_theme_dark = None
        self.act_theme_light = None
        self.act_view_projection_perspective = None
        self.act_view_projection_orthogonal = None
        self.view_projection_mode = DEFAULT_VIEW_PROJECTION
        self.api_server_started_by_viewer = False
        self.load_progress_container = None
        self.load_progress_label = None
        self.load_progress_bar = None
        self.side_tabs = None
        self.shared_progress_container = None
        self.help_label = None
        self.title_bar = None
        self._suspend_config_save = False
        self.current_model_data: Optional[ModelDataDict] = None
        self.current_sections = []
        self.current_thicknesses = []
        self.current_materials = []
        self.selected_sections = set()
        self.selected_thicknesses = set()
        self.selected_materials = set()
        self.filter_dialog_tab_index = 0
        self.properties_container = None
        self.properties_layout = None
        self.results_container = None
        self.results_layout = None
        self.results_scroll = None
        self.analysis_results_status_label = None
        self.analysis_results_combo = None
        self.analysis_results_value_combo = None
        self.analysis_results_component_combo = None
        self.analysis_results_apply_btn = None
        self.analysis_results_export_btn = None
        self.analysis_results_output_container = None
        self.current_linear_diagram_payload = None
        self.current_results_cases_combinations = []
        self.current_analysis_selection = {}
        self.analysis_results_worker = None
        self.current_analysis_result_value_label = tr_ui("analysis_result_displacements")
        self.current_analysis_result_type_label = tr_ui("analysis_result_displacements")
        self.current_analysis_result_family_key = "deplacements"
        self.current_analysis_result_component_label = "d"
        self.current_model_has_analysis_results = False
        self.project_session = None
        self._fem_nodes: list = []
        self._fem_connectivity_by_eid: dict = {}
        self.results_sections_state = {
            "linear_section": True,
            "linear_material": True,
            "planar_thickness": True,
            "planar_material": True,
            "load_area": True,
        }

        self._build_ui()
        self._apply_style()
        self._build_menu()
        self._load_or_create_config()

    def _config_path(self):
        return os.path.join(get_app_dir(), CONFIG_FILE)

    def _script_dir(self):
        return get_app_dir()

    def _resolve_initial_browse_dir(self):
        raw_path = ""
        if hasattr(self, "fto_edit") and self.fto_edit is not None:
            raw_path = self.fto_edit.text().strip()
        candidate = normalize_windows_path(raw_path) if raw_path else ""
        if candidate and os.path.isfile(candidate):
            return os.path.dirname(candidate)
        if candidate and os.path.isdir(candidate):
            return candidate
        return self._script_dir()

    def _format_color(self, color):
        return ",".join(f"{float(v):.6f}" for v in color)

    def _parse_color(self, value, fallback):
        try:
            parts = [float(part.strip()) for part in str(value).split(",")]
            if len(parts) != 3:
                return fallback
            return tuple(max(0.0, min(1.0, v)) for v in parts)
        except Exception:
            return fallback

    def save_config(self):
        if self.viewer is None or self._suspend_config_save:
            return

        cfg = configparser.ConfigParser()
        cfg["general"] = {
            "theme": self.theme_name,
            "api_server_exe": self.api_server_exe,
            "last_fto_path": normalize_windows_path(self.fto_edit.text().strip()) if getattr(self, "fto_edit", None) is not None else "",
            "view_projection": self.view_projection_mode,
        }
        cfg["styles"] = {
            "linear_width": str(self.viewer.linear_line_width),
            "planar_width": str(self.viewer.planar_line_width),
            "opening_width": str(self.viewer.opening_line_width),
            "load_area_width": str(self.viewer.load_area_line_width),
            "support_punctual_size": str(self.viewer.support_punctual_size),
            "support_punctual_line_width": str(self.viewer.support_punctual_line_width),
            "support_linear_line_width": str(self.viewer.support_linear_line_width),
            "support_planar_line_width": str(self.viewer.support_planar_line_width),
            "selection_line_width": str(self.viewer.selection_line_width),
            "mesh_width": str(self.viewer.mesh_line_width),
        }
        cfg["colors"] = {
            "linear_color": self._format_color(self.viewer.linear_color),
            "planar_color": self._format_color(self.viewer.planar_color),
            "opening_color": self._format_color(self.viewer.opening_color),
            "load_area_color": self._format_color(self.viewer.load_area_color),
            "support_punctual_color": self._format_color(self.viewer.support_punctual_color),
            "support_linear_color": self._format_color(self.viewer.support_linear_color),
            "support_planar_color": self._format_color(self.viewer.support_planar_color),
            "selection_color": self._format_color(self.viewer.selection_color),
            "mesh_color": self._format_color(self.viewer.mesh_color),
        }

        with open(self._config_path(), "w", encoding="utf-8") as f:
            cfg.write(f)

    def _load_or_create_config(self):
        path = self._config_path()
        if not os.path.isfile(path):
            self.apply_theme(self.theme_name)
            self.apply_view_projection(self.view_projection_mode, save=False)
            self.save_config()
            return

        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        config_updated = False

        self._suspend_config_save = True
        try:
            general = cfg["general"] if cfg.has_section("general") else {}
            styles = cfg["styles"] if cfg.has_section("styles") else {}
            colors = cfg["colors"] if cfg.has_section("colors") else {}

            self.api_server_exe = general.get("api_server_exe", DEFAULT_API_SERVER_EXE)
            loaded_theme = general.get("theme", self.theme_name)
            if loaded_theme not in QT_MATERIAL_THEMES:
                loaded_theme = DEFAULT_THEME

            loaded_projection = str(general.get("view_projection", DEFAULT_VIEW_PROJECTION) or DEFAULT_VIEW_PROJECTION).strip().lower()
            if loaded_projection not in ("perspective", "orthogonal"):
                loaded_projection = DEFAULT_VIEW_PROJECTION
            if not (cfg.has_section("general") and "view_projection" in cfg["general"]):
                config_updated = True
            self.view_projection_mode = loaded_projection

            last_fto_path = normalize_windows_path(general.get("last_fto_path", "").strip())
            if last_fto_path and os.path.isfile(last_fto_path):
                self.fto_edit.setText(last_fto_path)
            else:
                self.fto_edit.setText("")

            self.viewer.set_line_widths(
                float(styles.get("linear_width", self.viewer.linear_line_width)),
                float(styles.get("planar_width", self.viewer.planar_line_width)),
                float(styles.get("opening_width", self.viewer.opening_line_width)),
                float(styles.get("load_area_width", self.viewer.load_area_line_width)),
            )
            self.viewer.set_support_styles(
                float(styles.get("support_punctual_size", self.viewer.support_punctual_size)),
                float(styles.get("support_punctual_line_width", self.viewer.support_punctual_line_width)),
                float(styles.get("support_linear_line_width", self.viewer.support_linear_line_width)),
                float(styles.get("support_planar_line_width", self.viewer.support_planar_line_width)),
            )
            self.viewer.set_colors(
                self._parse_color(colors.get("linear_color", self._format_color(self.viewer.linear_color)), self.viewer.linear_color),
                self._parse_color(colors.get("planar_color", self._format_color(self.viewer.planar_color)), self.viewer.planar_color),
                self._parse_color(colors.get("opening_color", self._format_color(self.viewer.opening_color)), self.viewer.opening_color),
                self._parse_color(colors.get("load_area_color", self._format_color(self.viewer.load_area_color)), self.viewer.load_area_color),
                self._parse_color(colors.get("support_punctual_color", self._format_color(self.viewer.support_punctual_color)), self.viewer.support_punctual_color),
                self._parse_color(colors.get("support_linear_color", self._format_color(self.viewer.support_linear_color)), self.viewer.support_linear_color),
                self._parse_color(colors.get("support_planar_color", self._format_color(self.viewer.support_planar_color)), self.viewer.support_planar_color),
            )
            self.viewer.set_selection_style(
                self._parse_color(colors.get("selection_color", self._format_color(self.viewer.selection_color)), self.viewer.selection_color),
                float(styles.get("selection_line_width", self.viewer.selection_line_width)),
            )
            self.viewer.set_mesh_style(
                self._parse_color(colors.get("mesh_color", self._format_color(self.viewer.mesh_color)), self.viewer.mesh_color),
                float(styles.get("mesh_width", self.viewer.mesh_line_width)),
            )
            self.apply_view_projection(self.view_projection_mode, save=False)
            pass
        finally:
            self._suspend_config_save = False
        if config_updated:
            self.save_config()
    def _make_view_icon(self, kind: str) -> QIcon:
        size = 24
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Détecter le thème pour choisir la couleur d'icône
        is_dark = getattr(self, 'theme_name', DEFAULT_THEME) == 'dark'

        if is_dark:
            # Thème sombre : fond légèrement plus clair sous l'icône pour détacher du bouton
            # puis trait blanc épais par-dessus
            bg_pen = QPen(QColor(60, 70, 90, 180))
            bg_pen.setWidth(6)
            bg_pen.setJoinStyle(Qt.RoundJoin)
            bg_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(bg_pen)
            self._paint_icon_shape(painter, kind, size, offset=1)

            pen = QPen(QColor(220, 220, 230))
            pen.setWidth(2)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            self._paint_icon_shape(painter, kind, size, offset=0)
        else:
            # Thème clair : icône foncée simple
            pen = QPen(QColor(40, 40, 60))
            pen.setWidth(2)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            self._paint_icon_shape(painter, kind, size, offset=0)

        painter.end()
        return QIcon(pm)

    def _paint_icon_shape(self, painter: QPainter, kind: str, size: int, offset: int = 0):
        """Dessine la forme géométrique de l'icône (24x24)."""
        o = offset
        s = size
        scale = s / 20.0

        def sx(x): return int(round(x * scale)) + o
        def sy(y): return int(round(y * scale)) + o

        if kind == "front_back":
            painter.drawRect(sx(6), sy(5), int(8*scale), int(10*scale))
            painter.drawLine(sx(2), sy(10), sx(5), sy(10))
            painter.drawLine(sx(4), sy(8), sx(2), sy(10))
            painter.drawLine(sx(4), sy(12), sx(2), sy(10))
            painter.drawLine(sx(15), sy(10), sx(18), sy(10))
            painter.drawLine(sx(16), sy(8), sx(18), sy(10))
            painter.drawLine(sx(16), sy(12), sx(18), sy(10))
        elif kind == "left_right":
            painter.drawLine(sx(4), sy(4), sx(4), sy(16))
            painter.drawLine(sx(16), sy(4), sx(16), sy(16))
            painter.drawLine(sx(6), sy(10), sx(14), sy(10))
            painter.drawLine(sx(8), sy(8), sx(6), sy(10))
            painter.drawLine(sx(8), sy(12), sx(6), sy(10))
            painter.drawLine(sx(12), sy(8), sx(14), sy(10))
            painter.drawLine(sx(12), sy(12), sx(14), sy(10))
        elif kind == "top_bottom":
            painter.drawLine(sx(4), sy(4), sx(16), sy(4))
            painter.drawLine(sx(4), sy(16), sx(16), sy(16))
            painter.drawLine(sx(10), sy(6), sx(10), sy(14))
            painter.drawLine(sx(8), sy(8), sx(10), sy(6))
            painter.drawLine(sx(12), sy(8), sx(10), sy(6))
            painter.drawLine(sx(8), sy(12), sx(10), sy(14))
            painter.drawLine(sx(12), sy(12), sx(10), sy(14))
        elif kind == "filter":
            painter.drawLine(sx(4), sy(4), sx(16), sy(4))
            painter.drawLine(sx(4), sy(4), sx(9), sy(10))
            painter.drawLine(sx(16), sy(4), sx(11), sy(10))
            painter.drawLine(sx(9), sy(10), sx(9), sy(16))
            painter.drawLine(sx(11), sy(10), sx(11), sy(16))
            painter.drawLine(sx(9), sy(16), sx(11), sy(16))
        elif kind == "filter_clear":
            painter.drawLine(sx(4), sy(4), sx(16), sy(4))
            painter.drawLine(sx(4), sy(4), sx(9), sy(10))
            painter.drawLine(sx(16), sy(4), sx(11), sy(10))
            painter.drawLine(sx(9), sy(10), sx(9), sy(16))
            painter.drawLine(sx(11), sy(10), sx(11), sy(16))
            painter.drawLine(sx(9), sy(16), sx(11), sy(16))
            slash_pen = QPen(QColor(255, 80, 80))
            slash_pen.setWidth(int(2*scale))
            old_pen = painter.pen()
            painter.setPen(slash_pen)
            painter.drawLine(sx(3), sy(17), sx(17), sy(3))
            painter.setPen(old_pen)
        else:
            painter.drawLine(sx(6), sy(4), sx(14), sy(4))
            painter.drawLine(sx(14), sy(4), sx(17), sy(8))
            painter.drawLine(sx(17), sy(8), sx(9), sy(8))
            painter.drawLine(sx(9), sy(8), sx(6), sy(4))
            painter.drawLine(sx(6), sy(4), sx(6), sy(12))
            painter.drawLine(sx(6), sy(12), sx(9), sy(16))
            painter.drawLine(sx(9), sy(16), sx(17), sy(16))
            painter.drawLine(sx(17), sy(16), sx(17), sy(8))
            painter.drawLine(sx(9), sy(8), sx(9), sy(16))


    def _setup_view_button(self, button, kind: str, tooltip: str):
        button.setText("")
        button.setToolTip(tooltip)
        button.setIcon(self._make_view_icon(kind))
        button.setIconSize(QSize(18, 18))
        button.setMinimumWidth(32)
        button.setMinimumHeight(26)
        button.setMaximumHeight(26)
        button.setObjectName("iconBtn")

    def _apply_style(self):
        # qt-material handles the global stylesheet; we only add app-specific tweaks
        self.setStyleSheet(
            f"""
            QFrame#titleBar {{
                background: transparent;
                border: none;
            }}
            QPushButton#primary {{
                font-weight: bold;
            }}
            QPushButton#fitBtn {{
                background: {ACCENT};
                border: 1px solid {ACCENT};
                color: white;
            }}
            QPushButton#clearLogBtn {{
                padding: 4px 10px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#apiStopBtn {{
                background: {ERROR_COL};
                color: white;
                border: 1px solid {ERROR_COL};
                font-weight: bold;
            }}
            QPushButton#apiStopBtn:hover {{
                background: #ff6b6b;
                border: 1px solid #ff6b6b;
            }}
            QTextEdit {{
                border-radius: 8px;
                padding: 4px;
                font-family: "Segoe UI";
                font-size: 11px;
            }}
            QToolTip {{
                padding: 6px 8px;
                font-family: Segoe UI;
                font-size: 10pt;
            }}
            QSplitter::handle {{
                background: transparent;
            }}
            QProgressBar {{
                border-radius: 8px;
                text-align: center;
                min-height: 22px;
            }}
            QProgressBar::chunk {{
                border-radius: 7px;
            }}
            QTabWidget::pane {{
                border-top: none;
                top: 0px;
            }}
            QTabBar::tab {{
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 7px 12px;
                font-weight: bold;
                color: {FG};
            }}
            QTabBar::tab:selected {{
                color: white;
                background: {ACCENT};
            }}
            QTabBar::tab:!selected {{
                margin-top: 4px;
                color: {FG_DIM};
            }}
            /* Boutons d'icône (vues, filtres) - bordure uniforme */
            QPushButton[iconOnly="true"] {{
                border: 1px solid {BORDER};
                background: transparent;
            }}
            QPushButton[iconOnly="true"]:hover {{
                border: 1px solid {ACCENT};
                background: {ACCENT};
            }}
            QPushButton#iconBtn {{
                background: transparent;
                border: 1px solid {BORDER};
                color: {FG};
                padding: 2px;
                min-width: 32px;
                max-width: 32px;
                min-height: 26px;
                max-height: 26px;
            }}
            QPushButton#iconBtn:hover {{
                background: {ACCENT};
                border: 1px solid {ACCENT};
                color: white;
            }}
            """
        )


    def _create_menu(self, title: str):
        return QMenu(title, self)

    def apply_view_projection(self, mode: str, save: bool = True):
        normalized = str(mode or DEFAULT_VIEW_PROJECTION).strip().lower()
        if normalized not in ("perspective", "orthogonal"):
            normalized = DEFAULT_VIEW_PROJECTION
        self.view_projection_mode = normalized
        if self.viewer is not None:
            self.viewer.set_projection_mode(normalized)
        if self.act_view_projection_perspective is not None:
            self.act_view_projection_perspective.setChecked(normalized == "perspective")
        if self.act_view_projection_orthogonal is not None:
            self.act_view_projection_orthogonal.setChecked(normalized == "orthogonal")
        if save and not self._suspend_config_save:
            self.save_config()

    def _build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.clear()

        # ── Menu Fichier ──
        file_menu = menu_bar.addMenu(tr_ui("menu_file"))

        act_open = QAction(tr_ui("menu_open"), self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.browse_fto)
        file_menu.addAction(act_open)

        act_export_ifc = QAction(tr_ui("menu_export_ifc"), self)
        act_export_ifc.triggered.connect(self.export_ifc_from_viewer)
        file_menu.addAction(act_export_ifc)

        act_about = QAction(tr_ui("menu_about"), self)
        act_about.triggered.connect(self.open_about_dialog)
        file_menu.addAction(act_about)

        file_menu.addSeparator()

        act_quit = QAction(tr_ui("menu_quit"), self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # ── Menu Paramètres ──
        settings_menu = menu_bar.addMenu(tr_ui("menu_settings"))

        act_line_widths = QAction(tr_ui("menu_styles"), self)
        act_line_widths.triggered.connect(self.open_settings_dialog)
        settings_menu.addAction(act_line_widths)

        # Sous-menu Thème
        theme_menu = QMenu(tr_ui("menu_theme"), self)
        settings_menu.addMenu(theme_menu)

        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self.act_theme_dark = QAction(tr_ui("theme_dark"), self, checkable=True)
        self.act_theme_dark.triggered.connect(lambda checked: checked and self.apply_theme("dark"))
        theme_group.addAction(self.act_theme_dark)
        theme_menu.addAction(self.act_theme_dark)

        self.act_theme_light = QAction(tr_ui("theme_light"), self, checkable=True)
        self.act_theme_light.triggered.connect(lambda checked: checked and self.apply_theme("light"))
        theme_group.addAction(self.act_theme_light)
        theme_menu.addAction(self.act_theme_light)

        # Sous-menu Vue 3D
        view3d_menu = QMenu(tr_ui("menu_view3d"), self)
        settings_menu.addMenu(view3d_menu)

        projection_group = QActionGroup(self)
        projection_group.setExclusive(True)

        self.act_view_projection_perspective = QAction(tr_ui("view_projection_perspective"), self, checkable=True)
        self.act_view_projection_perspective.triggered.connect(lambda checked: checked and self.apply_view_projection("perspective"))
        projection_group.addAction(self.act_view_projection_perspective)
        view3d_menu.addAction(self.act_view_projection_perspective)

        self.act_view_projection_orthogonal = QAction(tr_ui("view_projection_orthogonal"), self, checkable=True)
        self.act_view_projection_orthogonal.triggered.connect(lambda checked: checked and self.apply_view_projection("orthogonal"))
        projection_group.addAction(self.act_view_projection_orthogonal)
        view3d_menu.addAction(self.act_view_projection_orthogonal)

        # Sous-menu Configuration
        configuration_menu = QMenu(tr_ui("menu_configuration"), self)
        settings_menu.addMenu(configuration_menu)

        act_api_server = QAction(tr_ui("menu_api_server"), self)
        act_api_server.triggered.connect(self.open_configuration_dialog)
        configuration_menu.addAction(act_api_server)

        self.apply_view_projection(self.view_projection_mode, save=False)

    def _create_main_layout(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(6)
        main_splitter.setChildrenCollapsible(False)
        root.addWidget(main_splitter, 1)
        return main_splitter

    def _build_project_card(self, left_layout):
        file_card = Card(tr_ui("project"))
        self.fto_edit = QLineEdit()
        self.fto_edit.setPlaceholderText(tr_ui("project_file"))
        browse_btn = QPushButton(tr_ui("browse"))
        browse_btn.clicked.connect(self.browse_fto)

        hb1 = QHBoxLayout()
        hb1.addWidget(self.fto_edit, 1)
        hb1.addWidget(browse_btn)

        file_card.layout.addWidget(QLabel(tr_ui("project_file")))
        file_card.layout.addLayout(hb1)

        self.host_edit = QLineEdit(DEFAULT_HOST)
        file_card.layout.addWidget(QLabel(tr_ui("api_url")))
        file_card.layout.addWidget(self.host_edit)

        self.start_api_btn = QPushButton(tr_ui("start_api"))
        self.start_api_btn.clicked.connect(self.toggle_api_server)
        file_card.layout.addWidget(self.start_api_btn)

        self.load_btn = QPushButton(tr_ui("load_model"))
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self.load_model)
        file_card.layout.addWidget(self.load_btn)

        left_layout.addWidget(file_card)

    def _build_actions_card(self, left_layout):
        action_card = Card(tr_ui("actions"))

        self.fit_btn = QPushButton(tr_ui("fit_view"))
        self.fit_btn.setObjectName("fitBtn")
        self.fit_btn.clicked.connect(self.viewer_fit_proxy)

        views_row = QHBoxLayout()
        views_row.setContentsMargins(0, 0, 0, 0)
        views_row.setSpacing(3)

        self.view_front_btn = QPushButton()
        self.view_front_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.view_front_btn, "front_back", tr_ui("tooltip_view_front_back"))
        self.view_front_btn.clicked.connect(self.viewer_front_back_proxy)

        self.view_left_btn = QPushButton()
        self.view_left_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.view_left_btn, "left_right", tr_ui("tooltip_view_left_right"))
        self.view_left_btn.clicked.connect(self.viewer_left_right_proxy)

        self.view_top_btn = QPushButton()
        self.view_top_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.view_top_btn, "top_bottom", tr_ui("tooltip_view_top_bottom"))
        self.view_top_btn.clicked.connect(self.viewer_top_bottom_proxy)

        self.view_iso_btn = QPushButton()
        self.view_iso_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.view_iso_btn, "iso", tr_ui("tooltip_view_iso"))
        self.view_iso_btn.clicked.connect(self.viewer_iso_proxy)

        self._install_view_shortcuts()

        for btn in (self.view_front_btn, self.view_left_btn, self.view_top_btn, self.view_iso_btn):
            views_row.addWidget(btn)

        self.filter_btn = QPushButton()
        self.filter_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.filter_btn, "filter", tr_ui("tooltip_filter"))
        self.filter_btn.clicked.connect(self.open_filter_dialog)

        self.clear_filter_btn = QPushButton()
        self.clear_filter_btn.setProperty("iconOnly", True)
        self._setup_view_button(self.clear_filter_btn, "filter_clear", tr_ui("tooltip_clear_filter"))
        self.clear_filter_btn.clicked.connect(self.clear_structural_filters)

        self.isolate_btn = QPushButton()
        self.isolate_btn.setCheckable(True)
        self.isolate_btn.setProperty("iconOnly", True)
        self.isolate_btn.setText("")
        self.isolate_btn.setToolTip(tr_ui("tooltip_isolate"))
        self.isolate_btn.setMinimumWidth(34)
        self.isolate_btn.setMaximumWidth(34)
        self.isolate_btn.clicked.connect(self.toggle_isolation)
        self._apply_isolate_button_icon(False)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(3)
        filter_row.addStretch(1)
        filter_row.addWidget(self.filter_btn)
        filter_row.addWidget(self.clear_filter_btn)
        filter_row.addWidget(self.isolate_btn)
        filter_row.addStretch(1)

        action_card.layout.addWidget(self.fit_btn)
        action_card.layout.addLayout(views_row)
        action_card.layout.addLayout(filter_row)

        transparency_title = QLabel(tr_ui("transparency"))
        transparency_title.setStyleSheet(f"color:{FG_DIM};")
        action_card.layout.addWidget(transparency_title)

        transparency_row = QHBoxLayout()
        transparency_row.setContentsMargins(0, 0, 0, 0)
        transparency_row.setSpacing(4)

        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setValue(INITIAL_TRANSPARENCY_PERCENT)
        self.transparency_slider.setSingleStep(5)
        self.transparency_slider.setPageStep(10)
        self.transparency_slider.valueChanged.connect(self.on_transparency_changed)

        self.transparency_value_label = QLabel(
            tr_ui("transparency_value", value=INITIAL_TRANSPARENCY_PERCENT)
        )
        self.transparency_value_label.setStyleSheet(f"color:{FG_DIM}; min-width:48px;")

        transparency_row.addWidget(self.transparency_slider, 1)
        transparency_row.addWidget(self.transparency_value_label)
        action_card.layout.addLayout(transparency_row)

        display_title = QLabel(tr_ui("display"))
        display_title.setStyleSheet(f"color:{FG_DIM}; font-weight:bold;")
        action_card.layout.addWidget(display_title)

        action_card.layout.addWidget(QLabel(tr_ui("display_mode")))
        self.cmb_display_mode = QComboBox()
        self.cmb_display_mode.setView(QListView())
        self.cmb_display_mode.addItem(tr_ui("display_wireframe"), "wireframe")
        self.cmb_display_mode.addItem(tr_ui("display_hidden_faces"), "hidden_faces")
        self.cmb_display_mode.addItem(tr_ui("display_wire_hidden"), "wire_hidden")
        self.cmb_display_mode.addItem(tr_ui("display_full"), "full")
        self.cmb_display_mode.setCurrentIndex(self.cmb_display_mode.findData("wire_hidden"))
        self.cmb_display_mode.currentIndexChanged.connect(self.on_display_mode_changed)
        action_card.layout.addWidget(self.cmb_display_mode)

        self.chk_lines = QCheckBox(tr_ui("show_lines"))
        self.chk_lines.setChecked(True)
        self.chk_lines.toggled.connect(self.on_toggle_lines)
        action_card.layout.addWidget(self.chk_lines)

        self.chk_planars = QCheckBox(tr_ui("show_planars"))
        self.chk_planars.setChecked(True)
        self.chk_planars.toggled.connect(self.on_toggle_planars)
        action_card.layout.addWidget(self.chk_planars)

        self.chk_load_areas = QCheckBox(tr_ui("show_load_areas"))
        self.chk_load_areas.setChecked(True)
        self.chk_load_areas.toggled.connect(self.on_toggle_load_areas)
        action_card.layout.addWidget(self.chk_load_areas)

        self.chk_support_punctual = QCheckBox(tr_ui("show_support_punctual"))
        self.chk_support_punctual.setChecked(True)
        self.chk_support_punctual.toggled.connect(self.on_toggle_support_punctual)
        action_card.layout.addWidget(self.chk_support_punctual)

        self.chk_support_linear = QCheckBox(tr_ui("show_support_linear"))
        self.chk_support_linear.setChecked(True)
        self.chk_support_linear.toggled.connect(self.on_toggle_support_linear)
        action_card.layout.addWidget(self.chk_support_linear)

        self.chk_support_planar = QCheckBox(tr_ui("show_support_planar"))
        self.chk_support_planar.setChecked(True)
        self.chk_support_planar.toggled.connect(self.on_toggle_support_planar)
        action_card.layout.addWidget(self.chk_support_planar)

        self.chk_marker = QCheckBox(tr_ui("show_marker"))
        self.chk_marker.setChecked(True)
        self.chk_marker.toggled.connect(self.on_toggle_marker)
        action_card.layout.addWidget(self.chk_marker)

        self.chk_mesh = QCheckBox(tr_ui("show_mesh"))
        self.chk_mesh.setChecked(False)
        self.chk_mesh.setEnabled(False)
        self.chk_mesh.toggled.connect(self.on_toggle_mesh)
        action_card.layout.addWidget(self.chk_mesh)

        self.chk_color_by_section = QCheckBox(tr_ui("color_by_section"))
        self.chk_color_by_section.setChecked(True)
        self.chk_color_by_section.toggled.connect(self.on_toggle_color_by_section)
        action_card.layout.addWidget(self.chk_color_by_section)

        self.help_label = QLabel(tr_ui("help_controls"))
        self.help_label.setToolTip(tr_ui("help_controls_tooltip"))
        self.help_label.setStyleSheet(f"color:{FG_DIM};")
        action_card.layout.addWidget(self.help_label)

        left_layout.addWidget(action_card)
        left_layout.addStretch(1)

    def _build_left_panel(self, main_splitter):
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self._build_project_card(left_layout)
        self._build_actions_card(left_layout)
        main_splitter.addWidget(left)
        return left

    def _build_viewer_panel(self, right_splitter):
        viewer_card = Card(tr_ui("view3d"), use_shadow=False)
        self.viewer = VTKViewerWidget()
        self.viewer.selectionChanged.connect(self.on_viewer_selection_changed)
        self._update_display_checkboxes()
        viewer_card.layout.addWidget(self.viewer, 1)
        right_splitter.addWidget(viewer_card)
        return viewer_card

    def _build_log_tab(self):
        log_tab = QWidget()
        log_tab_layout = QVBoxLayout(log_tab)
        log_tab_layout.setContentsMargins(6, 6, 6, 6)
        log_tab_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(4)

        log_title = QLabel(tr_ui("journal"))
        log_title.setObjectName("cardTitle")

        self.clear_log_btn = QPushButton(tr_ui("clear"))
        self.clear_log_btn.setObjectName("clearLogBtn")
        self.clear_log_btn.clicked.connect(self.clear_log)

        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(self.clear_log_btn)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumWidth(320)

        self.load_progress_container = QWidget()
        progress_layout = QVBoxLayout(self.load_progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(2)

        self.load_progress_label = QLabel("Chargement en attente")
        self.load_progress_label.setStyleSheet(f"color:{FG_DIM};")

        self.load_progress_bar = QProgressBar()
        self.load_progress_bar.setRange(0, 100)
        self.load_progress_bar.setValue(0)
        self.load_progress_bar.setFormat("0 %")
        self.load_progress_bar.setTextVisible(True)

        progress_layout.addWidget(self.load_progress_label)
        progress_layout.addWidget(self.load_progress_bar)
        self.load_progress_container.setVisible(False)

        self.shared_progress_container = QWidget()
        shared_progress_layout = QVBoxLayout(self.shared_progress_container)
        shared_progress_layout.setContentsMargins(6, 4, 6, 4)
        shared_progress_layout.setSpacing(2)
        shared_progress_layout.addWidget(self.load_progress_container)
        self.shared_progress_container.setVisible(False)

        log_tab_layout.addLayout(log_header)
        log_tab_layout.addWidget(self.log_edit)
        return log_tab

    def _build_properties_tab(self):
        properties_tab = QWidget()
        properties_layout = QVBoxLayout(properties_tab)
        properties_layout.setContentsMargins(6, 6, 6, 6)
        properties_layout.setSpacing(4)
        self.properties_layout = properties_layout
        properties_layout.addWidget(self.shared_progress_container)
        self.properties_container = QWidget()
        self.properties_container.setStyleSheet("background: transparent;")
        properties_layout.addWidget(self.properties_container)
        properties_layout.addStretch(1)
        return properties_tab

    def _build_results_tab(self):
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.setContentsMargins(6, 6, 6, 6)
        results_layout.setSpacing(4)
        self.results_layout = results_layout
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results_scroll.setStyleSheet("background: transparent; border: none;")
        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_scroll.setWidget(self.results_container)
        results_layout.addWidget(self.results_scroll)
        return results_tab

    def _build_analysis_results_tab(self):
        analysis_results_tab = QWidget()
        analysis_results_layout = QVBoxLayout(analysis_results_tab)
        analysis_results_layout.setContentsMargins(6, 6, 6, 6)
        analysis_results_layout.setSpacing(4)
        self.analysis_results_layout = analysis_results_layout
        self.analysis_results_status_label = QLabel(tr_ui("analysis_results_status_unavailable"))
        self.analysis_results_status_label.setWordWrap(True)
        self.analysis_results_status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.analysis_results_status_label.setStyleSheet(f"color:{FG_DIM};")
        analysis_results_layout.addWidget(self.analysis_results_status_label)
        self.analysis_results_combo = BoundedComboBox()
        self.analysis_results_combo.addItem(tr_ui("analysis_results_case_placeholder"))
        self.analysis_results_combo.setEnabled(False)
        self.analysis_results_combo.currentIndexChanged.connect(self.on_results_case_combination_changed)
        analysis_results_layout.addWidget(self.analysis_results_combo)
        self.analysis_results_value_combo = BoundedComboBox()
        self.analysis_results_value_combo.addItem(tr_ui("analysis_results_type_placeholder"))
        self.analysis_results_value_combo.setEnabled(False)
        self.analysis_results_value_combo.currentTextChanged.connect(self.on_analysis_result_value_changed)
        analysis_results_layout.addWidget(self.analysis_results_value_combo)
        self.analysis_results_component_combo = BoundedComboBox()
        self.analysis_results_component_combo.addItem(tr_ui("analysis_results_value_placeholder"))
        self.analysis_results_component_combo.setEnabled(False)
        self.analysis_results_component_combo.currentTextChanged.connect(self.on_analysis_result_component_changed)
        analysis_results_layout.addWidget(self.analysis_results_component_combo)
        scale_row = QHBoxLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(6)
        self.analysis_results_scale_label = QLabel(tr_ui("analysis_results_scale"))
        scale_row.addWidget(self.analysis_results_scale_label)
        self.analysis_results_scale_spin = QDoubleSpinBox()
        self.analysis_results_scale_spin.setRange(0.1, 10.0)
        self.analysis_results_scale_spin.setDecimals(1)
        self.analysis_results_scale_spin.setSingleStep(0.1)
        self.analysis_results_scale_spin.setValue(1.0)
        self.analysis_results_scale_spin.setEnabled(False)
        self.analysis_results_scale_spin.valueChanged.connect(self.on_analysis_scale_changed)
        scale_row.addWidget(self.analysis_results_scale_spin)
        scale_row.addStretch(1)
        analysis_results_layout.addLayout(scale_row)
        self.analysis_results_apply_btn = QPushButton(tr_ui("analysis_results_apply"))
        self.analysis_results_apply_btn.setEnabled(False)
        self.analysis_results_apply_btn.clicked.connect(self.apply_analysis_results)
        analysis_results_layout.addWidget(self.analysis_results_apply_btn)
        self.analysis_results_export_btn = QPushButton(tr_ui("analysis_results_export"))
        self.analysis_results_export_btn.setEnabled(False)
        self.analysis_results_export_btn.clicked.connect(self.export_analysis_results_csv)
        analysis_results_layout.addWidget(self.analysis_results_export_btn)
        self.analysis_results_scroll = QScrollArea()
        self.analysis_results_scroll.setWidgetResizable(True)
        self.analysis_results_scroll.setFrameShape(QFrame.NoFrame)
        self.analysis_results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.analysis_results_scroll.setStyleSheet("background: transparent; border: none;")
        self.analysis_results_output_container = QWidget()
        self.analysis_results_output_container.setStyleSheet("background: transparent;")
        output_layout = QVBoxLayout(self.analysis_results_output_container)
        output_layout.setContentsMargins(0, 6, 0, 0)
        output_layout.setSpacing(4)
        self.analysis_results_scroll.setWidget(self.analysis_results_output_container)
        analysis_results_layout.addWidget(self.analysis_results_scroll)
        return analysis_results_tab

    def _build_side_tabs(self, right_splitter):
        side_tabs = QTabWidget()
        self.side_tabs = side_tabs
        side_tabs.setTabPosition(QTabWidget.North)
        side_tabs.setDocumentMode(False)
        side_tabs.setMinimumWidth(336)
        side_tab_bar = side_tabs.tabBar()
        side_tab_bar.setExpanding(False)
        side_tab_bar.setUsesScrollButtons(False)
        side_tab_bar.setElideMode(Qt.ElideNone)

        log_tab = self._build_log_tab()
        properties_tab = self._build_properties_tab()
        results_tab = self._build_results_tab()
        analysis_results_tab = self._build_analysis_results_tab()

        side_tabs.addTab(log_tab, tr_ui("journal"))
        side_tabs.addTab(properties_tab, tr_ui("properties"))
        side_tabs.addTab(results_tab, tr_ui("takeoff"))
        side_tabs.addTab(analysis_results_tab, tr_ui("results"))
        side_tabs.currentChanged.connect(lambda _index: self._relocate_progress_container())
        right_splitter.addWidget(side_tabs)
        return side_tabs

    def _finalize_ui_state(self, main_splitter, right_splitter):
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([LEFT_PANEL_INITIAL_WIDTH, 1120])

        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)
        right_splitter.setSizes([860, 336])

        self.viewer.set_faces_transparency(INITIAL_TRANSPARENCY_PERCENT)
        self.viewer.set_display_mode(self.cmb_display_mode.currentData())
        self._update_transparency_controls_state()
        self._update_api_button_state()
        self._relocate_progress_container()
        self._set_properties_message(tr_ui("select_element"))
        self._set_results_message(tr_ui("takeoff_empty"))
        self._set_analysis_results_output_message(tr_ui("analysis_results_empty"))
        self._update_analysis_scale_controls(None)
        self.log(tr_log("ready"), "info")

    def _build_ui(self):
        main_splitter = self._create_main_layout()
        self._build_left_panel(main_splitter)

        right_splitter = QSplitter(Qt.Horizontal)
        right_splitter.setHandleWidth(6)
        right_splitter.setChildrenCollapsible(False)

        self._build_viewer_panel(right_splitter)
        self._build_side_tabs(right_splitter)
        main_splitter.addWidget(right_splitter)

        self._finalize_ui_state(main_splitter, right_splitter)
    def _get_tab_layout_for_progress(self):
        if self.side_tabs is None:
            return None
        current_widget = self.side_tabs.currentWidget()
        return current_widget.layout() if current_widget is not None else None

    def _relocate_progress_container(self):
        if self.shared_progress_container is None or self.load_progress_container is None:
            return
        target_layout = self._get_tab_layout_for_progress()
        if target_layout is None:
            return
        current_parent = self.shared_progress_container.parentWidget()
        if current_parent is not None and current_parent.layout() is not None:
            current_parent.layout().removeWidget(self.shared_progress_container)
        target_layout.insertWidget(0, self.shared_progress_container)
        self.shared_progress_container.setVisible(self.load_progress_container.isVisible())

    def _clear_layout_widgets(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout_widgets(child_layout)

    def _set_properties_message(self, text: str):
        if self.properties_container is None:
            return
        layout = self.properties_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.properties_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{FG_DIM};")
        layout.addWidget(label)
        layout.addStretch(1)

    def _add_properties_section_title(self, layout, title: str):
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{ACCENT}; font-weight:bold; font-size:12px;")
        layout.addWidget(lbl)

    def _create_results_section(self, title: str, state_key: str):
        header = QToolButton()
        header.setText(title)
        header.setCheckable(True)
        header.setChecked(bool(self.results_sections_state.get(state_key, True)))
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.DownArrow if header.isChecked() else Qt.RightArrow)
        header.setStyleSheet(
            f"QToolButton {{ color:{ACCENT}; font-weight:bold; font-size:12px; border:none; padding:2px 0; text-align:left; }}"
        )

        content = QWidget()
        content.setVisible(header.isChecked())
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 0, 0, 0)
        content_layout.setSpacing(3)

        def _toggle(checked):
            self.results_sections_state[state_key] = bool(checked)
            header.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            content.setVisible(bool(checked))
            QTimer.singleShot(0, self._align_results_tables)

        header.toggled.connect(_toggle)
        return header, content, content_layout

    def _add_properties_type_label(self, layout, text: str):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color:{FG}; font-weight:bold;")
        layout.addWidget(lbl)

    def _add_properties_spacer(self, layout, height: int = 8):
        spacer = QWidget()
        spacer.setFixedHeight(height)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

    def _create_properties_table(self, row_count: int):
        table = QTableWidget(row_count, 3)
        table.setHorizontalHeaderLabels(["", "", ""])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setWordWrap(False)
        table.setCornerButtonEnabled(False)
        table.setFrameShape(QFrame.NoFrame)
        table.setLineWidth(0)
        table.setMidLineWidth(0)
        table.setColumnWidth(0, 110)
        table.setColumnWidth(1, 1)
        table.setColumnWidth(2, 110)
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background: transparent;
                color: {FG};
                border: none;
            }}
            QTableWidget::item {{
                padding: 0px 6px;
                border: none;
            }}
            QHeaderView::section {{
                background: transparent;
                border: none;
            }}
            """
        )
        return table

    def _set_table_name_item(self, table, row: int, name: str):
        item = QTableWidgetItem(name)
        item.setFlags(Qt.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setData(Qt.ForegroundRole, QColor(FG))
        item.setData(Qt.UserRole, "name")
        table.setItem(row, 0, item)
        sep = QTableWidgetItem("")
        sep.setFlags(Qt.ItemIsEnabled)
        sep.setBackground(QColor(BORDER))
        table.setItem(row, 1, sep)
        if row == 0:
            table.setStyleSheet(
                f"""
                QTableWidget {{
                    background: transparent;
                    color: {FG};
                    border: none;
                }}
                QTableWidget::item {{
                    padding: 0px 6px;
                    border: none;
                }}
                QHeaderView::section {{
                    background: transparent;
                    border: none;
                }}
                """
            )

    def _set_table_value_item(self, table, row: int, value_text: str):
        item = QTableWidgetItem(value_text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.setItem(row, 2, item)

    def _set_table_checkbox(self, table, row: int, checked: bool):
        value = "☑" if checked else "☐"
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.setItem(row, 2, item)

    def _finalize_properties_table(self, table):
        table.resizeRowsToContents()
        table.verticalHeader().setDefaultSectionSize(14)

        if table.columnCount() >= 3:
            left_width = 110
            value_width = 110
            for row in range(table.rowCount()):
                left_item = table.item(row, 0)
                value_item = table.item(row, 2)
                if left_item is not None:
                    left_width = max(left_width, table.fontMetrics().horizontalAdvance(left_item.text()) + 18)
                if value_item is not None:
                    value_width = max(value_width, table.fontMetrics().horizontalAdvance(value_item.text()) + 18)
            table.setColumnWidth(0, left_width)
            table.setColumnWidth(1, 1)
            table.setColumnWidth(2, value_width)

        frame = table.frameWidth() * 2
        header_h = table.horizontalHeader().height() if table.horizontalHeader().isVisible() else 0
        row_h = sum(table.rowHeight(i) for i in range(table.rowCount()))
        extra = 2
        total_h = frame + header_h + row_h + extra
        total_w = frame + sum(table.columnWidth(i) for i in range(table.columnCount()))
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        table.setMinimumHeight(total_h)
        table.setMaximumHeight(total_h)
        table.setFixedHeight(total_h)
        table.setMinimumWidth(total_w)
        table.setMaximumWidth(total_w)
        table.setFixedWidth(total_w)
        return table

    def _format_stiffness_value(self, value: float, unit: str):
        numeric = float(value)
        if unit == "N*m/°":
            numeric = numeric / 180.0 * math.pi
        return f"{numeric:.6g} {unit}"

    def _render_linear_element_properties(self, data: dict):
        if self.properties_container is None:
            return
        layout = self.properties_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.properties_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
        else:
            layout.setSpacing(4)
        self._clear_layout_widgets(layout)

        self._add_properties_type_label(layout, str(data.get("type_label", tr_ui("prop_linear_element"))))
        self._add_properties_spacer(layout, 2)

        rows = list(data.get("rows", []) or [])
        has_relaxation_blocks = False
        if rows:
            table = self._create_properties_table(len(rows))
            for row, (name, value_text) in enumerate(rows):
                self._set_table_name_item(table, row, str(name))
                self._set_table_value_item(table, row, str(value_text))
            self._finalize_properties_table(table)
            layout.addWidget(table)

        for idx, (title, flags) in enumerate((
            (tr_ui("prop_relaxation_end_1"), data.get("start_relaxation") or {}),
            (tr_ui("prop_relaxation_end_2"), data.get("end_relaxation") or {}),
        )):
            if idx == 0:
                self._add_properties_spacer(layout, 2)
            else:
                self._add_properties_spacer(layout, 4)
            self._add_properties_section_title(layout, title)
            keys = ("TX", "TY", "TZ", "RX", "RY", "RZ")
            table = self._create_properties_table(len(keys))
            for row, key in enumerate(keys):
                self._set_table_name_item(table, row, key)
                self._set_table_checkbox(table, row, bool(flags.get(key, False)))
            self._finalize_properties_table(table)
            layout.addWidget(table)
            has_relaxation_blocks = True

        if not rows and not has_relaxation_blocks:
            self._set_properties_message(tr_ui("prop_no_linear"))
            return
        layout.addStretch(1)

    def _set_results_message(self, text: str):
        if self.results_container is None:
            return
        layout = self.results_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.results_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{FG_DIM};")
        layout.addWidget(label)
        layout.addStretch(1)


    def _set_analysis_results_status(self, has_results):
        if self.analysis_results_status_label is None:
            return
        if has_results is True:
            text = tr_ui("analysis_results_status_available")
        else:
            text = tr_ui("analysis_results_status_unavailable")
        self.analysis_results_status_label.setText(text)

    def _set_analysis_results_output_message(self, text: str):
        if self.analysis_results_output_container is None:
            return
        layout = self.analysis_results_output_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.analysis_results_output_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{FG_DIM};")
        layout.addWidget(label)
        layout.addStretch(1)

    def _render_analysis_results_rows(self, title: str, rows: list):
        if self.analysis_results_output_container is None:
            return
        layout = self.analysis_results_output_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.analysis_results_output_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)
        if title:
            self._add_properties_section_title(layout, title)
        if not rows:
            self._set_analysis_results_output_message(tr_ui("analysis_results_none_for_selection"))
            return

        sections = []
        current_rows = []
        for item in rows:
            item = item or {}
            if item.get("kind") == "section_title":
                if current_rows:
                    sections.append((None, current_rows))
                    current_rows = []
                sections.append((str(item.get("name", "")).strip(), None))
            else:
                current_rows.append(item)
        if current_rows:
            sections.append((None, current_rows))

        if not sections:
            self._set_analysis_results_output_message("Aucun résultat disponible pour cette sélection.")
            return

        first_block = True
        for section_title, section_rows in sections:
            if section_title:
                if not first_block:
                    self._add_properties_spacer(layout, 2)
                self._add_properties_section_title(layout, section_title)
                first_block = False
                continue
            if section_rows:
                table = self._create_properties_table(len(section_rows))
                for row, item in enumerate(section_rows):
                    self._set_table_name_item(table, row, str((item or {}).get("name", "N/A")))
                    self._set_table_value_item(table, row, str((item or {}).get("value", "N/A")))
                self._finalize_properties_table(table)
                layout.addWidget(table)
                first_block = False
        layout.addStretch(1)

    def _get_current_selected_support_info(self):
        selection = dict(self.current_analysis_selection or {})
        role = selection.get("role")
        if role in ("lines", "line", "linear", "element_linear"):
            eids = list((self.current_model_data or {}).get("line_eids", []) or [])
            if not eids:
                for props in list((self.current_model_data or {}).get("line_properties", []) or []):
                    eid = None
                    if isinstance(props, dict):
                        for key in ("eid", "id", "element_id"):
                            if props.get(key) is not None:
                                try:
                                    eid = int(props.get(key))
                                except Exception:
                                    eid = None
                                if eid is not None:
                                    break
                        if eid is None:
                            rows = list(props.get("rows", []) or [])
                            for i in range(0, max(0, len(rows) - 1), 2):
                                label = str(rows[i] or "").strip().lower()
                                if label in ("eid", "id", "element id"):
                                    try:
                                        eid = int(str(rows[i + 1]).strip())
                                    except Exception:
                                        eid = None
                                    break
                    eids.append(eid)
        elif role == "support_punctual":
            eids = list((self.current_model_data or {}).get("punctual_support_eids", []) or [])
        elif role == "support_linear":
            eids = list((self.current_model_data or {}).get("linear_support_eids", []) or [])
        elif role == "support_planar":
            eids = list((self.current_model_data or {}).get("planar_support_eids", []) or [])
        elif role in ("planars", "planar", "element_planar"):
            eids = list((self.current_model_data or {}).get("planar_eids", []) or [])
        else:
            return None
        index = int(selection.get("index", -1))
        if index < 0 or index >= len(eids):
            return None
        eid = eids[index]
        return {"index": index, "eid": eid, "role": role} if eid is not None else None
    def _get_selected_analysis_case_entry(self):
        if self.analysis_results_combo is None:
            return None
        data = self.analysis_results_combo.currentData()
        return data if isinstance(data, dict) else None

    def _update_analysis_results_apply_button(self):
        if self.analysis_results_apply_btn is None:
            return
        if self.analysis_results_value_combo is None or self.analysis_results_component_combo is None:
            self.analysis_results_apply_btn.setEnabled(False)
            if self.analysis_results_export_btn is not None:
                self.analysis_results_export_btn.setEnabled(False)
            return
        selected_info = self._get_current_selected_support_info()
        case_entry = self._get_selected_analysis_case_entry()
        family_key = self._get_selected_analysis_result_family_key()
        value_key = self._get_selected_analysis_result_component_key()
        role = str((selected_info or {}).get("role") or "").strip()
        export_enabled = bool(selected_info and case_entry and role in ("lines", "line", "linear", "element_linear"))
        if self.analysis_results_export_btn is not None:
            self.analysis_results_export_btn.setEnabled(export_enabled)
        if not selected_info or not case_entry:
            self.analysis_results_apply_btn.setEnabled(False)
            return
        if not family_key:
            self.analysis_results_apply_btn.setEnabled(False)
            return
        if role in ("lines", "line", "linear", "element_linear") and not value_key:
            self.analysis_results_apply_btn.setEnabled(False)
            return
        self.analysis_results_apply_btn.setEnabled(True)

    def on_analysis_result_value_changed(self, text: str):
        value = str(text or "").strip()
        family_key = self._get_selected_analysis_result_family_key()
        if value and family_key:
            self.current_analysis_result_family_key = family_key
            self.current_analysis_result_value_label = value
            self.current_analysis_result_type_label = value
        self._populate_analysis_result_component_combo()
        self._update_analysis_results_apply_button()

    def on_analysis_result_component_changed(self, text: str):
        value = self._get_selected_analysis_result_component_key() or str(text or "").strip()
        if value:
            self.current_analysis_result_component_label = value
        self._update_analysis_results_apply_button()

    def _get_selected_analysis_result_family_key(self) -> str:
        if self.analysis_results_value_combo is None:
            return ""
        value = self.analysis_results_value_combo.currentData()
        if value in (None, ""):
            value = _normalize_result_family_key(self.analysis_results_value_combo.currentText().strip())
        return str(value or "").strip()

    def _get_selected_analysis_result_component_key(self) -> str:
        if self.analysis_results_component_combo is None:
            return ""
        value = self.analysis_results_component_combo.currentData()
        if value in (None, ""):
            value = self.analysis_results_component_combo.currentText().strip()
        return str(value or "").strip()

    def _analysis_result_component_options(self, role: str, family_key: str):
        family_key = _normalize_result_family_key(family_key)
        if role in ("lines", "line", "linear", "element_linear"):
            if family_key == "deplacements":
                return ["dx", "dy", "dz", "d"], "d"
            if family_key == "efforts":
                return ["fx", "fy", "fz", "mx", "my", "mz"], "fx"
            if family_key == "contraintes":
                return ["sxxMin", "sxxMax", "sxyMin", "sxyMax", "sxzMin", "sxzMax", "sv"], "sv"
        return [], ""

    def _populate_analysis_result_component_combo(self):
        if self.analysis_results_component_combo is None:
            return
        role = str((self.current_analysis_selection or {}).get("role") or "").strip()
        family_key = self._get_selected_analysis_result_family_key()
        options, default_value = self._analysis_result_component_options(role, family_key)
        self.analysis_results_component_combo.blockSignals(True)
        self.analysis_results_component_combo.clear()
        if options:
            for option in options:
                self.analysis_results_component_combo.addItem(option, option)
            self.analysis_results_component_combo.setEnabled(True)
            remembered = str(self.current_analysis_result_component_label or "").strip()
            if remembered in options:
                self.analysis_results_component_combo.setCurrentText(remembered)
            elif default_value in options:
                self.analysis_results_component_combo.setCurrentText(default_value)
                self.current_analysis_result_component_label = default_value
            else:
                self.analysis_results_component_combo.setCurrentIndex(0)
                self.current_analysis_result_component_label = self._get_selected_analysis_result_component_key()
        else:
            self.analysis_results_component_combo.addItem(tr_ui("analysis_results_value_placeholder"), "")
            self.analysis_results_component_combo.setEnabled(False)
        self.analysis_results_component_combo.blockSignals(False)

    def _update_analysis_results_value_combo(self, selection=None):
        self.current_analysis_selection = dict(selection or {})
        if self.analysis_results_value_combo is None:
            return
        self.analysis_results_value_combo.blockSignals(True)
        self.analysis_results_value_combo.clear()
        role = selection.get("role") if isinstance(selection, dict) else None
        items = []
        message = tr_ui("analysis_results_apply_support_help")
        if role in ("lines", "line", "linear", "element_linear"):
            items = [
                (tr_ui("analysis_result_displacements"), "deplacements"),
                (tr_ui("analysis_result_forces"), "efforts"),
                (tr_ui("analysis_result_stresses"), "contraintes"),
            ]
            message = tr_ui("analysis_results_help")
        elif role == "support_punctual":
            items = [
                (tr_ui("analysis_result_displacements"), "deplacements"),
                (tr_ui("analysis_result_forces"), "efforts"),
            ]
        elif role in ("support_linear", "support_planar", "planars", "planar", "element_planar"):
            items = [(tr_ui("analysis_result_forces"), "efforts")]

        if items:
            for label, key in items:
                self.analysis_results_value_combo.addItem(label, key)
            self.analysis_results_value_combo.setEnabled(True)
            remembered = _normalize_result_family_key(getattr(self, "current_analysis_result_family_key", ""))
            available = {key for _label, key in items}
            target_key = remembered if remembered in available else items[0][1]
            index = next((i for i, (_label, key) in enumerate(items) if key == target_key), 0)
            self.analysis_results_value_combo.setCurrentIndex(index)
            self.current_analysis_result_family_key = target_key
            self.current_analysis_result_type_label = self.analysis_results_value_combo.currentText().strip() or items[0][0]
            self.current_analysis_result_value_label = self.current_analysis_result_type_label
            self._set_analysis_results_output_message(message)
        else:
            self.analysis_results_value_combo.addItem(tr_ui("analysis_results_type_placeholder"), "")
            self.analysis_results_value_combo.setEnabled(False)
            self._set_analysis_results_output_message(tr_ui("analysis_results_select_element"))
        self.analysis_results_value_combo.blockSignals(False)
        self._update_analysis_scale_controls(selection)
        self._populate_analysis_result_component_combo()
        self._update_analysis_results_apply_button()

    def _populate_results_case_combination_combo(self, entries):
        self.current_results_cases_combinations = list(entries or [])
        if self.analysis_results_combo is None:
            return
        self.analysis_results_combo.blockSignals(True)
        self.analysis_results_combo.clear()
        if not self.current_results_cases_combinations:
            self.analysis_results_combo.addItem(tr_ui("analysis_results_case_placeholder"))
            self.analysis_results_combo.setEnabled(False)
        else:
            for entry in self.current_results_cases_combinations:
                self.analysis_results_combo.addItem(str((entry or {}).get("label", "")), entry)
            self.analysis_results_combo.setEnabled(True)
            self.analysis_results_combo.setCurrentIndex(0)
        self.analysis_results_combo.blockSignals(False)
        self._update_analysis_results_apply_button()

    def on_results_case_combination_changed(self, index: int):
        self._update_analysis_results_apply_button()

    def _update_analysis_scale_controls(self, selection=None):
        role = selection.get("role") if isinstance(selection, dict) else None
        enabled = role in ("lines", "line", "linear", "element_linear")
        if self.analysis_results_scale_label is not None:
            self.analysis_results_scale_label.setEnabled(enabled)
        if self.analysis_results_scale_spin is not None:
            self.analysis_results_scale_spin.setEnabled(enabled)

    def _create_results_three_value_table(self, row_count: int):
        table = QTableWidget(row_count, 5)
        table.setHorizontalHeaderLabels(["", "", "", "", ""])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setWordWrap(False)
        table.setCornerButtonEnabled(False)
        table.setFrameShape(QFrame.NoFrame)
        table.setLineWidth(0)
        table.setMidLineWidth(0)
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 1)
        table.setColumnWidth(3, 1)
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background: transparent;
                color: {FG};
                border: none;
            }}
            QTableWidget::item {{
                padding: 4px 6px;
                border: none;
            }}
            QHeaderView::section {{
                background: transparent;
                border: none;
            }}
            """
        )
        return table

    def _set_table_extra_value_item(self, table, row: int, value_text: str):
        sep = QTableWidgetItem("")
        sep.setFlags(Qt.ItemIsEnabled)
        sep.setBackground(QColor(BORDER))
        table.setItem(row, 3, sep)
        item = QTableWidgetItem(value_text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        table.setItem(row, 4, item)

    def _render_results(self, model_data: dict):
        if self.results_container is None:
            return
        layout = self.results_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.results_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)

        linear_rows = list((model_data or {}).get("linear_takeoff", []) or [])
        linear_material_rows = list((model_data or {}).get("linear_material_takeoff", []) or [])
        planar_rows = list((model_data or {}).get("planar_takeoff", []) or [])
        planar_material_rows = list((model_data or {}).get("planar_material_takeoff", []) or [])
        load_area_total = (model_data or {}).get("load_area_takeoff")

        sections = [
            (tr_ui("takeoff_linear_section"), "linear_section", linear_rows, "value_text", tr_ui("takeoff_empty_linear")),
            (tr_ui("takeoff_linear_material"), "linear_material", linear_material_rows, "value_text", tr_ui("takeoff_empty_linear")),
            (tr_ui("takeoff_planar_thickness"), "planar_thickness", planar_rows, "area_text", tr_ui("takeoff_empty_planar")),
            (tr_ui("takeoff_planar_material"), "planar_material", planar_material_rows, "area_text", tr_ui("takeoff_empty_planar")),
        ]

        for idx, (title, state_key, rows, value_key, empty_text) in enumerate(sections):
            if idx > 0:
                self._add_properties_spacer(layout, 8)
            header, content, content_layout = self._create_results_section(title, state_key)
            layout.addWidget(header)
            if rows:
                table = self._create_properties_table(len(rows))
                for row, item in enumerate(rows):
                    self._set_table_name_item(table, row, str(item.get("name", "N/A")))
                    self._set_table_value_item(table, row, str(item.get(value_key, "N/A")))
                self._finalize_properties_table(table)
                content_layout.addWidget(table)
            else:
                label = QLabel(empty_text)
                label.setWordWrap(True)
                label.setStyleSheet(f"color:{FG_DIM};")
                content_layout.addWidget(label)
            layout.addWidget(content)

        self._add_properties_spacer(layout, 8)
        header, content, content_layout = self._create_results_section(tr_ui("takeoff_load_area"), "load_area")
        layout.addWidget(header)
        if load_area_total is None:
            label = QLabel(tr_ui("takeoff_empty_load_area"))
            label.setWordWrap(True)
            label.setStyleSheet(f"color:{FG_DIM};")
            content_layout.addWidget(label)
        else:
            table = self._create_properties_table(1)
            self._set_table_name_item(table, 0, tr_ui("takeoff_total_area"))
            self._set_table_value_item(table, 0, _format_fixed_unit(load_area_total, "m²", 2))
            self._finalize_properties_table(table)
            content_layout.addWidget(table)
        layout.addWidget(content)

        layout.addStretch(1)
        QTimer.singleShot(0, self._align_results_tables)

    def _align_results_tables(self):
        if self.results_container is None:
            return
        tables = self.results_container.findChildren(QTableWidget)
        if not tables:
            return
        left_width = 0
        value_width = 0
        for table in tables:
            if table.columnCount() < 3:
                continue
            left_width = max(left_width, table.columnWidth(0))
            value_width = max(value_width, table.columnWidth(2))
        if left_width <= 0 or value_width <= 0:
            return
        for table in tables:
            if table.columnCount() < 3:
                continue
            table.setColumnWidth(0, left_width)
            table.setColumnWidth(1, 1)
            table.setColumnWidth(2, value_width)
            frame = table.frameWidth() * 2
            total_w = frame + sum(table.columnWidth(i) for i in range(table.columnCount()))
            table.setMinimumWidth(total_w)
            table.setMaximumWidth(total_w)
            table.setFixedWidth(total_w)

    def _render_planar_element_properties(self, data: dict):
        if self.properties_container is None:
            return
        layout = self.properties_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.properties_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)

        self._add_properties_type_label(layout, str(data.get("type_label", tr_ui("prop_planar_element"))))
        self._add_properties_spacer(layout, 8)

        rows = list(data.get("rows", []) or [])
        if not rows:
            self._set_properties_message(tr_ui("prop_no_planar"))
            return

        table = self._create_properties_table(len(rows))
        for row, (name, value_text) in enumerate(rows):
            self._set_table_name_item(table, row, str(name))
            self._set_table_value_item(table, row, str(value_text))
        self._finalize_properties_table(table)
        layout.addWidget(table)
        layout.addStretch(1)

    def _render_punctual_support_properties(self, data: dict):
        if self.properties_container is None:
            return
        layout = self.properties_container.layout()
        if layout is None:
            layout = QVBoxLayout(self.properties_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
        self._clear_layout_widgets(layout)

        self._add_properties_type_label(layout, str(data.get("type_label", tr_ui("prop_punctual_support"))))
        self._add_properties_spacer(layout, 8)

        kind = str(data.get("kind", ""))
        if kind == "rigid":
            self._add_properties_section_title(layout, data.get("section_title", tr_ui("prop_blocking")))
            keys = ("TX", "TY", "TZ", "RX", "RY", "RZ")
            table = self._create_properties_table(len(keys))
            restraints = data.get("restraints") or {}
            for row, key in enumerate(keys):
                self._set_table_name_item(table, row, key)
                self._set_table_checkbox(table, row, bool(restraints.get(key, False)))
            self._finalize_properties_table(table)
            layout.addWidget(table)
        elif kind in ("elastic", "tc"):
            self._add_properties_section_title(layout, data.get("section_title", tr_ui("prop_stiffness")))
            rows = []
            tc_behavior = str(data.get("tc_behavior", "")).strip()
            if kind == "tc":
                rows.append((tr_ui("prop_operation"), tc_behavior or ""))
            stiffness = data.get("stiffness") or {}
            for key, unit in (
                ("KTX", "N/m"),
                ("KTY", "N/m"),
                ("KTZ", "N/m"),
                ("KRX", "N*m/°"),
                ("KRY", "N*m/°"),
                ("KRZ", "N*m/°"),
            ):
                rows.append((key, self._format_stiffness_value(stiffness.get(key, 0.0), unit)))
            table = self._create_properties_table(len(rows))
            for row, (name, value_text) in enumerate(rows):
                self._set_table_name_item(table, row, name)
                self._set_table_value_item(table, row, value_text)
            self._finalize_properties_table(table)
            layout.addWidget(table)
        else:
            message = QLabel(str(data.get("message", "Non pris en charge")))
            message.setWordWrap(True)
            message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            message.setStyleSheet(f"color:{FG_DIM};")
            layout.addWidget(message)
            layout.addStretch(1)
            return
        layout.addStretch(1)

    def _sanitize_export_stem(self, value: str) -> str:
        text = str(value or "").strip()
        invalid = '<>:"/\\|?*'
        for char in invalid:
            text = text.replace(char, "_")
        text = text.replace(" ", "_")
        return text.strip("._") or "element"

    def _get_selected_linear_element_export_info(self):
        selected_info = self._get_current_selected_support_info()
        if not selected_info:
            return None
        role = str(selected_info.get("role") or "").strip()
        if role not in ("lines", "line", "linear", "element_linear"):
            return None
        index = int(selected_info.get("index", -1))
        eid = int(selected_info.get("eid"))
        props_list = list((self.current_model_data or {}).get("line_properties", []) or [])
        props = props_list[index] if 0 <= index < len(props_list) and isinstance(props_list[index], dict) else {}
        name = str(props.get("base_type_label") or props.get("type_label") or tr_ui("prop_linear_element")).strip()
        user_id = str(props.get("user_id") or eid).strip()
        return {"eid": eid, "index": index, "name": name, "user_id": user_id, "props": props}

    def export_analysis_results_csv(self):
        info = self._get_selected_linear_element_export_info()
        case_entry = self._get_selected_analysis_case_entry()
        if not info or not case_entry or not isinstance(self.project_session, ProjectSessionManager) or not self.project_session.can_read_results():
            self._set_analysis_results_output_message(tr_ui("analysis_results_export_not_available"))
            return
        fto_path = normalize_windows_path(self.fto_edit.text().strip()) if self.fto_edit is not None else ""
        base_dir = os.path.dirname(fto_path) if fto_path else ""
        if not base_dir:
            self._set_analysis_results_output_message(tr_ui("analysis_results_export_not_available"))
            return
        file_name = f"{self._sanitize_export_stem(info.get('name'))}_{self._sanitize_export_stem(info.get('user_id'))}.xlsx"
        xlsx_path = os.path.join(base_dir, file_name)
        if os.path.exists(xlsx_path):
            answer = QMessageBox.question(
                self,
                tr_ui("analysis_results_export_confirm_title"),
                tr_ui("analysis_results_export_confirm_overwrite"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            analysis_case_id = int((case_entry or {}).get("eid", (case_entry or {}).get("id", 0)) or 0)
            payloads = read_linear_element_all_families_export(
                self.project_session.host.rstrip("/"),
                int(info.get("eid")),
                analysis_case_id,
            )
            sheet_titles = {
                "deplacements": tr_ui("analysis_results_export_sheet_displacements"),
                "efforts": tr_ui("analysis_results_export_sheet_forces"),
                "contraintes": tr_ui("analysis_results_export_sheet_stresses"),
            }
            workbook = Workbook()
            first_sheet = True
            written = 0
            for family_key in ("deplacements", "efforts", "contraintes"):
                payload = payloads.get(family_key) if isinstance(payloads, dict) else {}
                rows = list((payload or {}).get("rows", []) or [])
                components = list((payload or {}).get("components", []) or [])
                if not rows or not components:
                    continue
                if first_sheet:
                    ws = workbook.active
                    ws.title = sheet_titles.get(family_key, family_key)
                    first_sheet = False
                else:
                    ws = workbook.create_sheet(title=sheet_titles.get(family_key, family_key))
                ws.append(["abscissa", *components])
                for row in rows:
                    ws.append([row.get("abscissa", ""), *[row.get(key, "") for key in components]])
                written += 1
            if written == 0:
                self._set_analysis_results_output_message(tr_ui("analysis_results_export_no_data"))
                self.log(tr_log("results_export_no_data", eid=info.get("eid")), "warn")
                return
            workbook.save(xlsx_path)
            self.log(tr_ui("analysis_results_export_workbook_success", path=xlsx_path), "ok")
        except OSError:
            self.log(tr_log("results_export_write_error", path=xlsx_path), "error")
        except PermissionError:
            self.log(tr_log("results_export_write_error", path=xlsx_path), "error")
        except Exception:
            self.log(tr_log("results_export_write_error", path=xlsx_path), "error")

    def _ifc_export_logger(self, message, level="info"):
        try:
            self.log(str(message), level)
        except Exception:
            pass

    def export_ifc_from_viewer(self):
        if ad_ifc_exporter is None:
            msg = tr_ui("export_ifc_module_missing")
            self.log(msg, "error")
            QMessageBox.critical(self, tr_ui("export_ifc_title"), msg)
            return

        fto_path = normalize_windows_path(self.fto_edit.text().strip()) if self.fto_edit is not None else ""
        base_dir = os.path.dirname(fto_path) if fto_path else ""
        suggested_name = os.path.splitext(os.path.basename(fto_path))[0] + ".ifc" if fto_path else "export.ifc"

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            tr_ui("export_ifc_title"),
            os.path.join(base_dir, suggested_name) if base_dir else suggested_name,
            tr_ui("export_ifc_filter"),
        )
        if not out_path:
            return

        project_session = self.project_session if isinstance(self.project_session, ProjectSessionManager) else None
        host = ""
        if project_session is not None and getattr(project_session, "host", ""):
            host = str(project_session.host).strip()
        elif getattr(self, "api_edit", None) is not None:
            host = str(self.api_edit.text() or "").strip()
        host = (host or DEFAULT_HOST).rstrip("/")

        can_use_open_project = False
        if project_session is not None and getattr(project_session, "is_open", False):
            session_fto = normalize_windows_path(getattr(project_session, "fto_path", "") or "")
            can_use_open_project = bool(session_fto) and (not fto_path or session_fto == fto_path)

        if not can_use_open_project and not fto_path:
            msg = tr_ui("export_ifc_no_project")
            self.log(msg, "warn")
            QMessageBox.warning(self, tr_ui("export_ifc_title"), msg)
            return

        self.log(tr_log("ifc_export_module_version", version=getattr(ad_ifc_exporter, "VERSION", "?")), "info")
        self.log(tr_log("ifc_export_started", path=out_path), "info")
        self._set_analysis_results_output_message(tr_ui("export_ifc_running"))

        try:
            if can_use_open_project:
                ad_ifc_exporter.export_ifc_from_open_project(
                    host=host,
                    out_path=out_path,
                    include_loads=False,
                    project_name=os.path.basename(fto_path) if fto_path else "ViewerProject",
                    logger=self._ifc_export_logger,
                    check_api_first=True,
                )
            else:
                ad_ifc_exporter.export_ifc_from_fto(
                    host=host,
                    fto_path=fto_path,
                    out_path=out_path,
                    include_loads=False,
                    logger=self._ifc_export_logger,
                    check_api_first=True,
                    close_project_on_exit=True,
                )
            success_path = normalize_windows_path(out_path)
            success_message = tr_ui("export_ifc_success", path=success_path)
            self._set_analysis_results_output_message(success_message)
            QMessageBox.information(self, tr_ui("export_ifc_title"), success_message)
        except Exception as e:
            details = str(e)
            self.log(tr_log("ifc_export_failed", details=details), "error")
            self._set_analysis_results_output_message(tr_ui("export_ifc_failed", details=details))
            QMessageBox.critical(self, tr_ui("export_ifc_title"), tr_ui("export_ifc_failed", details=details))

    def apply_analysis_results(self):
        self.current_linear_diagram_payload = None
        selected_info = self._get_current_selected_support_info()
        current_selection = dict(self.current_analysis_selection or {})
        case_entry = self._get_selected_analysis_case_entry()
        family_key = self._get_selected_analysis_result_family_key()
        family_label = self.analysis_results_value_combo.currentText().strip() if self.analysis_results_value_combo is not None else ""
        value_key = self._get_selected_analysis_result_component_key()
        value_label = self.analysis_results_component_combo.currentText().strip() if self.analysis_results_component_combo is not None else ""
        if not selected_info or not case_entry:
            self._set_analysis_results_output_message(tr_ui("analysis_results_select_supported_element_and_case"))
            return
        role = str(selected_info.get("role") or "").strip()
        if not family_key:
            self._set_analysis_results_output_message(tr_ui("analysis_results_invalid_type"))
            return
        if role in ("lines", "line", "linear", "element_linear") and not value_key:
            self._set_analysis_results_output_message(tr_ui("analysis_results_invalid_linear_value"))
            return
        if self.viewer is not None and role in ("lines", "line", "linear", "element_linear"):
            self.viewer.clear_result_diagram()
        centroid_info = None
        if self.viewer is not None:
            if role == "support_planar":
                try:
                    centroid_info = self.viewer.get_planar_support_centroid_info(int(current_selection.get("index", -1)))
                except Exception:
                    centroid_info = None
            else:
                self.viewer.clear_planar_support_result_centroid()
        analysis_case_id = int((case_entry or {}).get("eid", (case_entry or {}).get("id", 0)) or 0)
        self.analysis_results_apply_btn.setEnabled(False)
        self._set_analysis_results_output_message(tr_ui("analysis_results_loading"))
        self.analysis_results_worker = LoadAnalysisResultsWorker(
            self.project_session,
            int(selected_info.get("eid")),
            analysis_case_id,
            family_key,
            role,
            value_key,
        )
        self.current_analysis_result_family_key = family_key
        self.current_analysis_result_type_label = family_label or _analysis_result_display_label(family_key)
        self.current_analysis_result_value_label = self.current_analysis_result_type_label
        self.current_analysis_result_component_label = value_key or value_label
        self.analysis_results_worker.success.connect(lambda payload, role=role, centroid=centroid_info: self._on_analysis_results_loaded(payload, role, centroid))
        self.analysis_results_worker.error.connect(self._on_analysis_results_error)
        self.analysis_results_worker.finished.connect(self._on_analysis_results_worker_finished)
        self.analysis_results_worker.start()

    def _on_analysis_results_loaded(self, payload, support_role: str = "", centroid_info=None):
        role = str(support_role or (self.current_analysis_selection or {}).get("role") or "").strip()
        if isinstance(payload, dict) and payload.get("kind") == "linear_diagram":
            series = list(payload.get("series") or [])
            if self.viewer is not None:
                self.viewer.clear_result_diagram()
            if not series:
                self.current_linear_diagram_payload = None
                self._set_analysis_results_output_message("Aucune valeur de diagramme disponible pour cette sélection.")
                return
            line_index = int((self.current_analysis_selection or {}).get("index", -1))
            lines = list((self.current_model_data or {}).get("lines", []) or [])
            if self.viewer is None or line_index < 0 or line_index >= len(lines):
                self.current_linear_diagram_payload = None
                self._set_analysis_results_output_message("Diagramme calculé, mais l'élément filaire sélectionné est introuvable dans la vue.")
                return
            line_properties = list((self.current_model_data or {}).get("line_properties", []) or [])
            line_property = line_properties[line_index] if 0 <= line_index < len(line_properties) else {}
            payload = dict(payload)
            payload["selection"] = dict(self.current_analysis_selection or {})
            self.current_linear_diagram_payload = payload
            self.viewer.set_linear_result_diagram(lines[line_index], series, str(payload.get("title") or ""), line_property)
            unit = str(payload.get("unit") or "").strip()
            max_abs = max(abs(float((entry or {}).get("value", 0.0))) for entry in series)
            suffix = f" {unit}" if unit else ""
            display_family = self.analysis_results_value_combo.currentText().strip() if self.analysis_results_value_combo is not None else _analysis_result_display_label(str(payload.get("family_label") or ""))
            display_component = self.analysis_results_component_combo.currentText().strip() if self.analysis_results_component_combo is not None else str(payload.get("value_label") or "").strip()
            display_title = f"{display_family} {display_component}" if display_component else display_family
            self._set_analysis_results_output_message(
                tr_ui("analysis_results_linear_diagram_shown", title=display_title, points=len(series), max_abs=f"{max_abs:.6g}", suffix=suffix)
            )
            return
        if self.viewer is not None and role in ("lines", "line", "linear", "element_linear"):
            self.viewer.clear_result_diagram()
        rows = list(payload or []) if isinstance(payload, list) else []
        if role == "support_planar":
            if self.viewer is not None:
                if rows and isinstance(centroid_info, dict):
                    self.viewer.show_planar_support_result_centroid(centroid_info)
                else:
                    self.viewer.clear_planar_support_result_centroid()
            if isinstance(centroid_info, dict):
                try:
                    rows.extend([
                        {"kind": "section_title", "name": tr_ui("prop_cg_coordinates")},
                        {"name": "X", "value": f"{float(centroid_info.get('x')):.3f} m"},
                        {"name": "Y", "value": f"{float(centroid_info.get('y')):.3f} m"},
                        {"name": "Z", "value": f"{float(centroid_info.get('z')):.3f} m"},
                    ])
                except Exception:
                    pass
        elif self.viewer is not None:
            self.viewer.clear_planar_support_result_centroid()
        self._render_analysis_results_rows("", rows)
    def _on_analysis_results_error(self, error_text: str):
        self.current_linear_diagram_payload = None
        if self.viewer is not None:
            self.viewer.clear_planar_support_result_centroid()
        self._set_analysis_results_output_message("Erreur lors de la lecture des résultats.")
        text = str(error_text or "").strip()
        if text:
            self.log("Erreur lecture résultats", "error")
            for line in text.splitlines()[:12]:
                self.log(line, "error")

    def _on_analysis_results_worker_finished(self):
        self.analysis_results_worker = None
        self._update_analysis_results_apply_button()

    def on_viewer_selection_changed(self, selection: dict):
        self.current_linear_diagram_payload = None
        if self.viewer is not None:
            self.viewer.clear_planar_support_result_centroid()
            self.viewer.clear_result_diagram()
        if self.viewer is not None and not self.viewer.has_isolated_selection():
            self._apply_isolate_button_icon(False)
        self._update_analysis_results_value_combo(selection)
        if not selection:
            self._set_properties_message(tr_ui("select_element"))
            return

        role = selection.get("role")
        if role in ("lines", "line", "linear", "element_linear"):
            items = []
            if isinstance(self.current_model_data, dict):
                items = list(self.current_model_data.get("line_properties", []) or [])
            index = int(selection.get("index", -1))
            if 0 <= index < len(items):
                self._render_linear_element_properties(items[index])
            else:
                self._set_properties_message("Aucune propriété disponible pour cet élément filaire.")
            return

        if role == "support_punctual":
            items = []
            if isinstance(self.current_model_data, dict):
                items = list(self.current_model_data.get("punctual_support_properties", []) or [])
            index = int(selection.get("index", -1))
            if 0 <= index < len(items):
                self._render_punctual_support_properties(items[index])
            else:
                self._set_properties_message("Aucune propriété disponible pour cet appui ponctuel.")
            return

        if role == "support_linear":
            items = []
            if isinstance(self.current_model_data, dict):
                items = list(self.current_model_data.get("linear_support_properties", []) or [])
            index = int(selection.get("index", -1))
            if 0 <= index < len(items):
                self._render_punctual_support_properties(items[index])
            else:
                self._set_properties_message("Aucune propriété disponible pour cet appui linéaire.")
            return

        if role == "support_planar":
            items = []
            if isinstance(self.current_model_data, dict):
                items = list(self.current_model_data.get("planar_support_properties", []) or [])
            index = int(selection.get("index", -1))
            if 0 <= index < len(items):
                self._render_punctual_support_properties(items[index])
            else:
                self._set_properties_message("Aucune propriété disponible pour cet appui surfacique.")
            return

        if role in ("planars", "planar", "element_planar"):
            items = []
            if isinstance(self.current_model_data, dict):
                items = list(self.current_model_data.get("planar_properties", []) or [])
            index = int(selection.get("index", -1))
            if 0 <= index < len(items):
                self._render_planar_element_properties(items[index])
            else:
                self._set_properties_message("Aucune propriété disponible pour cet élément surfacique.")
            return

        self._set_properties_message("Propriétés disponibles pour les éléments filaires, surfaciques et les appuis.")

    def _install_view_shortcuts(self):
        if self.shortcut_view_front_back is not None:
            return

        def bind(shortcut_attr: str, key_sequence: str, handler):
            shortcut = QShortcut(QKeySequence(key_sequence), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(handler)
            setattr(self, shortcut_attr, shortcut)

        bind("shortcut_view_front_back", "Alt+&", self.viewer_front_back_proxy)
        bind("shortcut_view_left_right", "Alt+é", self.viewer_left_right_proxy)
        bind("shortcut_view_top_bottom", 'Alt+"', self.viewer_top_bottom_proxy)
        bind("shortcut_view_iso", "Alt+'", self.viewer_iso_proxy)

    def viewer_fit_proxy(self):
        if self.viewer:
            self.viewer.fit_view()

    def viewer_front_back_proxy(self):
        if not self.viewer:
            return
        if self._front_is_back:
            self.viewer.set_front_view()
        else:
            self.viewer.set_back_view()
        self._front_is_back = not self._front_is_back

    def viewer_left_right_proxy(self):
        if not self.viewer:
            return
        if self._left_is_right:
            self.viewer.set_left_view()
        else:
            self.viewer.set_right_view()
        self._left_is_right = not self._left_is_right

    def viewer_top_bottom_proxy(self):
        if not self.viewer:
            return
        if self._top_is_bottom:
            self.viewer.set_top_view()
        else:
            self.viewer.set_bottom_view()
        self._top_is_bottom = not self._top_is_bottom

    def viewer_iso_proxy(self):
        if self.viewer:
            self.viewer.set_isometric_view()

    def _extract_filter_choices(self, model_data: dict):
        line_props = list((model_data or {}).get("line_properties", []) or [])
        planar_props = list((model_data or {}).get("planar_properties", []) or [])
        sections = sorted({str((p or {}).get("section", "N/A")) for p in line_props})
        thicknesses = sorted({str((p or {}).get("thickness", "N/A")) for p in planar_props})
        materials = sorted({str((p or {}).get("material", "N/A")) for p in (line_props + planar_props)})
        return sections, thicknesses, materials

    def open_filter_dialog(self):
        if self.current_model_data is None or self.viewer is None:
            return
        dlg = FilterDialog(
            self.current_sections,
            self.current_thicknesses,
            self.current_materials,
            self.selected_sections,
            self.selected_thicknesses,
            self.selected_materials,
            self.filter_dialog_tab_index,
            self,
        )
        if dlg.exec() == QDialog.Accepted:
            sections, thicknesses, materials = dlg.get_values()
            self.filter_dialog_tab_index = dlg.get_active_tab_index()
            self.selected_sections = set(str(v) for v in sections)
            self.selected_thicknesses = set(str(v) for v in thicknesses)
            self.selected_materials = set(str(v) for v in materials)
            self.viewer.set_structural_filters(self.selected_sections, self.selected_thicknesses, self.selected_materials)
            self._update_display_checkboxes()
            self._refresh_mesh_display()

    def clear_structural_filters(self):
        if self.current_model_data is None or self.viewer is None:
            return
        self.selected_sections = set(self.current_sections)
        self.selected_thicknesses = set(self.current_thicknesses)
        self.selected_materials = set(self.current_materials)
        self.viewer.set_structural_filters(self.selected_sections, self.selected_thicknesses, self.selected_materials)
        self._update_display_checkboxes()
        self._refresh_mesh_display()

    def _make_isolate_icon(self, active: bool):
        size = 18
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        stroke = QColor(ACCENT if active else FG)
        faint = QColor(FG_DIM)
        pen = QPen(stroke, 1.25)
        pen_faint = QPen(faint, 1.15)
        painter.setBrush(Qt.NoBrush)

        left_x = 1.4
        left_w = 4.2
        left_h = 3.1
        left_ys = [1.2, 7.1, 13.0]

        painter.setPen(pen)
        for y in left_ys:
            rect = QRectF(left_x, y, left_w, left_h)
            painter.drawRect(rect)
            painter.drawLine(rect.left() + 0.45, rect.top() + 0.45, rect.right() - 0.45, rect.bottom() - 0.45)
            painter.drawLine(rect.right() - 0.45, rect.top() + 0.45, rect.left() + 0.45, rect.bottom() - 0.45)

        painter.setPen(pen_faint)
        y_mid = size / 2.0
        painter.drawLine(7.0, y_mid, 11.0, y_mid)
        painter.drawLine(10.0, y_mid - 1.6, 11.0, y_mid)
        painter.drawLine(10.0, y_mid + 1.6, 11.0, y_mid)

        painter.setPen(pen)
        rect_right = QRectF(12.2, 7.1, 4.4, 3.1)
        painter.drawRect(rect_right)

        painter.end()
        return QIcon(pix)

    def _apply_isolate_button_icon(self, active: bool):
        if self.isolate_btn is None:
            return
        self.isolate_btn.setIcon(self._make_isolate_icon(bool(active)))
        self.isolate_btn.setIconSize(QSize(18, 18))
        self.isolate_btn.setChecked(bool(active))
        self.isolate_btn.setToolTip(tr_ui("tooltip_isolation_active") if active else tr_ui("tooltip_isolate"))

    def toggle_isolation(self):
        if self.current_model_data is None or self.viewer is None:
            self._apply_isolate_button_icon(False)
            return
        if self.viewer.has_isolated_selection():
            self.viewer.set_isolated_selection(None)
            self._apply_isolate_button_icon(False)
            self._update_display_checkboxes()
            self._refresh_mesh_display()
            return
        selection = dict(self.current_analysis_selection or {})
        role = str(selection.get("role") or "").strip()
        index = int(selection.get("index", -1))
        if not role or index < 0:
            self._set_analysis_results_output_message("Sélectionnez un élément avant d'activer l'isolation.")
            self._apply_isolate_button_icon(False)
            return
        self.viewer.set_isolated_selection({"role": role, "index": index})
        self._apply_isolate_button_icon(True)
        self._update_display_checkboxes()
        self._refresh_mesh_display()

    def on_analysis_scale_changed(self, value: float):
        if self.viewer is not None:
            self.viewer.set_linear_result_scale_factor(value)
        if self.analysis_results_scale_spin is not None:
            self.analysis_results_scale_spin.setToolTip(f"Échelle diagramme : {float(value):.1f}")
        self._refresh_current_linear_diagram()

    def _refresh_current_linear_diagram(self):
        payload = self.current_linear_diagram_payload if isinstance(self.current_linear_diagram_payload, dict) else None
        if not payload or payload.get("kind") != "linear_diagram":
            return
        selection = dict(payload.get("selection") or {})
        line_index = int(selection.get("index", -1))
        lines = list((self.current_model_data or {}).get("lines", []) or [])
        if self.viewer is None or line_index < 0 or line_index >= len(lines):
            return
        line_properties = list((self.current_model_data or {}).get("line_properties", []) or [])
        line_property = line_properties[line_index] if 0 <= line_index < len(line_properties) else {}
        series = list(payload.get("series") or [])
        if not series:
            self.viewer.clear_result_diagram()
            return
        self.viewer.set_linear_result_diagram(lines[line_index], series, str(payload.get("title") or ""), line_property)

    def _format_display_checkbox_text(self, key, count=None):
        label = tr_ui(key)
        if count is None:
            return label
        return f"{label} ({count})"

    def _update_display_checkboxes(self):
        counts = self.viewer.get_display_counts()
        self.chk_lines.setText(self._format_display_checkbox_text("show_lines", counts["lines"]))
        self.chk_planars.setText(self._format_display_checkbox_text("show_planars", counts["planars"]))
        self.chk_load_areas.setText(self._format_display_checkbox_text("show_load_areas", counts["load_areas"]))
        self.chk_support_punctual.setText(self._format_display_checkbox_text("show_support_punctual", counts["support_punctual"]))
        self.chk_support_linear.setText(self._format_display_checkbox_text("show_support_linear", counts["support_linear"]))
        self.chk_support_planar.setText(self._format_display_checkbox_text("show_support_planar", counts["support_planar"]))
        self.chk_marker.setText(tr_ui("show_marker"))
        # Le maillage n'est disponible que si le fichier chargé possède des résultats.
        # setEnabled(False) grise aussi le libellé nativement sous Qt.
        # On ne touche PAS à setChecked ici — l'état coché est préservé lors des
        # filtres/isolation. La réinitialisation à décoché se fait uniquement dans
        # set_loading(True) au début d'un nouveau chargement.
        has_results = bool(self.current_model_has_analysis_results)
        if self.chk_mesh is not None:
            self.chk_mesh.setEnabled(has_results)

    def _refresh_mesh_display(self):
        """Reconstruit le maillage VTK pour ne montrer que les éléments visibles.

        N'est appelé que si la case 'Afficher le maillage' est cochée et que
        des données FEM sont disponibles. Sans effet sinon.
        """
        if self.viewer is None:
            return
        if self.chk_mesh is None or not self.chk_mesh.isChecked():
            return
        if not self._fem_nodes or not self._fem_connectivity_by_eid:
            return
        self.viewer.refresh_mesh(self._fem_nodes, self._fem_connectivity_by_eid)

    def clear_log(self):
        self.log_edit.clear()

    def _set_load_progress(self, value: int, message: str = ""):
        value = max(0, min(100, int(value)))
        if self.load_progress_bar is not None:
            self.load_progress_bar.setValue(value)
            self.load_progress_bar.setFormat(f"{value} %")
        if self.load_progress_label is not None:
            self.load_progress_label.setText(message or tr_ui("loading"))

    def on_load_progress(self, value: int, message: str):
        self._relocate_progress_container()
        if self.load_progress_container is not None:
            self.load_progress_container.setVisible(True)
        if self.shared_progress_container is not None:
            self.shared_progress_container.setVisible(True)
        self._set_load_progress(value, message)

    def _update_transparency_controls_state(self):
        mode = self.cmb_display_mode.currentData() if self.cmb_display_mode else None
        enabled = (mode != "full")
        if self.transparency_slider is not None:
            self.transparency_slider.setEnabled(enabled)
        if self.transparency_value_label is not None:
            color = FG_DIM if enabled else BORDER
            self.transparency_value_label.setStyleSheet(f"color:{color}; min-width:48px;")

    def _update_api_button_state(self):
        running = bool(self.api_server_process and self.api_server_process.poll() is None)
        if self.start_api_btn is None:
            return
        if running:
            self.start_api_btn.setText(tr_ui("stop_api"))
            self.start_api_btn.setObjectName("apiStopBtn")
        else:
            self.start_api_btn.setText(tr_ui("start_api"))
            self.start_api_btn.setObjectName("")
            self.api_server_process = None
            self.api_server_started_by_viewer = False
        self.start_api_btn.style().unpolish(self.start_api_btn)
        self.start_api_btn.style().polish(self.start_api_btn)
        self.start_api_btn.update()

    def apply_theme(self, theme_name: str):
        self.theme_name = theme_name if theme_name in QT_MATERIAL_THEMES else DEFAULT_THEME
        set_active_theme(self.theme_name)

        # Apply qt-material stylesheet
        theme_file = QT_MATERIAL_THEMES.get(self.theme_name, QT_MATERIAL_THEMES[DEFAULT_THEME])
        apply_stylesheet(self.app_ref, theme=theme_file, extra={
            'font_family': 'Segoe UI',
            'font_size': '13px',
            'density_scale': '-2',
        })
        # Surcharge compacte pour QMenu (extra['QMenu'] non fiable sur tous les OS)
        self.app_ref.setStyleSheet(
            self.app_ref.styleSheet() +
            f"""
            QMenu::item {{
                padding: -2px 12px -2px 8px;
                min-height: 18px;
            }}
            QMenu::separator {{
                height: 1px;
                margin: 2px 6px;
            }}
            """
        )

        # Re-apply our custom tweaks on top
        self._apply_style()

        if self.transparency_value_label is not None:
            self.transparency_value_label.setStyleSheet(f"color:{FG_DIM}; min-width:48px;")
        if self.load_progress_label is not None:
            self.load_progress_label.setStyleSheet(f"color:{FG_DIM};")
        if self.help_label is not None:
            self.help_label.setStyleSheet(f"color:{FG_DIM};")

        for card in self.findChildren(Card):
            card.apply_theme()

        if self.viewer is not None:
            self.viewer.apply_theme()

        self._update_transparency_controls_state()
        self._update_api_button_state()
        if self.act_theme_dark is not None:
            self.act_theme_dark.setChecked(self.theme_name == "dark")
        if self.act_theme_light is not None:
            self.act_theme_light.setChecked(self.theme_name == "light")

        if self.current_model_data is not None:
            self._render_results(self.current_model_data)
        if not self._suspend_config_save:
            self.save_config()


    def open_configuration_dialog(self):
        dlg = ApiServerConfigDialog(self.api_server_exe, self)
        if dlg.exec() == QDialog.Accepted:
            self.api_server_exe = dlg.get_value()
            self.save_config()

    def open_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def start_api_server(self):
        exe_path = normalize_windows_path(self.api_server_exe)
        self.api_server_exe = exe_path

        if not exe_path or not os.path.isfile(exe_path):
            self.log(tr_err("api_server_exe_not_found", path=exe_path), "error")
            QMessageBox.warning(self, tr_ui("menu_configuration"), tr_err("api_server_exe_not_found", path=exe_path))
            return

        try:
            self.log(tr_log("api_server_starting", path=exe_path), "info")
            self.api_server_process = subprocess.Popen([exe_path, "/console"], cwd=os.path.dirname(exe_path) or None)
            self.api_server_started_by_viewer = True
            self._update_api_button_state()
            self.log(tr_log("api_server_started"), "ok")
        except Exception as e:
            details = str(e).strip() or e.__class__.__name__
            self.log(tr_err("api_server_start_failed", details=details), "error")
            QMessageBox.critical(self, tr_ui("menu_configuration"), tr_err("api_server_start_failed", details=details))

    def stop_api_server(self, log_on_success: bool = True):
        try:
            if self.api_server_process and self.api_server_process.poll() is None:
                self.api_server_process.terminate()
                try:
                    self.api_server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.api_server_process.kill()
                if log_on_success:
                    self.log(tr_log("api_server_stopped"), "ok")
        finally:
            self.api_server_process = None
            self.api_server_started_by_viewer = False
            self._update_api_button_state()

    def _restart_api_server(self) -> bool:
        exe_path = normalize_windows_path(self.api_server_exe)
        self.api_server_exe = exe_path
        if not exe_path or not os.path.isfile(exe_path):
            self.log(tr_err("api_server_exe_not_found", path=exe_path), "error")
            return False
        self.stop_api_server(log_on_success=False)
        try:
            self.log(tr_log("api_server_restarting"), "info")
            self.api_server_process = subprocess.Popen([exe_path, "/console"], cwd=os.path.dirname(exe_path) or None)
            self.api_server_started_by_viewer = True
            self._update_api_button_state()
        except Exception as e:
            details = str(e).strip() or e.__class__.__name__
            self.log(tr_err("api_server_start_failed", details=details), "error")
            return False

        deadline = time.time() + 20.0
        host = self.host_edit.text().strip().rstrip("/") if self.host_edit is not None else ""
        while time.time() < deadline:
            try:
                check_port(host)
                self.log(tr_log("api_server_restarted"), "ok")
                return True
            except Exception:
                time.sleep(0.5)
        self.log("L'API ne répond pas après redémarrage.", "error")
        return False

    def _reset_api_between_model_loads_if_needed(self) -> bool:
        session = self.project_session if isinstance(self.project_session, ProjectSessionManager) else None
        if session is None or not session.keep_open or not session.has_results:
            return True
        self.log(tr_log("api_session_full_reset_before_model_change"), "warn")
        try:
            if self.viewer is not None:
                self.viewer.clear_result_diagram()
                self.viewer.clear_selection()
        except Exception:
            pass
        session.reset_api_session()
        self.project_session = None
        return self._restart_api_server()

    def toggle_api_server(self):
        running = bool(self.api_server_process and self.api_server_process.poll() is None)
        if running:
            self.stop_api_server(log_on_success=True)
        else:
            self.start_api_server()

    def open_settings_dialog(self):
        dlg = SettingsDialog(
            self.viewer.linear_line_width,
            self.viewer.planar_line_width,
            self.viewer.opening_line_width,
            self.viewer.load_area_line_width,
            self.viewer.support_punctual_size,
            self.viewer.support_punctual_line_width,
            self.viewer.support_linear_line_width,
            self.viewer.support_planar_line_width,
            self.viewer.linear_color,
            self.viewer.planar_color,
            self.viewer.opening_color,
            self.viewer.load_area_color,
            self.viewer.support_punctual_color,
            self.viewer.support_linear_color,
            self.viewer.support_planar_color,
            self.viewer.selection_line_width,
            self.viewer.selection_color,
            self.viewer.mesh_line_width,
            self.viewer.mesh_color,
            self
        )
        if dlg.exec() == QDialog.Accepted:
            values = dlg.get_values()

            self.viewer.set_line_widths(
                values["linear_width"],
                values["planar_width"],
                values["opening_width"],
                values["load_area_width"]
            )
            self.viewer.set_support_styles(
                values["support_punctual_size"],
                values["support_punctual_line_width"],
                values["support_linear_line_width"],
                values["support_planar_line_width"]
            )
            self.viewer.set_colors(
                values["linear_color"],
                values["planar_color"],
                values["opening_color"],
                values["load_area_color"],
                values["support_punctual_color"],
                values["support_linear_color"],
                values["support_planar_color"],
            )
            self.viewer.set_selection_style(
                values["selection_color"],
                values["selection_line_width"]
            )
            self.viewer.set_mesh_style(
                values["mesh_color"],
                values["mesh_width"]
            )

            self.log(
                tr_log(
                    "settings_applied",
                    linear=values["linear_width"],
                    planar=values["planar_width"],
                    openings=values["opening_width"],
                    load_areas=values["load_area_width"],
                    support_size=values["support_punctual_size"],
                    support_punctual=values["support_punctual_line_width"],
                    support_linear=values["support_linear_line_width"],
                    support_planar=values["support_planar_line_width"],
                ),
                "ok"
            )
            self.save_config()

    def on_toggle_lines(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_lines(checked)
        self.log(tr_log("show_lines_on" if checked else "show_lines_off"), "info")

    def on_toggle_planars(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_planars(checked)
        self.log(tr_log("show_planars_on" if checked else "show_planars_off"), "info")

    def on_toggle_load_areas(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_load_areas(checked)
        self.log(tr_log("show_load_areas_on" if checked else "show_load_areas_off"), "info")

    def on_toggle_support_punctual(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_support_punctual(checked)
        self.log(tr_log("show_support_punctual_on" if checked else "show_support_punctual_off"), "info")

    def on_toggle_support_linear(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_support_linear(checked)
        self.log(tr_log("show_support_linear_on" if checked else "show_support_linear_off"), "info")

    def on_toggle_support_planar(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_support_planar(checked)
        self.log(tr_log("show_support_planar_on" if checked else "show_support_planar_off"), "info")

    def on_toggle_marker(self, checked: bool):
        if self.viewer:
            self.viewer.set_show_marker(checked)
        self.log(tr_log("show_marker_on" if checked else "show_marker_off"), "info")

    def on_toggle_mesh(self, checked: bool):
        if self.viewer:
            if checked:
                self._refresh_mesh_display()
            else:
                self.viewer.set_show_mesh(False)
        self.log(tr_log("show_mesh_on" if checked else "show_mesh_off"), "info")

    def on_toggle_color_by_section(self, checked: bool):
        if self.viewer:
            self.viewer.set_color_by_section(checked)
        self.log(
            "Couleur par section activée" if checked else "Couleur par section désactivée",
            "info",
        )

    def on_display_mode_changed(self, index: int):
        mode = self.cmb_display_mode.currentData()
        if self.viewer:
            self.viewer.set_display_mode(mode)
        self._update_transparency_controls_state()

        mode_map = {
            "wireframe": "mode_wireframe",
            "hidden_faces": "mode_hidden_faces",
            "wire_hidden": "mode_wire_hidden",
            "full": "mode_full",
        }
        self.log(tr_log(mode_map.get(mode, "mode_wireframe")), "info")

    def on_transparency_changed(self, value: int):
        if self.transparency_value_label:
            self.transparency_value_label.setText(
                tr_ui("transparency_value", value=value)
            )

        if self.viewer:
            self.viewer.set_faces_transparency(value)

    def browse_fto(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            tr_ui("browse_title"),
            self._resolve_initial_browse_dir(),
            tr_ui("browse_filter")
        )
        if filename:
            self.fto_edit.setText(normalize_windows_path(filename))
            self.save_config()

    def log(self, message: str, level: str = "info"):
        colors = {
            "info": FG_DIM,
            "ok": ACCENT2,
            "warn": WARN,
            "error": ERROR_COL,
        }
        prefixes = {
            "info": "",
            "ok": "✓ ",
            "warn": "⚠ ",
            "error": "✗ ",
        }
        color = colors.get(level, FG_DIM)
        prefix = prefixes.get(level, "")
        safe_text = html.escape(prefix + message)
        self.log_edit.append(f'<span style="color:{color};">{safe_text}</span>')
        self.log_edit.moveCursor(QTextCursor.End)

    def _close_project_session(self, log_message: str = "") -> bool:
        session = self.project_session if isinstance(self.project_session, ProjectSessionManager) else None
        if session is None:
            return False
        closed = session.close()
        if closed and log_message:
            self.log(log_message, "info")
        return closed

    def _sync_project_session_state(self, model_data: dict, session_manager=None):
        self.current_analysis_result_value_label = tr_ui("analysis_result_displacements")
        self.current_model_has_analysis_results = bool((model_data or {}).get("has_analysis_results")) if isinstance(model_data, dict) else False
        session = session_manager if isinstance(session_manager, ProjectSessionManager) else None
        if session is None and isinstance(self.worker, LoadModelWorker):
            session = self.worker.session_manager
        self.project_session = session

    def set_loading(self, loading: bool):
        widgets = [
            self.load_btn, self.fit_btn,
            self.view_front_btn, self.view_left_btn, self.view_top_btn, self.view_iso_btn,
            self.transparency_slider,
            self.start_api_btn,
            self.chk_lines, self.chk_planars, self.chk_load_areas,
            self.chk_support_punctual, self.chk_support_linear, self.chk_support_planar,
            self.chk_marker, self.chk_color_by_section, self.cmb_display_mode, self.clear_log_btn
        ]
        for w in widgets:
            if w is not None:
                w.setEnabled(not loading)

        # chk_mesh est géré séparément : il doit toujours être décoché et grisé
        # pendant le chargement, et rester grisé après si aucun résultat n'est dispo.
        if self.chk_mesh is not None:
            if loading:
                self.chk_mesh.setEnabled(False)
                self.chk_mesh.blockSignals(True)
                self.chk_mesh.setChecked(False)
                self.chk_mesh.blockSignals(False)
            else:
                # L'état définitif est appliqué par _update_display_checkboxes
                # appelé dans on_model_loaded / on_model_error.
                pass

        if loading:
            self.load_btn.setText(tr_ui("loading"))
            if self.load_progress_container is not None:
                self.load_progress_container.setVisible(True)
            self._set_load_progress(0, "Préparation du chargement...")
        else:
            self.load_btn.setText(tr_ui("load_model"))
            if self.load_progress_container is not None:
                self.load_progress_container.setVisible(False)
            if self.shared_progress_container is not None:
                self.shared_progress_container.setVisible(False)
            self._set_load_progress(0, "Chargement en attente")
            self._update_transparency_controls_state()

    def load_model(self):
        raw_path = self.fto_edit.text().strip()
        host = self.host_edit.text().strip().rstrip("/")

        if not raw_path:
            self.log(tr_err("no_file_selected"), "error")
            return

        fto_path = normalize_windows_path(raw_path)
        self.fto_edit.setText(fto_path)
        self.save_config()

        if not os.path.exists(fto_path):
            self.log(tr_err("file_not_found", path=fto_path), "error")
            return

        if not os.path.isfile(fto_path):
            self.log(tr_err("path_not_file", path=fto_path), "error")
            return

        self.clear_log()
        self.log(tr_log("api_connection", host=host), "info")
        if not self._reset_api_between_model_loads_if_needed():
            self.log("Impossible de réinitialiser l'API avant le chargement du nouveau modèle.", "error")
            return
        self._close_project_session(tr_log("project_closed_before_new_load"))

        self.set_loading(True)
        self.worker = LoadModelWorker(host, fto_path)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.on_load_progress)
        self.worker.success.connect(self.on_model_loaded)
        self.worker.error.connect(self.on_model_error)
        self.worker.finished.connect(lambda: self.set_loading(False))
        self.worker.start()

    def on_model_loaded(self, model_data: ModelDataDict):
        self.current_model_data = model_data
        self._sync_project_session_state(model_data)
        self.current_sections, self.current_thicknesses, self.current_materials = self._extract_filter_choices(model_data)
        self.selected_sections = set(self.current_sections)
        self.selected_thicknesses = set(self.current_thicknesses)
        self.selected_materials = set(self.current_materials)
        if self.chk_color_by_section is not None:
            self.chk_color_by_section.blockSignals(True)
            self.chk_color_by_section.setChecked(True)
            self.chk_color_by_section.blockSignals(False)
        self._set_load_progress(100, "Rendu terminé.")
        self.viewer.load_model(model_data)
        self.viewer.set_color_by_section(True)
        self.viewer.set_linear_result_scale_factor(self.analysis_results_scale_spin.value() if self.analysis_results_scale_spin is not None else 10.0)
        self.viewer.set_isolated_selection(None)
        self._apply_isolate_button_icon(False)
        self.viewer.set_structural_filters(self.selected_sections, self.selected_thicknesses, self.selected_materials)

        # Chargement du maillage FEM si disponible
        self._fem_nodes = list((model_data or {}).get("fem_nodes", []) or [])
        self._fem_connectivity_by_eid = dict((model_data or {}).get("fem_by_eid", {}) or {})
        if self._fem_nodes and self._fem_connectivity_by_eid:
            total_faces = sum(len(f) for f in self._fem_connectivity_by_eid.values())
            self.log("Maillage FEM : {} nœuds, {} éléments ({} mailles).".format(
                len(self._fem_nodes), len(self._fem_connectivity_by_eid), total_faces), "ok")
            # Le maillage VTK sera construit à la demande via on_toggle_mesh /
            # _refresh_mesh_display. On efface tout acteur résiduel pour l'instant.
            self.viewer.load_mesh([], [])
        else:
            self._fem_nodes = []
            self._fem_connectivity_by_eid = {}
            self.viewer.load_mesh([], [])
            if (model_data or {}).get("has_analysis_results"):
                self.log("Maillage FEM : aucune donnée reçue de l'API.", "warn")
        self._set_properties_message("Sélectionnez un élément pour afficher ses propriétés.")
        self._render_results(model_data)
        self._set_analysis_results_status((model_data or {}).get("has_analysis_results"))
        self._populate_results_case_combination_combo((model_data or {}).get("results_cases_combinations", []))
        self._update_analysis_results_value_combo(None)
        self._set_analysis_results_output_message("Sélectionnez un appui ponctuel, linéaire ou surfacique pour afficher ses résultats.")
        self._update_display_checkboxes()
        self.viewer.apply_display_state(
            show_lines=self.chk_lines.isChecked(),
            show_planars=self.chk_planars.isChecked(),
            show_load_areas=self.chk_load_areas.isChecked(),
            show_support_punctual=self.chk_support_punctual.isChecked(),
            show_support_linear=self.chk_support_linear.isChecked(),
            show_support_planar=self.chk_support_planar.isChecked(),
            show_marker=self.chk_marker.isChecked(),
            display_mode=self.cmb_display_mode.currentData(),
            transparency_percent=self.transparency_slider.value(),
        )

        self.log(tr_log("render_updated"), "ok")
        self.log(
            tr_log(
                "display_counts",
                linear=model_data["linear_count"],
                planar=model_data["planar_count"],
                load_areas=model_data["load_area_count"],
                openings=model_data["openings_count"],
            ),
            "ok"
        )
        self.log(
            tr_log(
                "support_counts",
                punctual=model_data["punctual_support_count"],
                linear=model_data["linear_support_count"],
                planar=model_data["planar_support_count"],
            ),
            "ok"
        )

    def on_model_error(self, error_text: str):
        self.project_session = None
        self.current_model_has_analysis_results = False
        self._set_load_progress(0, "Chargement interrompu.")
        self._set_analysis_results_status(False)
        self._update_analysis_results_value_combo(None)
        self._set_analysis_results_output_message("Sélectionnez un appui ponctuel, linéaire ou surfacique pour afficher ses résultats.")
        if self.chk_mesh is not None:
            self.chk_mesh.setEnabled(False)
            self.chk_mesh.blockSignals(True)
            self.chk_mesh.setChecked(False)
            self.chk_mesh.blockSignals(False)
        self._fem_nodes = []
        self._fem_connectivity_by_eid = {}
        if self.viewer is not None:
            self.viewer.load_mesh([], [])
        text = error_text.strip()
        low = text.lower()

        if (
            "api non joignable" in low
            or "impossible de contacter l'api" in low
            or "api advance design ne répond pas" in low
        ):
            self.log(tr_err("api_no_response"), "error")
            self.log(tr_err("api_check_advice"), "error")
            return

        if (
            "déjà ouvert" in low
            or "deja ouvert" in low
            or "verrouillé" in low
            or "already open" in low
            or "locked" in low
        ):
            self.log(tr_err("file_already_open_short"), "error")
            return

        if (
            "openproject échec api" in low
            and "project_open_failed" in low
            and "engine returned failure" in low
            and "engine_error" in low
        ):
            self.log(tr_err("api_engine_not_initialized"), "error")
            return

        self._populate_results_case_combination_combo([])
        self.log(tr_err("load_error"), "error")
        for line in text.splitlines():
            self.log(line, "error")

    def closeEvent(self, event):
        try:
            if self.worker and self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(1000)
        except RuntimeError:
            pass

        try:
            if self.analysis_results_worker and self.analysis_results_worker.isRunning():
                self.analysis_results_worker.quit()
                self.analysis_results_worker.wait(1000)
        except RuntimeError:
            pass

        try:
            self._close_project_session(tr_log("project_closed_on_exit"))
        except RuntimeError:
            pass

        try:
            if self.api_server_started_by_viewer and self.api_server_process and self.api_server_process.poll() is None:
                self.api_server_process.terminate()
                try:
                    self.api_server_process.wait(timeout=5)
                except Exception:
                    self.api_server_process.kill()
                self.log(tr_log("api_server_stopped_on_exit"), "info")
        except (AttributeError, OSError, RuntimeError):
            pass

        super().closeEvent(event)


def main():
    set_windows_app_user_model_id("graitec.viewer.desktop")
    app = QApplication(sys.argv)
    app_icon = load_app_icon("cube.ico", "cube.png", "icon.ico", "icon.png")
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    qt_translator = QTranslator()
    qt_translator.load(
        "qt_fr",
        QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    )
    app.installTranslator(qt_translator)

    w = MainWindow(app=app)
    w.apply_theme(DEFAULT_THEME)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
