# -*- coding: utf-8 -*-
"""Branche Chargement de l'arbre Systemes : familles, cas, infobulles, masquage
par cas, Selectionner / Isoler sur des charges."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ad_model_data import _build_load_tree, _count_by_load_case


def _families_and_cases():
    family_ids = [5235, 5016, 777]
    families = [
        {"$type": "LoadCaseFamily_LiveLoads", "userID": 2, "userName": "Exploitations"},
        {"$type": "LoadCaseFamily_DeadLoads", "userID": 1, "userName": "Charges Permanentes"},
        {"$type": "LoadCaseFamily_Other", "userID": 3, "userName": "Autres"},   # sans cas
    ]
    case_ids = [5369, 5019, 5238]
    cases = [
        {"userID": 6, "userName": "QB", "loadCaseFamilyID": {"value": 5235}},
        {"userID": 4, "userName": "G", "loadCaseFamilyID": {"value": 5016}},
        {"userID": 5, "userName": "QE", "loadCaseFamilyID": {"value": 5235}},
    ]
    return family_ids, families, case_ids, cases


def test_load_tree_sorts_families_and_cases_and_drops_empty_families():
    tree = _build_load_tree(*_families_and_cases())
    assert [f["name"] for f in tree] == ["Charges Permanentes", "Exploitations"]
    assert [(c["user_id"], c["name"], c["eid"]) for c in tree[1]["cases"]] == [(5, "QE", 5238), (6, "QB", 5369)]


def test_count_by_load_case():
    objects = [{"loadCase": {"value": 10}}, {"loadCase": {"value": 10}}, {"loadCase": 11}, {}]
    assert _count_by_load_case(objects) == {10: 2, 11: 1}


# --- Interface : branche Chargement dans l'arbre Systemes --------------------

def _qt_app():
    import pytest
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        pytest.skip("une QCoreApplication existe deja dans ce processus")
    return app


def _model_data():
    family_ids, families, case_ids, cases = _families_and_cases()
    return {
        "systems_tree": {"roots": [], "nodes": {}},
        "system_direct_items": {},
        "load_tree": _build_load_tree(family_ids, families, case_ids, cases),
        "imposed_displacement_counts": {5019: 1},
        "punctual_loads": [{"load_case_eid": 5019}, {"load_case_eid": 5238}],
        "linear_loads": [{"load_case_eid": 5238}],
        "planar_loads": [{"load_case_eid": 5369}, {"load_case_eid": 5369}],
    }


def _host():
    import types
    import main_window as mw
    from PySide6.QtWidgets import QLabel

    class Host:
        _system_tree_label = staticmethod(mw.MainWindow._system_tree_label)
        _system_tree_tooltip = mw.MainWindow._system_tree_tooltip
        _load_tree_tooltip = mw.MainWindow._load_tree_tooltip
        _load_selection_items = mw.MainWindow._load_selection_items
        _tree_selection_items = mw.MainWindow._tree_selection_items
        _ROLE_COUNT_KEYS = mw.MainWindow._ROLE_COUNT_KEYS
        _SYSTEMS_TOOLTIP_ROLE_ORDER = mw.MainWindow._SYSTEMS_TOOLTIP_ROLE_ORDER
        _LOAD_NODE_ROLE = mw.MainWindow._LOAD_NODE_ROLE
        _LOAD_TOOLTIP_ROLE_ORDER = mw.MainWindow._LOAD_TOOLTIP_ROLE_ORDER
        _populate_systems_tab = mw.MainWindow._populate_systems_tab
        _apply_systems_visibility = mw.MainWindow._apply_systems_visibility

    host = Host()
    host.systems_tree = mw.SystemsTree()
    host.systems_empty_label = QLabel()
    host.current_model_data = _model_data()
    host.dirty = []
    host.viewer = types.SimpleNamespace(
        set_hidden_items=lambda items, rebuild_profiles=True: None,
        _punctual_load_case_filter=None, _linear_load_case_filter=None, _planar_load_case_filter=None,
    )
    host._mark_loads_dirty = lambda *kinds: host.dirty.append(kinds)
    host._refresh_mesh_display = lambda: None
    host._refresh_profiles_if_needed = lambda: None
    host._populate_systems_tab(host.current_model_data)
    return host


def _find(tree, text):
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    it = QTreeWidgetItemIterator(tree)
    while it.value():
        if it.value().text(0) == text:
            return it.value()
        it += 1
    raise AssertionError(text)


def test_loads_branch_lists_families_then_cases():
    from viewer_config import tr_ui

    _qt_app()
    host = _host()
    root = _find(host.systems_tree, tr_ui("loads_tree_root"))
    assert [root.child(i).text(0) for i in range(root.childCount())] == ["Charges Permanentes", "Exploitations"]
    live = root.child(1)
    assert [live.child(i).text(0) for i in range(live.childCount())] == ["5 - QE", "6 - QB"]
    assert host.systems_empty_label.isHidden()   # pas de systeme mais des charges : l'arbre s'affiche


def test_load_tooltips_count_loads_by_type_and_skip_empty_types():
    from viewer_config import tr_ui

    _qt_app()
    host = _host()
    assert _find(host.systems_tree, "4 - G").toolTip(0) == "\n".join([
        tr_ui("selection_count_punctual_load", count=1),
        tr_ui("selection_count_imposed_displacement", count=1),
    ])
    assert _find(host.systems_tree, "Exploitations").toolTip(0) == "\n".join([
        tr_ui("selection_count_punctual_load", count=1),
        tr_ui("selection_count_linear_load", count=1),
        tr_ui("selection_count_planar_load", count=2),
    ])


def test_unchecking_a_case_restricts_visible_load_cases():
    from PySide6.QtCore import Qt

    _qt_app()
    host = _host()
    _find(host.systems_tree, "6 - QB").setCheckState(0, Qt.Unchecked)
    host._apply_systems_visibility()
    assert host.viewer._planar_load_case_filter == {5019, 5238}
    assert host.dirty[-1] == ("punctual", "linear", "planar")

    _find(host.systems_tree, "Exploitations").setCheckState(0, Qt.Unchecked)
    host._apply_systems_visibility()
    assert host.viewer._punctual_load_case_filter == {5019}

    _find(host.systems_tree, "Exploitations").setCheckState(0, Qt.Checked)
    host._apply_systems_visibility()
    assert host.viewer._linear_load_case_filter is None


def test_select_on_a_family_returns_the_loads_of_its_cases():
    _qt_app()
    host = _host()
    items = host._tree_selection_items([_find(host.systems_tree, "Exploitations")])
    assert sorted((i["role"], i["index"]) for i in items) == [
        ("linear_load", 0), ("planar_load", 0), ("planar_load", 1), ("punctual_load", 1),
    ]


def test_select_ignores_the_loads_of_unchecked_cases():
    from PySide6.QtCore import Qt

    _qt_app()
    host = _host()
    _find(host.systems_tree, "6 - QB").setCheckState(0, Qt.Unchecked)
    items = host._tree_selection_items([_find(host.systems_tree, "Exploitations")])
    assert sorted((i["role"], i["index"]) for i in items) == [("linear_load", 0), ("punctual_load", 1)]
