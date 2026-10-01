# -*- coding: utf-8 -*-
"""Boite de coupe : geometrie pure, helpers VTK, controleur."""

import math
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import clip_box

BOX = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0]


def test_expand_bounds_adds_margin_percentage():
    out = clip_box.expand_bounds([0, 10, 0, 20, 0, 30], 10.0)
    assert out == [-1.0, 11.0, -2.0, 22.0, -3.0, 33.0]


def test_expand_bounds_flat_dimension_gets_minimum_thickness():
    out = clip_box.expand_bounds([0, 10, 0, 10, 0, 0], 2.0)
    assert abs((out[5] - out[4]) - 0.1) < 1e-9
    assert abs((out[4] + out[5]) / 2.0) < 1e-9


def test_expand_bounds_single_point_is_still_a_box():
    out = clip_box.expand_bounds([5, 5, 5, 5, 5, 5], 2.0)
    for i in range(3):
        assert out[2 * i + 1] - out[2 * i] >= 0.1 - 1e-9


def test_point_in_box_edges_and_outside():
    assert clip_box.point_in_box((5, 5, 5), BOX)
    assert clip_box.point_in_box((10, 0, 10), BOX)
    assert not clip_box.point_in_box((10.1, 5, 5), BOX)
    assert clip_box.point_in_box((10.0000001, 5, 5), BOX, tol=1e-3)


def test_clip_segment_fully_inside_is_unchanged():
    seg = clip_box.clip_segment((1, 1, 1), (9, 9, 9), BOX)
    assert seg == ((1.0, 1.0, 1.0), (9.0, 9.0, 9.0))


def test_clip_segment_crossing_is_trimmed():
    a, b = clip_box.clip_segment((-5, 5, 5), (15, 5, 5), BOX)
    assert abs(a[0]) < 1e-9 and abs(b[0] - 10.0) < 1e-9


def test_clip_segment_outside_is_none():
    assert clip_box.clip_segment((-5, 5, 5), (-1, 5, 5), BOX) is None
    assert clip_box.clip_segment((-5, 20, 5), (15, 20, 5), BOX) is None


def test_clip_segment_degenerate_point_inside_and_outside():
    assert clip_box.clip_segment((5, 5, 5), (5, 5, 5), BOX) is not None
    assert clip_box.clip_segment((50, 5, 5), (50, 5, 5), BOX) is None


def test_clip_polygon_square_cut_in_half():
    square = [(-5, 0, 5), (5, 0, 5), (5, 10, 5), (-5, 10, 5)]
    out = clip_box.clip_polygon(square, BOX)
    xs = [p[0] for p in out]
    assert min(xs) >= -1e-9 and abs(max(xs) - 5.0) < 1e-9


def test_clip_polygon_outside_is_empty_and_inside_is_kept():
    far = [(20, 0, 5), (30, 0, 5), (30, 10, 5)]
    assert clip_box.clip_polygon(far, BOX) == []
    inside = [(1, 1, 1), (2, 1, 1), (2, 2, 1)]
    assert len(clip_box.clip_polygon(inside, BOX)) == 3


def test_clip_cell_points_dispatch_by_size():
    assert clip_box.clip_cell_points([(5, 5, 5)], BOX) == [(5, 5, 5)]
    assert clip_box.clip_cell_points([(50, 5, 5)], BOX) == []
    assert len(clip_box.clip_cell_points([(-5, 5, 5), (5, 5, 5)], BOX)) == 2
    assert clip_box.clip_cell_points([], BOX) == []


def test_move_face_moves_only_that_face():
    out = clip_box.move_face(BOX, 1, 12.0, 0.1)
    assert out == [0.0, 12.0, 0.0, 10.0, 0.0, 10.0]


def test_move_face_cannot_cross_opposite_face():
    out = clip_box.move_face(BOX, 1, -50.0, 0.1)
    assert abs(out[1] - 0.1) < 1e-9 and out[0] == 0.0
    out = clip_box.move_face(BOX, 4, 99.0, 0.1)
    assert abs(out[4] - 9.9) < 1e-9 and out[5] == 10.0


def test_move_box_translates_all_faces():
    assert clip_box.move_box(BOX, (1, 2, 3)) == [1.0, 11.0, 2.0, 12.0, 3.0, 13.0]


