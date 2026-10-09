# -*- coding: utf-8 -*-
"""Controle du modele 3D : moteur de detection pur (model_check.py)."""

import copy
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_check as mc


def test_aligned_line_eids_skip_elements_without_geometry():
    import ad_model_data

    elements = [
        {"geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 1, "y": 0, "z": 0}},
        {"geomPtStart": None, "geomPtEnd": {"x": 1, "y": 0, "z": 0}},
        {"geomPtStart": {"x": 0, "y": 1, "z": 0}, "geomPtEnd": {"x": 1, "y": 1, "z": 0}},
    ]
    assert ad_model_data._aligned_line_eids([10, 11, 12], elements) == [10, 12]
    assert ad_model_data._aligned_line_eids([10, None, 12], [elements[0], elements[0], elements[2]]) == [10, None, 12]


_DEFAULT_SUPPORT_PROPS = {"kind": "rigid", "restraints": {k: True for k in ("TX", "TY", "TZ", "RX", "RY", "RZ")}}


def _model(lines=(), planars=(), punctual=None, props=None, linear_supports=(), planar_supports=(), eids=None):
    """Modele minimal. Sans `punctual`, un appui eloigne est ajoute pour que les
    tests des autres regles ne recoivent pas l'erreur "aucun appui" ; passer
    punctual=[] pour un modele reellement sans appui ponctuel."""
    if punctual is None:
        punctual, props = [(1000.0, 1000.0, 1000.0)], [_DEFAULT_SUPPORT_PROPS]
    lines = [[tuple(a), tuple(b)] for a, b in lines]
    return {
        "lines": lines,
        "line_eids": list(eids) if eids is not None else list(range(1, len(lines) + 1)),
        "planars": [{"outer": [tuple(p) for p in poly], "openings": []} for poly in planars],
        "planar_eids": [100 + i for i in range(len(planars))],
        "punctual_supports": [tuple(p) for p in punctual],
        "punctual_support_eids": [200 + i for i in range(len(punctual))],
        "punctual_support_properties": list(props or []),
        "linear_supports": list(linear_supports),
        "planar_supports": list(planar_supports),
    }


def _kinds(anomalies):
    return [a.kind for a in anomalies]


def test_empty_model_gives_no_anomaly():
    assert mc.detect({}) == []
    assert mc.detect(None) == []
    assert mc.detect({"lines": [], "planars": []}) == []


def test_missing_keys_do_not_raise():
    mc.detect({"lines": [[(0, 0, 0), (1, 0, 0)]]})
    mc.detect({"punctual_supports": [(0, 0, 0)]})
    mc.detect({"planars": [{"outer": [(0, 0, 0), (1, 0, 0), (1, 1, 0)]}]})


def test_thresholds_defaults_and_clamp():
    th = mc.Thresholds()
    assert th.connection_tol_mm == 5.0 and th.symbol_transparency_pct == 50.0
    assert mc.Thresholds(symbol_transparency_pct=10.0).clamped().symbol_transparency_pct == 40.0
    assert mc.Thresholds(symbol_transparency_pct=99.0).clamped().symbol_transparency_pct == 60.0
    assert mc.Thresholds(connection_tol_mm=float("nan")).clamped().connection_tol_mm == 5.0
    assert mc.Thresholds(connection_tol_mm=-3.0).clamped().connection_tol_mm == 0.0


def test_thresholds_section_roundtrip_only_non_defaults():
    th = mc.Thresholds(connection_tol_mm=7.5, check_supports=False)
    section = th.to_section()
    assert section == {"connection_tol_mm": "7.5", "check_supports": "false"}
    assert mc.Thresholds.from_section(section) == th
    assert mc.Thresholds().to_section() == {}


def test_thresholds_from_corrupted_section_falls_back_to_defaults():
    th = mc.Thresholds.from_section({
        "connection_tol_mm": "abc",
        "duplicate_angle_deg": "500",
        "check_supports": "peut-etre",
        "symbol_transparency_pct": "5",
    })
    assert th.connection_tol_mm == 5.0
    assert th.duplicate_angle_deg == 90.0
    assert th.check_supports is True    # booleen invalide = valeur par defaut
    assert th.symbol_transparency_pct == 40.0
    assert mc.Thresholds.from_section(None) == mc.Thresholds()


def test_detect_is_read_only_and_deterministic():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0)), ((0, 0, 0), (1, 0.0005, 0))])
    before = copy.deepcopy(model)
    first = mc.detect(model)
    second = mc.detect(model)
    assert model == before
    assert first == second


