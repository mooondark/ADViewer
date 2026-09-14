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


if __name__ == "__main__":
    test_build_systems_tree_roots_and_children()
    test_build_system_direct_items_and_collect_descendants()
    print("ok")