def test_handle_positions_face_centers_and_center():
    pos = clip_box.handle_positions(BOX)
    assert pos["center"] == (5.0, 5.0, 5.0)
    assert pos[0] == (0.0, 5.0, 5.0) and pos[1] == (10.0, 5.0, 5.0)
    assert pos[4] == (5.0, 5.0, 0.0) and pos[5] == (5.0, 5.0, 10.0)


def test_face_axis_dir():
    assert clip_box.face_axis_dir(0) == (1.0, 0.0, 0.0)
    assert clip_box.face_axis_dir(3) == (0.0, 1.0, 0.0)
    assert clip_box.face_axis_dir(5) == (0.0, 0.0, 1.0)


def test_pick_handle_nearest_within_radius():
    pts = {0: (100.0, 100.0), 1: (110.0, 100.0), "center": (300.0, 300.0)}
    assert clip_box.pick_handle(pts, (101.0, 100.0), 14.0) == 0
    assert clip_box.pick_handle(pts, (109.0, 100.0), 14.0) == 1
    assert clip_box.pick_handle(pts, (200.0, 200.0), 14.0) is None
    assert clip_box.pick_handle({0: None}, (0.0, 0.0), 14.0) is None


def test_world_per_pixel_parallel_and_perspective():
    assert abs(clip_box.world_per_pixel(0.0, 30.0, True, 5.0, 100.0) - 0.1) < 1e-9
    persp = clip_box.world_per_pixel(10.0, 90.0, False, 0.0, 100.0)
    assert abs(persp - 0.2) < 1e-9


def test_line_param_closest_to_ray_recovers_axis_position():
    t = clip_box.line_param_closest_to_ray((7, 3, 100), (0, 0, -1), (0, 3, 0), (1, 0, 0))
    assert abs(t - 7.0) < 1e-9


def test_line_param_closest_to_ray_parallel_returns_none():
    assert clip_box.line_param_closest_to_ray((0, 0, 0), (1, 0, 0), (0, 5, 0), (1, 0, 0)) is None


def test_ray_plane_intersection_hit_and_parallel():
    hit = clip_box.ray_plane_intersection((0, 0, 10), (0, 0, -1), (0, 0, 0), (0, 0, 1))
    assert hit == (0.0, 0.0, 0.0)
    assert clip_box.ray_plane_intersection((0, 0, 10), (1, 0, 0), (0, 0, 0), (0, 0, 1)) is None


def _cube_pd(size=10.0):
    src = vtk.vtkCubeSource()
    src.SetBounds(0, size, 0, size, 0, size)
    tri = vtk.vtkTriangleFilter()
    tri.SetInputConnection(src.GetOutputPort())
    tri.Update()
    return tri.GetOutput()


def _single_line_pd(p0, p1):
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    pts.InsertNextPoint(*p0)
    pts.InsertNextPoint(*p1)
    cells = vtk.vtkCellArray()
    line = vtk.vtkLine()
    line.GetPointIds().SetId(0, 0)
    line.GetPointIds().SetId(1, 1)
    cells.InsertNextCell(line)
    pd.SetPoints(pts)
    pd.SetLines(cells)
    return pd


def test_make_planes_keep_inside_positive():
    planes = clip_box.make_planes(BOX)
    assert len(planes) == 6
    assert all(p.EvaluateFunction((5, 5, 5)) > 0 for p in planes)
    assert planes[0].EvaluateFunction((-1, 5, 5)) < 0
    assert planes[1].EvaluateFunction((11, 5, 5)) < 0
    assert planes[5].EvaluateFunction((5, 5, 11)) < 0


def test_update_planes_follows_box():
    planes = clip_box.make_planes(BOX)
    clip_box.update_planes(planes, [0, 20, 0, 10, 0, 10])
    assert planes[1].EvaluateFunction((15, 5, 5)) > 0


def test_compute_cut_edges_cube_traces_stay_inside_box_extent():
    lines_pd, points_pd = clip_box.compute_cut_edges(_cube_pd(), [2, 8, 2, 8, -1, 11])
    assert lines_pd is not None and lines_pd.GetNumberOfCells() > 0
    assert points_pd is None
    b = lines_pd.GetBounds()
    assert b[0] >= 2 - 5e-3 and b[1] <= 8 + 5e-3
    assert b[2] >= 2 - 5e-3 and b[3] <= 8 + 5e-3
    assert b[4] >= -1e-3 and b[5] <= 10 + 1e-3


