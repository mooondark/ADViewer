# -*- coding: utf-8 -*-
"""Verifie la construction de l'arbre des systemes et la resolution de selection."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ad_model_data import (
    _build_systems_tree,
    _build_system_direct_items,
    collect_system_descendant_eids,
    resolve_system_selection_items,
)


def _eid(v):
    return {"value": v}


def test_build_systems_tree_roots_and_children():
    # 1 -> 2 -> 3 ; 4 est racine isolee ; 5 est un niveau
    system_ids = [1, 2, 3, 4, 5]
    system_objects = [
        {"userID": 1, "userName": "Bloc 1", "subSystemIDs": [_eid(2)]},
        {"userID": 2, "userName": "Etage 0", "subSystemIDs": [_eid(3)]},
        {"userID": 3, "userName": "Poteau", "subSystemIDs": []},
        {"userID": 4, "userName": "Radier", "subSystemIDs": []},
        {"userID": 5, "userName": "Niveau", "isLevel": True, "levelTop": 3.05, "levelBottom": 0.0, "subSystemIDs": []},
    ]
    tree = _build_systems_tree(system_ids, system_objects)
    assert tree["roots"] == [1, 4, 5]
    assert tree["nodes"][1]["children"] == [2]
    assert tree["nodes"][2]["children"] == [3]
    assert tree["nodes"][5]["is_level"] is True
    assert tree["nodes"][5]["level_top"] == 3.05


def test_build_system_direct_items_and_collect_descendants():
    direct = _build_system_direct_items([
        ("lines", [[10], [10, 20], []]),   # index 0 -> systeme 10 ; index 1 -> systemes 10,20
        ("planars", [[20]]),               # index 0 -> systeme 20
    ])
    assert {"role": "lines", "index": 0} in direct[10]
    assert {"role": "lines", "index": 1} in direct[10]
    assert {"role": "lines", "index": 1} in direct[20]
    assert {"role": "planars", "index": 0} in direct[20]

    nodes = {10: {"children": [20]}, 20: {"children": []}}
    descendants = collect_system_descendant_eids(nodes, [10])
    assert descendants == {10, 20}

    items = resolve_system_selection_items(direct, descendants)
    keys = {(it["role"], it["index"]) for it in items}
    assert keys == {("lines", 0), ("lines", 1), ("planars", 0)}


# --- Arbre Systemes (cases de visibilite) et masquage 3D ---------------------

def _qt_app():
    import pytest
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        # tests/test_qt_translation.py cree un QCoreApplication a l'import
        pytest.skip("une QCoreApplication existe deja dans ce processus")
    return app


def _model_data():
    # 1 (Bloc) -> 2 (Etage 0), 3 (Etage 1)
    tree = _build_systems_tree([1, 2, 3], [
        {"userID": 1, "userName": "Bloc", "subSystemIDs": [_eid(2), _eid(3)]},
        {"userID": 2, "userName": "Etage 0", "subSystemIDs": []},
        {"userID": 3, "userName": "Etage 1", "subSystemIDs": []},
    ])
    direct = _build_system_direct_items([
        ("lines", [[2], [3], [2, 3], []]),     # ligne 2 dans les deux etages, ligne 3 hors systeme
        ("support_punctual", [[3]]),
    ])
    return {"systems_tree": tree, "system_direct_items": direct}


def _host():
    import types
    import main_window as mw
    from PySide6.QtWidgets import QLabel

    class Host:
        _system_tree_label = staticmethod(mw.MainWindow._system_tree_label)
        _system_tree_tooltip = mw.MainWindow._system_tree_tooltip
        _ROLE_COUNT_KEYS = mw.MainWindow._ROLE_COUNT_KEYS
        _SYSTEMS_TOOLTIP_ROLE_ORDER = mw.MainWindow._SYSTEMS_TOOLTIP_ROLE_ORDER
        _populate_systems_tab = mw.MainWindow._populate_systems_tab
        _apply_systems_visibility = mw.MainWindow._apply_systems_visibility

    host = Host()
    host.systems_tree = mw.SystemsTree()
    host.systems_empty_label = QLabel()
    host.current_model_data = _model_data()
    host.hidden_calls = []
    host.viewer = types.SimpleNamespace(
        set_hidden_items=lambda items, rebuild_profiles=True: host.hidden_calls.append(
            sorted((i["role"], i["index"]) for i in items)))
    host._refresh_mesh_display = lambda: None
    host._refresh_profiles_if_needed = lambda: None
    host._populate_systems_tab(host.current_model_data)
    return host


def _item(tree, eid):
    from PySide6.QtWidgets import QTreeWidgetItemIterator
    from PySide6.QtCore import Qt

    it = QTreeWidgetItemIterator(tree)
    while it.value():
        if it.value().data(0, Qt.UserRole) == eid:
            return it.value()
        it += 1
    raise AssertionError(eid)


def test_systems_tree_items_are_checked_and_propagate_to_children_and_parent():
    from PySide6.QtCore import Qt

    _qt_app()
    host = _host()
    root, etage0, etage1 = (_item(host.systems_tree, e) for e in (1, 2, 3))
    assert all(i.checkState(0) == Qt.Checked for i in (root, etage0, etage1))

    etage0.setCheckState(0, Qt.Unchecked)
    assert root.checkState(0) == Qt.PartiallyChecked

    root.setCheckState(0, Qt.Unchecked)
    assert etage1.checkState(0) == Qt.Unchecked


def test_unchecked_system_hides_its_items_except_those_of_a_checked_system():
    from PySide6.QtCore import Qt

    _qt_app()
    host = _host()
    _item(host.systems_tree, 3).setCheckState(0, Qt.Unchecked)
    host._apply_systems_visibility()
    # ligne 2 reste visible (aussi dans Etage 0, coche), ligne 3 hors systeme jamais masquee
    assert host.hidden_calls[-1] == [("lines", 1), ("support_punctual", 0)]

    _item(host.systems_tree, 1).setCheckState(0, Qt.Unchecked)
    host._apply_systems_visibility()
    assert host.hidden_calls[-1] == [("lines", 0), ("lines", 1), ("lines", 2), ("support_punctual", 0)]

    _item(host.systems_tree, 1).setCheckState(0, Qt.Checked)
    host._apply_systems_visibility()
    assert host.hidden_calls[-1] == []


def test_systems_tree_draws_branches_without_error():
    _qt_app()
    host = _host()
    host.systems_tree.resize(200, 120)
    host.systems_tree.expandAll()
    assert not host.systems_tree.grab().isNull()


def _viewer_with_lines_and_planars():
    from viewer_widget import VTKViewerWidget

    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._model_data = {
        "line_properties": [{}, {}, {}],
        "planar_properties": [{}, {}],
        "line_eids": [10, 11, 12],
        "planar_eids": [20, 21],
    }
    w._filter_section_names = w._filter_thickness_names = w._filter_material_names = None
    w._isolated_selection = []
    w._hidden_items = set()
    return w


def test_viewer_hidden_items_are_removed_from_visible_elements():
    w = _viewer_with_lines_and_planars()
    rebuilds = []
    w._rebuild_filtered_structural_actors = lambda rebuild_profiles=True: rebuilds.append(rebuild_profiles)

    w.set_hidden_items([{"role": "lines", "index": 1}, {"role": "planars", "index": 0}], rebuild_profiles=False)
    assert rebuilds == [False]
    assert w.get_visible_linear_eids() == [10, 12]
    assert w.get_visible_planar_eids() == [21]

    w.set_hidden_items([])
    assert w.get_visible_linear_eids() == [10, 11, 12]


def test_viewer_hidden_items_also_apply_inside_an_isolation():
    w = _viewer_with_lines_and_planars()
    w._isolated_selection = [{"role": "lines", "index": 0}, {"role": "lines", "index": 1}]
    w._hidden_items = {("lines", 0)}
    assert w.get_visible_linear_eids() == [11]


if __name__ == "__main__":
    test_build_systems_tree_roots_and_children()
    test_build_system_direct_items_and_collect_descendants()
    print("ok")
