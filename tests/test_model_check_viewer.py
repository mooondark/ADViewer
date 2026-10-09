# -*- coding: utf-8 -*-
"""Controle du modele 3D : branchement de l'overlay d'anomalies dans le viewer."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import model_check as mc
import model_check_view as mcv
from test_clip_box import _viewer_stub


def _anomaly(items, shape=None, kind=mc.K_DUPLICATE):
    shape = shape or {"type": "sphere", "center": (0.0, 0.0, 0.0), "radius": 0.1}
    return mc.Anomaly(kind, mc.SEVERITY_BY_KIND[kind], tuple(items), tuple(range(len(items))), (0.0, 0.0, 0.0),
                      1.0, 1.0, "mm", shape)


def _viewer(anomalies):
    w = _viewer_stub()
    w.render_window = types.SimpleNamespace(Render=lambda: None)
    w._anomaly_overlay = mcv.AnomalyOverlay(w.renderer)
    w._active_anomaly = None
    w._anomaly_emit = False
    w._selected_item = None
    w.emitted = []
    w.selectionChanged = types.SimpleNamespace(emit=lambda items: w.emitted.append((list(items), w._anomaly_emit)))
    w._refresh_selection_overlay = lambda: None
    w._update_view_overlay = lambda: None
    w.set_anomalies(anomalies, mc.Thresholds())
    return w


def test_select_anomaly_fills_ordinary_selection_and_flags_the_emission():
    w = _viewer([_anomaly([("lines", 3), ("lines", 4)])])
    w.select_anomaly(0)
    assert w._selected_items == [{"role": "lines", "index": 3}, {"role": "lines", "index": 4}]
    assert w._selected_item == {"role": "lines", "index": 3}
    assert w.emitted == [([{"role": "lines", "index": 3}, {"role": "lines", "index": 4}], True)]
    assert w._anomaly_emit is False and w._active_anomaly == 0


def test_consume_returns_index_only_for_the_anomaly_emission():
    w = _viewer([_anomaly([("lines", 3)])])
    w.select_anomaly(0)
    w._anomaly_emit = True            # simule l'appel pendant l'emission
    assert w.consume_anomaly_selection() == 0
    w._anomaly_emit = False           # une selection ulterieure d'un autre chemin
    assert w.consume_anomaly_selection() is None
    assert w._active_anomaly is None


def test_active_symbol_is_reinforced_then_restored_when_forgotten():
    w = _viewer([_anomaly([("lines", 0)])])
    actor = w.renderer.GetActors().GetItemAsObject(0)
    w.select_anomaly(0)
    assert actor.GetProperty().GetOpacity() == mcv.ACTIVE_OPACITY
    w.consume_anomaly_selection()
    assert abs(actor.GetProperty().GetOpacity() - 0.5) < 1e-9


def test_anomaly_without_items_clears_the_selection_but_stays_active():
    w = _viewer([_anomaly([], {"type": "frame", "bounds": (0, 1, 0, 1, 0, 1)}, mc.K_NO_SUPPORT)])
    w.select_anomaly(0)
    assert w._selected_items == [] and w._selected_item is None and w._active_anomaly == 0


def test_select_item_with_anomaly_role_delegates_to_select_anomaly():
    w = _viewer([_anomaly([("lines", 1)])])
    assert w._select_item("anomaly", 0) is True
    assert w._active_anomaly == 0 and w._selected_items == [{"role": "lines", "index": 1}]


def test_visibility_and_clear():
    w = _viewer([_anomaly([("lines", 1)])])
    assert w.anomalies_visible()
    w.set_anomalies_visible(False)
    assert not w.anomalies_visible()
    w.clear_anomalies()
    assert w._anomaly_overlay.count() == 0 and w._active_anomaly is None


def test_visible_bounds_ignore_anomaly_symbols():
    w = _viewer([_anomaly([("lines", 1)], {"type": "sphere", "center": (100.0, 0, 0), "radius": 5.0})])
    assert w._get_visible_bounds() is None
    assert w._anomaly_overlay.bounds(0) is not None


def test_pick_candidates_append_anomalies_after_elements():
    w = _viewer([_anomaly([("lines", 1)])])
    w._display_mode = "full"
    w._anomaly_overlay.pick = lambda x, y, max_layers=6: [0]
    w._get_pick_hit = lambda x, y, exclude_keys=None: {"role": "lines", "index": 7, "depth": 1.0}
    out = w._pick_selection_candidates(10, 10)
    assert [(c["role"], c["index"]) for c in out] == [("lines", 7), ("anomaly", 0)]
    w._get_pick_hit = lambda x, y, exclude_keys=None: None
    assert [(c["role"], c["index"]) for c in w._pick_selection_candidates(10, 10)] == [("anomaly", 0)]


def test_focus_bounds_keeps_view_direction_and_frames_the_box():
    w = _viewer([])
    cam = w.renderer.GetActiveCamera()
    cam.SetPosition(0, -10, 0)
    cam.SetFocalPoint(0, 0, 0)
    before = cam.GetDirectionOfProjection()
    w.focus_bounds((4.0, 6.0, -1.0, 1.0, -1.0, 1.0))
    after = cam.GetDirectionOfProjection()
    assert all(abs(a - b) < 1e-9 for a, b in zip(before, after))
    fx, fy, fz = cam.GetFocalPoint()
    assert abs(fx - 5.0) < 1e-6