def test_compute_cut_edges_line_crossing_two_faces_gives_two_points():
    lines_pd, points_pd = clip_box.compute_cut_edges(_single_line_pd((0, 5, 5), (10, 5, 5)), [2, 8, 0, 10, 0, 10])
    assert lines_pd is None
    xs = {round(points_pd.GetPoint(i)[0], 6) for i in range(points_pd.GetNumberOfPoints())}
    assert xs == {2.0, 8.0}


def test_compute_cut_edges_nothing_cut_returns_none_none():
    assert clip_box.compute_cut_edges(_cube_pd(), [100, 110, 100, 110, 100, 110]) == (None, None)
    assert clip_box.compute_cut_edges(None, BOX) == (None, None)


class _Host:
    def __init__(self):
        self.renderer = vtk.vtkRenderer()
        self.render_window = None
        self._actors = []
        self._window_select_mode = False
        self._zoom_window_mode = False
        self._flight = types.SimpleNamespace(active=False)
        self.edge_sources = []

    def _clippable_actors(self):
        return list(self._actors)

    def _clip_edge_sources(self):
        return self.edge_sources


def _actor_for(pd):
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def _controller():
    host = _Host()
    return host, clip_box.ClipBoxController(host)


def test_activate_applies_planes_and_deactivate_removes_them():
    host, ctrl = _controller()
    actor = _actor_for(_cube_pd())
    host._actors.append(actor)
    assert ctrl.activate([0, 10, 0, 10, 0, 10]) is True
    assert ctrl.active
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 6
    assert ctrl.deactivate() is True
    assert not ctrl.active and ctrl.box is None
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 0


def test_activate_without_bounds_does_nothing():
    host, ctrl = _controller()
    assert ctrl.activate(None) is False
    assert not ctrl.active
    assert ctrl.deactivate() is False


def test_exempt_actor_is_never_clipped():
    host, ctrl = _controller()
    actor = _actor_for(_cube_pd())
    actor._clip_exempt = True
    host._actors.append(actor)
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 0


def test_actor_added_after_activation_gets_planes():
    host, ctrl = _controller()
    ctrl.activate([0, 10, 0, 10, 0, 10])
    late = _actor_for(_cube_pd())
    host._actors.append(late)
    ctrl.apply_to_actor(late)
    assert late.GetMapper().GetNumberOfClippingPlanes() == 6


def test_billboard_labels_outside_box_are_hidden_then_restored():
    host, ctrl = _controller()
    inside = clip_box.vtkBillboardTextActor3D()
    inside.SetPosition(5, 5, 5)
    outside = clip_box.vtkBillboardTextActor3D()
    outside.SetPosition(50, 5, 5)
    host._actors += [inside, outside]
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert inside.GetVisibility() == 1 and outside.GetVisibility() == 0
    ctrl.deactivate()
    assert outside.GetVisibility() == 1


def test_label_hidden_by_user_stays_hidden_after_deactivate():
    host, ctrl = _controller()
    label = clip_box.vtkBillboardTextActor3D()
    label.SetPosition(5, 5, 5)
    label.SetVisibility(0)
    host._actors.append(label)
    ctrl.activate([0, 10, 0, 10, 0, 10])
    ctrl.deactivate()
    assert label.GetVisibility() == 0


def test_accepts_point_and_visible_part():
    host, ctrl = _controller()
    assert ctrl.accepts_point((99, 99, 99))
    assert ctrl.visible_part([(99, 99, 99)]) == [(99, 99, 99)]
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert ctrl.accepts_point((5, 5, 5))
    assert not ctrl.accepts_point((11, 5, 5))
    assert ctrl.visible_part([(99, 99, 99)]) == []


def _viewer_stub():
    from viewer_widget import VTKViewerWidget

    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.renderer = vtk.vtkRenderer()
    w.render_window = None
    w._actors = []
    w._mesh_actor = None
    w._pickable_actors = {}
    w._selection_overlay_actors = []
    w._selected_items = []
    w._window_select_mode = False
    w._zoom_window_mode = False
    w._flight = types.SimpleNamespace(active=False)
    w._display_mode = "wire_hidden"
    w._show_lines = w._show_planars = w._show_support_planar = True
    w._lines_actor = w._profiles_actor = None
    w._planar_faces_actor = w._support_planar_faces_actor = None
    w._clip = clip_box.ClipBoxController(w)
    return w


def test_viewer_add_actor_applies_planes_when_active():
    w = _viewer_stub()
    w._clip.activate([0, 10, 0, 10, 0, 10])
    actor = _actor_for(_cube_pd())
    w._add_actor(actor)
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 6
    w._clip.deactivate()
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 0