def test_cancel_raises_and_returns_nothing():
    model = _model(lines=[((0, 0, 0), (1, 0, 0))])
    try:
        mc.detect(model, cancelled=lambda: True)
    except mc.DetectionCancelled:
        return
    raise AssertionError("DetectionCancelled attendue")


def test_progress_reports_stages_in_order():
    seen = []
    mc.detect(_model(lines=[((0, 0, 0), (1, 0, 0))]), progress=lambda d, t: seen.append((d, t)))
    assert seen[0][0] == 0 and seen[-1][0] == seen[-1][1]
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def _only(anomalies, kind):
    return [a for a in anomalies if a.kind == kind]


def test_duplicate_reversed_elements():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (0, 0, 0))])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_DUPLICATE]
    a = out[0]
    assert a.severity == mc.ERROR and a.items == (("lines", 0), ("lines", 1)) and a.eids == (1, 2)
    assert a.measured == 0.0 and a.threshold == 1.0 and a.unit == "mm"
    assert a.shape["type"] == "prism"


def test_duplicate_tolerance_boundary_is_inclusive():
    on = _model(lines=[((0, 0, 0), (1, 0, 0)), ((0, 0.001, 0), (1, 0.001, 0))])
    assert mc.K_DUPLICATE in _kinds(mc.detect(on))
    off = _model(lines=[((0, 0, 0), (1, 0, 0)), ((0, 0.0011, 0), (1, 0.0011, 0))])
    assert mc.K_DUPLICATE not in _kinds(mc.detect(off))


def test_duplicate_is_not_also_reported_as_overlap_or_collinear():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((0, 0, 0), (1, 0, 0))])
    assert _kinds(mc.detect(model)) == [mc.K_DUPLICATE]


def test_overlap_partial_with_cylinder_over_common_zone():
    model = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1, 0.003, 0), (3, 0.003, 0))])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_OVERLAP]
    a = out[0]
    assert abs(a.measured - 3.0) < 1e-6 and a.threshold == 5.0
    s = a.shape
    assert s["type"] == "cylinder"
    xs = sorted([s["p0"][0], s["p1"][0]])
    assert abs(xs[0] - 1.0) < 1e-9 and abs(xs[1] - 2.0) < 1e-9


def test_end_to_end_elements_are_not_an_overlap():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (2, 0, 0))])
    assert mc.K_OVERLAP not in _kinds(mc.detect(model))


def test_overlap_shorter_than_minimum_length_is_ignored():
    model = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1.995, 0, 0), (4, 0, 0))])
    assert mc.K_OVERLAP not in _kinds(mc.detect(model))


def test_overlap_too_far_or_too_inclined_is_ignored():
    far = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1, 0.02, 0), (3, 0.02, 0))])
    assert mc.K_OVERLAP not in _kinds(mc.detect(far))
    inclined = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1, 0, 0), (3, 0.2, 0))])   # ~5.7 deg
    assert mc.K_OVERLAP not in _kinds(mc.detect(inclined))


def test_overlap_pair_is_not_reported_as_missing_connection():
    model = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1.9, 0.001, 0), (4, 0.001, 0))])
    kinds = _kinds(mc.detect(model))
    assert mc.K_OVERLAP in kinds and mc.K_MISSING not in kinds


