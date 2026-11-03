# -*- coding: utf-8 -*-
"""Reconstruction des acteurs de structure : quels elements (et quels index du
modele) sont dessines selon l'isolation, les elements masques (arbre Systemes)
et les cas de charge visibles. Les constructeurs VTK sont remplaces par des
enregistreurs : seule la decision est verifiee ici."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget


def _viewer():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._model_data = {
        "lines": ["L0", "L1", "L2"], "line_properties": [{}, {}, {}], "line_sections": ["S0", "S1", "S2"],
        "planars": ["P0", "P1"], "planar_properties": [{}, {}],
        "load_areas": ["A0", "A1"],
        "punctual_supports": ["SP0", "SP1", "SP2"],
        "linear_supports": ["SL0", "SL1"],
        "planar_supports": ["SS0", "SS1"],
    }
    w._filter_section_names = w._filter_thickness_names = w._filter_material_names = None
    w._isolated_selection = []
    w._hidden_items = set()
    for kind, cases in (("punctual", [1, 2, 1]), ("linear", [2, 2]), ("planar", [1, 3])):
        setattr(w, f"_{kind}_load_data", [{"id": f"{kind}{i}", "load_case_eid": c} for i, c in enumerate(cases)])
        setattr(w, f"_{kind}_load_actors", [f"old-{kind}"])
        setattr(w, f"_show_{kind}_loads", True)
        setattr(w, f"_{kind}_load_case_filter", None)
        setattr(w, f"{kind}_load_color", kind)
        setattr(w, f"{kind}_load_line_width", 1.5)
    for name in ("linear", "planar", "opening", "load_area", "support_punctual", "support_linear", "support_planar"):
        setattr(w, f"{name}_color", name)
        setattr(w, f"{name}_line_width", 1.0)
    w.load_areas_faces_base_opacity = w.support_planar_faces_base_opacity = 0.3
    w.load_auto_scale = False
    for kind in ("punctual", "linear", "planar"):
        setattr(w, f"{kind}_load_scale", 1.0)

    log = types.SimpleNamespace(drawn={}, loads={}, removed=[], added=[], rebuilt=[], centroid_cleared=False)
    w.log = log
    w._make_wire_actor = lambda pd, color, width: pd
    w._make_surface_actor = lambda pd, color, opacity: pd
    w._build_lines_polydata = lambda items, element_indexes=None, include_section_colors=True: ("lines", list(items), element_indexes)
    w._build_loops_wire_polydata = lambda items, openings=False, element_indexes=None: ("loops", list(items), element_indexes)
    w._build_faces_polydata = lambda items, element_indexes=None: ("faces", list(items), element_indexes)
    w._build_punctual_supports_polydata = lambda items, element_indexes=None: ("points", list(items), element_indexes)

    def replace_actor(name, actor, role=None, pickable=False):
        log.drawn[name] = actor

    w._replace_actor = replace_actor
    w._rebuild_profiles_actor = lambda idx, lines, sections, synchronous=True: log.drawn.__setitem__("profiles", (idx, lines, sections))
    w._rebuild_planar_faces_actor = lambda: None
    w._apply_visibility_state = lambda: None
    w.clear_planar_support_result_centroid = lambda: setattr(log, "centroid_cleared", True)
    w.renderer = types.SimpleNamespace(ResetCameraClippingRange=lambda: None)
    w.render_window = types.SimpleNamespace(Render=lambda: None)
    w._remove_actor = log.removed.append
    w._add_actor = lambda actor, role=None, pickable=False: log.added.append((role, actor))
    for kind in ("punctual", "linear", "planar"):
        setattr(w, f"_rebuild_{kind}_load_actors", lambda kind=kind: log.rebuilt.append(kind))

        def build(loads, scale, color, case_filter=None, line_width=1.5, global_data=None, kind=kind):
            log.loads[kind] = ([ld["id"] for ld in loads], case_filter, global_data is not None)
            return [((kind, ld["id"]), -1) for ld in loads]

        setattr(w, f"_build_{kind}_load_actors", build)
    return w


def _drawn(w, name):
    _kind, items, indexes = w.log.drawn[name]
    return items, indexes


def test_without_isolation_everything_is_drawn_with_model_indexes():
    w = _viewer()
    w._rebuild_filtered_structural_actors()
    assert _drawn(w, "_lines_actor") == (["L0", "L1", "L2"], [0, 1, 2])
    assert w.log.drawn["profiles"] == ([0, 1, 2], ["L0", "L1", "L2"], ["S0", "S1", "S2"])
    assert _drawn(w, "_planar_actor") == (["P0", "P1"], [0, 1])
    assert _drawn(w, "_load_areas_actor") == (["A0", "A1"], None)
    assert _drawn(w, "_support_punctual_actor") == (["SP0", "SP1", "SP2"], None)
    assert w._support_punctual_indexes is None and w._support_punctual_points == ["SP0", "SP1", "SP2"]
    assert (w.lines_count, w.planars_count, w.load_areas_count) == (3, 2, 2)
    assert (w.support_punctual_count, w.support_linear_count, w.support_planar_count) == (3, 2, 2)
    assert w.log.rebuilt == ["punctual", "linear", "planar"]
    assert w.log.centroid_cleared


def test_hidden_items_are_dropped_and_indexes_kept_aligned():
    w = _viewer()
    w._hidden_items = {("support_punctual", 1), ("load_areas", 0), ("lines", 2), ("planars", 0)}
    w._rebuild_filtered_structural_actors()
    assert _drawn(w, "_lines_actor") == (["L0", "L1"], [0, 1])
    assert _drawn(w, "_planar_actor") == (["P1"], [1])
    assert _drawn(w, "_load_areas_actor") == (["A1"], [1])
    assert _drawn(w, "_load_areas_faces_actor") == (["A1"], [1])
    assert _drawn(w, "_support_punctual_actor") == (["SP0", "SP2"], [0, 2])
    assert w._support_punctual_indexes == [0, 2]
    assert _drawn(w, "_support_linear_actor") == (["SL0", "SL1"], [0, 1])
    assert w.support_punctual_count == 2 and w.load_areas_count == 1


def test_isolation_draws_only_isolated_items_and_rebuilds_isolated_loads():
    w = _viewer()
    w._isolated_selection = [
        {"role": "lines", "index": 1}, {"role": "support_punctual", "index": 2},
        {"role": "support_planar", "index": 0}, {"role": "load_areas", "index": 1},
        {"role": "punctual_load", "index": 0}, {"role": "punctual_load", "index": 2},
        {"role": "linear_load", "index": 1},
    ]
    w._hidden_items = {("support_punctual", 2)}
    w._punctual_load_case_filter = {1}
    w._linear_load_case_filter = {9}
    w._rebuild_filtered_structural_actors()
    assert _drawn(w, "_lines_actor") == (["L1"], [1])
    assert _drawn(w, "_planar_actor") == ([], [])
    assert _drawn(w, "_load_areas_actor") == (["A1"], [1])
    assert _drawn(w, "_support_punctual_actor") == ([], [])
    assert _drawn(w, "_support_linear_actor") == ([], [])
    assert _drawn(w, "_support_planar_actor") == (["SS0"], [0])
    assert w.log.rebuilt == []
    assert w.log.loads == {"punctual": (["punctual0", "punctual2"], None, False)}
    assert w.log.removed == ["old-punctual", "old-linear", "old-planar"]
    assert w.log.added == [("punctual_load", ("punctual", "punctual0")), ("punctual_load", ("punctual", "punctual2"))]
    assert w._punctual_load_actors == [("punctual", "punctual0"), ("punctual", "punctual2")]
    assert w._linear_load_actors == [] and w._planar_load_actors == []
    assert not w.log.centroid_cleared   # un appui surfacique est isole : son centroide reste


def test_isolated_loads_of_a_hidden_type_are_not_built():
    w = _viewer()
    w._isolated_selection = [{"role": "linear_load", "index": 0}, {"role": "planar_load", "index": 1}]
    w._show_linear_loads = False
    w._rebuild_filtered_structural_actors()
    assert w.log.loads == {"planar": (["planar1"], None, True)}
    assert w._linear_load_actors == []
    assert w.log.centroid_cleared


def test_indexes_by_role_groups_valid_indexes():
    from viewer_widget import _indexes_by_role

    selection = [{"role": " lines ", "index": 2}, {"role": "lines", "index": 0}, {"role": "planars", "index": -1}, {"index": 3}]
    assert _indexes_by_role(selection) == {"lines": [2, 0], "": [3]}
    assert _indexes_by_role(None) == {}


def test_visible_indexes_combines_isolation_and_hidden_items():
    from viewer_widget import _visible_indexes

    assert _visible_indexes("load_areas", 3, None, set()) is None
    assert _visible_indexes("load_areas", 3, None, {("load_areas", 1)}) == [0, 2]
    assert _visible_indexes("load_areas", 3, {"load_areas": [2, 7, 0]}, {("load_areas", 0)}) == [2]
    assert _visible_indexes("load_areas", 3, {"lines": [0]}, set()) == []


def test_isolated_load_indexes_keep_existing_loads_of_visible_cases():
    from viewer_widget import _isolated_load_indexes

    loads = [{"load_case_eid": 1}, {"load_case_eid": 2}]
    assert _isolated_load_indexes([1, 0, 5, -1], loads, None) == [1, 0]
    assert _isolated_load_indexes([1, 0], loads, {2}) == [1]