def test_viewer_clippable_actors_include_mesh_actor():
    w = _viewer_stub()
    w._mesh_actor = _actor_for(_cube_pd())
    w._clip.activate([0, 10, 0, 10, 0, 10])
    assert w._mesh_actor.GetMapper().GetNumberOfClippingPlanes() == 6
    w._clip.deactivate()
    assert w._mesh_actor.GetMapper().GetNumberOfClippingPlanes() == 0


def test_viewer_activation_bounds_use_selection_overlay_then_visible_props():
    w = _viewer_stub()
    big = _actor_for(_cube_pd(10.0))
    w._add_actor(big)
    assert w._clip_activation_bounds() == list(big.GetBounds())
    overlay = _actor_for(_cube_pd(2.0))
    w._selection_overlay_actors = [overlay]
    w._selected_items = [{"role": "lines", "index": 0}]
    assert w._clip_activation_bounds() == list(overlay.GetBounds())


def test_viewer_activation_bounds_none_without_geometry():
    w = _viewer_stub()
    assert w._clip_activation_bounds() is None


def test_gizmos_hidden_context_restores_visibility_even_on_error():
    host, ctrl = _controller()
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert ctrl._frame_actor.GetVisibility() == 1
    try:
        with ctrl.gizmos_hidden():
            assert ctrl._frame_actor.GetVisibility() == 0
            assert all(a.GetVisibility() == 0 for a in ctrl._handle_actors.values())
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert ctrl._frame_actor.GetVisibility() == 1
    assert all(a.GetVisibility() == 1 for a in ctrl._handle_actors.values())


def test_set_frame_visible_false_hides_gizmos_but_keeps_clipping():
    host, ctrl = _controller()
    actor = _actor_for(_cube_pd())
    host._actors.append(actor)
    ctrl.activate([0, 10, 0, 10, 0, 10])
    ctrl.set_frame_visible(False)
    assert ctrl._frame_actor.GetVisibility() == 0
    assert actor.GetMapper().GetNumberOfClippingPlanes() == 6
    assert not ctrl.handles_enabled()


def test_handles_disabled_in_window_select_zoom_window_and_flight():
    host, ctrl = _controller()
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert ctrl.handles_enabled()
    host._window_select_mode = True
    assert not ctrl.handles_enabled()
    host._window_select_mode = False
    host._zoom_window_mode = True
    assert not ctrl.handles_enabled()
    host._zoom_window_mode = False
    host._flight.active = True
    assert not ctrl.handles_enabled()


def test_activation_builds_cut_edges_from_edge_sources():
    host, ctrl = _controller()
    host.edge_sources = [_cube_pd()]
    ctrl.activate([2, 8, 2, 8, -1, 11])
    assert ctrl._edge_actor.GetVisibility() == 1
    assert ctrl._edge_points_actor.GetVisibility() == 0
    b = ctrl._edge_actor.GetMapper().GetInput().GetBounds()
    assert b[0] >= ctrl.box[0] - 5e-3 and b[1] <= ctrl.box[1] + 5e-3


def test_edge_actors_are_exempt_and_use_edge_color():
    host, ctrl = _controller()
    ctrl.activate([2, 8, 2, 8, -1, 11])
    assert ctrl._edge_actor._clip_exempt is True
    assert ctrl._edge_actor.GetProperty().GetColor() == tuple(ctrl.edge_color)


def test_refresh_edges_skips_when_nothing_changed():
    host, ctrl = _controller()
    host.edge_sources = [_cube_pd()]
    calls = []
    original = clip_box.compute_cut_edges

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    clip_box.compute_cut_edges = counting
    try:
        ctrl.activate([2, 8, 2, 8, -1, 11])
        first = len(calls)
        ctrl.refresh_edges()
        assert len(calls) == first
        ctrl.refresh_edges(force=True)
        assert len(calls) == first + 1
    finally:
        clip_box.compute_cut_edges = original


def test_edges_disappear_when_sources_become_empty():
    host, ctrl = _controller()
    host.edge_sources = [_cube_pd()]
    ctrl.activate([2, 8, 2, 8, -1, 11])
    host.edge_sources = []
    ctrl.refresh_edges(force=True)
    assert ctrl._edge_actor.GetVisibility() == 0