def test_short_element_warning_and_null_length_error():
    out = mc.detect(_model(lines=[((0, 0, 0), (0.03, 0, 0)), ((5, 0, 0), (5.0005, 0, 0)), ((9, 0, 0), (9.06, 0, 0))]))
    kinds = {a.kind: a for a in out}
    assert mc.K_SHORT in kinds and kinds[mc.K_SHORT].severity == mc.WARNING
    assert abs(kinds[mc.K_SHORT].measured - 30.0) < 1e-6 and kinds[mc.K_SHORT].threshold == 50.0
    assert mc.K_NULL in kinds and kinds[mc.K_NULL].severity == mc.ERROR
    assert len(out) == 2   # le troisieme (60 mm) est assez long


def test_short_element_has_no_missing_connection_between_its_own_ends():
    assert _kinds(mc.detect(_model(lines=[((0, 0, 0), (0.003, 0, 0))]))) == [mc.K_SHORT]


def test_zero_length_element_and_none_eids_do_not_crash_and_sort_stably():
    model = _model(lines=[((1, 1, 1), (1, 1, 1)), ((0, 0, 0), (0.02, 0, 0))], eids=[None, None])
    out = mc.detect(model)
    assert [a.kind for a in out] == [mc.K_NULL, mc.K_SHORT]
    assert out[0].eids == (None,)
    assert mc.detect(model) == out


def test_missing_connection_end_to_end():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1.002, 0, 0), (2, 0, 0))])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_MISSING]
    a = out[0]
    assert a.severity == mc.ERROR and abs(a.measured - 2.0) < 1e-6 and a.threshold == 5.0
    assert a.items == (("lines", 0), ("lines", 1))
    assert abs(a.point[0] - 1.001) < 1e-9
    assert a.shape["type"] == "sphere" and abs(a.shape["radius"] - 0.005) < 1e-12


def test_shared_node_is_not_a_missing_connection():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0))])
    assert mc.detect(model) == []


def test_missing_connection_end_to_body_t_junction():
    model = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1, 0.003, 0), (1, 1, 0))])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_MISSING]
    assert abs(out[0].measured - 3.0) < 1e-6
    assert abs(out[0].point[1] - 0.0015) < 1e-9


def test_end_exactly_on_body_is_not_reported():
    model = _model(lines=[((0, 0, 0), (2, 0, 0)), ((1, 0, 0), (1, 1, 0))])
    assert mc.detect(model) == []


def test_missing_connection_beyond_tolerance_is_ignored():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1.010, 0, 0), (2, 0, 0))])
    assert mc.K_MISSING not in _kinds(mc.detect(model))


def test_missing_connection_between_nodes_is_reported_once():
    # deux poutres arrivent au noeud A, deux autres au noeud B, a 2 mm : un seul defaut
    model = _model(lines=[
        ((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0)),
        ((1.002, 0, 0), (2, 0, 0)), ((1.002, 0, 0), (1.002, -1, 0)),
    ])
    out = _only(mc.detect(model), mc.K_MISSING)
    assert len(out) == 1 and len(out[0].items) == 4


def test_short_element_neighbours_connections_are_still_checked():
    model = _model(lines=[((0, 0, 0), (0.03, 0, 0)), ((0.032, 0, 0), (1, 0, 0))])
    kinds = _kinds(mc.detect(model))
    assert mc.K_MISSING in kinds and mc.K_SHORT in kinds


def test_collinear_elements_sharing_a_node_are_information():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (2, 0.0001, 0))])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_COLLINEAR]
    a = out[0]
    assert a.severity == mc.INFO and a.unit == "deg" and a.threshold == 1.0 and a.measured < 0.01
    assert a.point == (1.0, 0.0, 0.0)
    assert a.shape["type"] == "cylinder" and a.shape["thin"] is True


def test_not_collinear_when_deviation_exceeds_tolerance_or_no_shared_node():
    inclined = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (2, 0.05, 0))])
    assert mc.detect(inclined) == []
    apart = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1.5, 0, 0), (2.5, 0, 0))])
    assert mc.K_COLLINEAR not in _kinds(mc.detect(apart))


def test_collinear_ignores_short_elements_and_folded_back_elements():
    short = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1.02, 0, 0))])
    assert mc.K_COLLINEAR not in _kinds(mc.detect(short))
    folded = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (0.5, 0, 0))])   # revient sur le premier
    assert mc.K_COLLINEAR not in _kinds(mc.detect(folded))


def test_many_elements_on_one_node_do_not_blow_up():
    lines = []
    for k in range(40):
        ang = 2 * math.pi * k / 40
        lines.append(((0, 0, 0), (math.cos(ang), math.sin(ang), 0)))
    start = time.time()
    out = mc.detect(_model(lines=lines))
    assert time.time() - start < 5.0
    assert mc.K_MISSING not in _kinds(out)


def _square(side=1.0, z=0.0):
    return [(0, 0, z), (side, 0, z), (side, side, z), (0, side, z)]


def test_healthy_surface_gives_nothing():
    assert mc.detect(_model(planars=[_square()])) == []


def test_surface_with_tiny_area_is_an_error():
    out = mc.detect(_model(planars=[_square(0.05)]))
    assert _kinds(out) == [mc.K_SURF_AREA]
    a = out[0]
    assert a.severity == mc.ERROR and a.unit == "m2" and abs(a.measured - 0.0025) < 1e-9 and a.threshold == 0.01
    assert a.items == (("planars", 0),) and a.eids == (100,)
    assert a.shape["type"] == "surface" and len(a.shape["outline"]) == 4


def test_surface_with_coincident_vertices_is_an_error():
    poly = [(0, 0, 0), (1, 0, 0), (1.0005, 0, 0), (1, 1, 0), (0, 1, 0)]
    out = mc.detect(_model(planars=[poly]))
    assert _kinds(out) == [mc.K_SURF_VERTICES]
    assert abs(out[0].measured - 0.5) < 1e-6 and out[0].threshold == 1.0


def test_closed_ring_with_repeated_first_vertex_is_not_a_coincidence():
    ring = _square() + [(0, 0, 0)]
    assert mc.detect(_model(planars=[ring])) == []


def test_self_intersecting_surface_is_detected_on_a_tilted_plane():
    bowtie = [(0, 0, 0), (1, 1, 1), (1, 0, 0), (0, 1, 1)]
    kinds = _kinds(mc.detect(_model(planars=[bowtie])))
    assert mc.K_SURF_CROSS in kinds


def test_simple_concave_surface_is_not_self_intersecting():
    l_shape = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0), (1, 2, 0), (0, 2, 0)]
    assert mc.detect(_model(planars=[l_shape])) == []


def test_short_edges_are_warnings_one_per_edge():
    out = mc.detect(_model(planars=[[(0, 0, 0), (5, 0, 0), (5, 0.005, 0), (0, 0.005, 0)]]))
    assert _kinds(out) == [mc.K_SURF_EDGE, mc.K_SURF_EDGE]
    assert all(a.severity == mc.WARNING and abs(a.measured - 5.0) < 1e-6 and a.threshold == 10.0 for a in out)


def test_surface_with_fewer_than_three_vertices_is_ignored():
    assert mc.detect(_model(planars=[[(0, 0, 0), (1, 0, 0)]])) == []


def _rigid(**blocked):
    keys = ("TX", "TY", "TZ", "RX", "RY", "RZ")
    return {"kind": "rigid", "restraints": {k: bool(blocked.get(k, False)) for k in keys}}


_BEAM = [((0, 0, 0), (1, 0, 0))]


def test_no_support_is_an_error_with_a_frame_over_the_model():
    out = mc.detect(_model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 2, 3))], punctual=[]))
    assert _kinds(out) == [mc.K_NO_SUPPORT]
    a = out[0]
    assert a.severity == mc.ERROR and a.items == () and a.shape["type"] == "frame"
    assert a.shape["bounds"] == (0.0, 1.0, 0.0, 2.0, 0.0, 3.0)
    assert a.point == (0.5, 1.0, 1.5)