def test_set_style_recolors_frame_and_edges():
    host, ctrl = _controller()
    ctrl.activate([2, 8, 2, 8, -1, 11])
    ctrl.set_style((0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert ctrl._frame_actor.GetProperty().GetColor() == (0.0, 1.0, 0.0)
    assert ctrl._edge_actor.GetProperty().GetColor() == (0.0, 0.0, 1.0)
    assert ctrl.box_color == (0.0, 1.0, 0.0) and ctrl.edge_color == (0.0, 0.0, 1.0)


def test_deactivate_removes_edge_actors_from_renderer():
    host, ctrl = _controller()
    ctrl.activate([2, 8, 2, 8, -1, 11])
    n = host.renderer.GetActors().GetNumberOfItems()
    assert n >= 2
    ctrl.deactivate()
    assert host.renderer.GetActors().GetNumberOfItems() == n - 2


def test_visible_part_trims_cells_for_window_selection():
    host, ctrl = _controller()
    ctrl.activate([0, 10, 0, 10, 0, 10])
    box = ctrl.box
    seg = ctrl.visible_part([(-5, 5, 5), (5, 5, 5)])
    assert abs(seg[0][0] - box[0]) < 1e-9 and seg[1] == (5.0, 5.0, 5.0)
    assert ctrl.visible_part([(20, 5, 5), (30, 5, 5)]) == []
    poly = ctrl.visible_part([(-5, 0, 5), (5, 0, 5), (5, 10, 5), (-5, 10, 5)])
    assert len(poly) >= 3 and min(p[0] for p in poly) >= box[0] - 1e-9


def test_clip_lang_keys_exist_in_both_languages_without_long_dash():
    from lang import lang_fr, lang_en

    keys = [
        "tooltip_clip_box", "controls_general_clip", "controls_general_clip_handles",
        "tooltip_clip_frame", "menu_clip_box", "clip_box_margin_title", "clip_box_margin_label",
        "settings_label_clip_box", "settings_label_clip_edges",
    ]
    for key in keys:
        for module in (lang_fr, lang_en):
            value = module.MSG_UI[key]
            assert value
            assert "—" not in value and "–" not in value


def test_viewer_save_screenshot_wrapper_hides_gizmos_and_restores_on_error():
    w = _viewer_stub()
    w._clip.activate([0, 10, 0, 10, 0, 10])
    seen = {}

    def failing_impl(path, scale=1, target_size=None):
        seen["during"] = w._clip._frame_actor.GetVisibility()
        raise RuntimeError("disk full")

    w._save_screenshot_impl = failing_impl
    try:
        w.save_screenshot("x.png")
    except RuntimeError:
        pass
    assert seen["during"] == 0
    assert w._clip._frame_actor.GetVisibility() == 1


def test_margin_applies_at_next_activation_only():
    host, ctrl = _controller()
    ctrl.margin_pct = 10.0
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert ctrl.box[0] == -1.0 and ctrl.box[1] == 11.0
    ctrl.margin_pct = 50.0
    assert ctrl.box[0] == -1.0
    ctrl.deactivate()
    ctrl.activate([0, 10, 0, 10, 0, 10])
    assert ctrl.box[0] == -5.0


def test_framing_bounds_follow_box_when_active_else_visible_props():
    w = _viewer_stub()
    w._add_actor(_actor_for(_cube_pd(10.0)))
    assert w._framing_bounds() == list(w._get_visible_bounds())
    w._clip.activate([2, 4, 2, 4, 2, 4])
    assert w._framing_bounds() == w._clip.box


def _controller_with_camera(position, focal, up=(0, 0, 1)):
    host, ctrl = _controller()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(host.renderer)
    host._offscreen_window = window
    camera = host.renderer.GetActiveCamera()
    camera.SetPosition(*position)
    camera.SetFocalPoint(*focal)
    camera.SetViewUp(*up)
    ctrl.activate([0, 10, 0, 10, 0, 10])
    return host, ctrl


def test_handle_behind_camera_is_not_pickable():
    host, ctrl = _controller_with_camera((8, 5, 5), (9, 5, 5), up=(0, 0, 1))
    points = ctrl._screen_points()
    assert points[2] is None and points[3] is None
    assert points["center"] is None


def test_axial_view_excludes_handles_aligned_with_view_so_center_wins():
    host, ctrl = _controller_with_camera((5, 5, 50), (5, 5, 0), up=(0, 1, 0))
    points = ctrl._screen_points()
    assert points[4] is None and points[5] is None
    assert points["center"] is not None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