def test_any_support_family_counts_as_a_support():
    assert mc.detect(_model(lines=_BEAM, punctual=[(0, 0, 0)], props=[_rigid(TX=True)])) == []
    assert mc.detect(_model(lines=_BEAM, linear_supports=[[(0, 0, 0), (1, 0, 0)]])) == []
    assert mc.detect(_model(lines=_BEAM, planar_supports=[{"outer": _square()}])) == []


def test_empty_model_has_no_no_support_anomaly():
    assert mc.detect(_model(punctual=[])) == []


def test_support_check_can_be_disabled():
    th = mc.Thresholds(check_supports=False)
    assert mc.detect(_model(lines=_BEAM, punctual=[]), th) == []
    two = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[_rigid(TX=True)] * 2)
    assert mc.detect(two, th) == []


def test_overlapping_supports_same_blocking_same_node():
    model = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[_rigid(TX=True), _rigid(TX=True)])
    out = mc.detect(model)
    assert _kinds(out) == [mc.K_SUPPORT_OVERLAP]
    a = out[0]
    assert a.severity == mc.WARNING and a.items == (("support_punctual", 0), ("support_punctual", 1))
    assert a.eids == (200, 201) and a.shape["type"] == "cube" and a.point == (0.0, 0.0, 0.0)


def test_supports_with_different_blocking_are_not_overlapping():
    model = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[_rigid(TX=True), _rigid(TZ=True)])
    assert mc.detect(model) == []


def test_supports_within_duplicate_tolerance_overlap_but_not_beyond():
    near = _model(lines=_BEAM, punctual=[(0, 0, 0), (0.0005, 0, 0)], props=[_rigid(TX=True)] * 2)
    assert _kinds(mc.detect(near)) == [mc.K_SUPPORT_OVERLAP]
    far = _model(lines=_BEAM, punctual=[(0, 0, 0), (0.005, 0, 0)], props=[_rigid(TX=True)] * 2)
    assert mc.detect(far) == []


def test_overlapping_supports_report_can_be_disabled():
    model = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[_rigid(TX=True)] * 2)
    assert mc.detect(model, mc.Thresholds(report_overlapping_supports=False)) == []


def test_elastic_supports_compare_their_stiffness():
    keys = ("KTX", "KTY", "KTZ", "KRX", "KRY", "KRZ")
    p1 = {"kind": "elastic", "stiffness": {k: 100.0 for k in keys}}
    p2 = {"kind": "elastic", "stiffness": {k: 200.0 for k in keys}}
    same = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[p1, p1])
    assert _kinds(mc.detect(same)) == [mc.K_SUPPORT_OVERLAP]
    diff = _model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[p1, p2])
    assert mc.detect(diff) == []


def _grid_model(n=71, defects=True):
    lines = []
    for ix in range(n):
        for iy in range(n):
            if ix + 1 < n:
                lines.append(((ix, iy, 0.0), (ix + 1, iy, 0.0)))
            if iy + 1 < n:
                lines.append(((ix, iy, 0.0), (ix, iy + 1, 0.0)))
    if defects:
        lines[10] = ((lines[10][0][0], lines[10][0][1], 0.0), (lines[10][1][0] + 0.002, lines[10][1][1], 0.0))
        lines.append(lines[500])   # doublon exact
    return _model(lines=lines, punctual=[(0, 0, 0)], props=[_rigid(TX=True)])


def test_ten_thousand_elements_run_in_reasonable_time():
    model = _grid_model()
    assert len(model["lines"]) >= 9900
    start = time.time()
    out = mc.detect(model)
    elapsed = time.time() - start
    print(f"detect(10k elements) = {elapsed:.2f} s, {len(out)} anomalies")
    assert elapsed < 30.0
    kinds = _kinds(out)
    assert mc.K_DUPLICATE in kinds and mc.K_MISSING in kinds


# ---- correctifs de la relecture finale -------------------------------------

def test_short_element_between_neighbours_gives_no_missing_connection():
    model = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1.003, 0, 0)), ((1.003, 0, 0), (2, 0, 0))])
    kinds = _kinds(mc.detect(model))
    assert mc.K_SHORT in kinds and mc.K_MISSING not in kinds
    null = _model(lines=[((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1.0005, 0, 0)), ((1.0005, 0, 0), (2, 0, 0))])
    kinds = _kinds(mc.detect(null))
    assert mc.K_NULL in kinds and mc.K_MISSING not in kinds


def test_duplicate_with_neighbours_gives_no_missing_connection():
    model = _model(lines=[
        ((0, 0, 0), (5, 0, 0)), ((0, 0.0005, 0), (5, 0.0005, 0)),
        ((0, 0, 0), (0, 0, -3)), ((5, 0, 0), (5, 0, -3)),
    ])
    kinds = _kinds(mc.detect(model))
    assert kinds.count(mc.K_DUPLICATE) == 1 and mc.K_MISSING not in kinds


def test_overlap_with_neighbours_gives_no_missing_connection():
    model = _model(lines=[
        ((0, 0, 0), (5, 0, 0)), ((0, 0.003, 0), (5, 0.003, 0)),
        ((0, 0, 0), (0, 0, -3)),
    ])
    kinds = _kinds(mc.detect(model))
    assert mc.K_OVERLAP in kinds and mc.K_MISSING not in kinds


def test_long_3d_diagonal_does_not_explode_the_spatial_index():
    lines = [((i * 0.25, 0.0, 0.0), (i * 0.25 + 0.25, 0.0, 0.0)) for i in range(200)]
    lines.append(((0.0, 0.0, 0.0), (60.0, 60.0, 60.0)))
    start = time.time()
    mc.detect(_model(lines=lines))
    assert time.time() - start < 3.0


def test_thresholds_from_configparser_with_percent_sign_does_not_raise():
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read_string("[model_check]\nconnection_tol_mm = 5%\ncheck_supports = true\n")
    th = mc.Thresholds.from_section(cfg[mc.SECTION])
    assert th.connection_tol_mm == 5.0 and th.check_supports is True


# ---- evolutions demandees apres la relecture ---------------------------------

def test_advanced_supports_on_the_same_node_overlap():
    adv = {"kind": "advanced"}
    out = mc.detect(_model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[adv, adv]))
    assert _kinds(out) == [mc.K_SUPPORT_OVERLAP]
    mixed = mc.detect(_model(lines=_BEAM, punctual=[(0, 0, 0), (0, 0, 0)], props=[adv, _rigid(TX=True)]))
    assert mixed == []


def test_invalid_boolean_in_config_falls_back_to_default():
    th = mc.Thresholds.from_section({"check_supports": "peut-etre", "include_info": "0", "report_overlapping_supports": "oui"})
    assert th.check_supports is True            # defaut (invalide)
    assert th.include_info is False             # "0" reconnu
    assert th.report_overlapping_supports is True


def test_nodes_closer_than_1e9_are_the_same_node_across_a_rounding_boundary():
    model = _model(lines=[((0, 0, 0), (1.0000000005, 0, 0)), ((1.0000000004999, 0, 0), (1.0000000004999, 1, 0))])
    assert mc.detect(model) == []


def test_three_close_nodes_are_one_missing_connection():
    model = _model(lines=[
        ((0, 0, 0), (1, 0, 0)), ((1.002, 0, 0), (1.002, 1, 0)), ((1.004, 0, 0), (2, 0, 0)),
    ])
    out = _only(mc.detect(model), mc.K_MISSING)
    assert len(out) == 1 and len(out[0].items) == 3
    assert abs(out[0].measured - 4.0) < 1e-6
    assert abs(out[0].point[0] - 1.002) < 1e-9
