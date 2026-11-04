# -*- coding: utf-8 -*-
"""Reglages d'affichage de la vue 3D : epaisseurs, appuis, etat d'affichage,
filtres, maillage, faces des surfaciques, croix de centroide, recouvrement de
selection, nettoyage, capture d'image a taille exacte."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import viewer_config
from test_clip_box import _viewer_stub
from viewer_widget import VTKViewerWidget


def _actor():
    return vtk.vtkActor()


def _widths_viewer():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.log = []
    for attr in ("_lines_actor", "_planar_actor", "_openings_actor", "_load_areas_actor",
                 "_support_linear_actor", "_support_planar_actor", "_support_planar_centroid_actor"):
        setattr(w, attr, _actor())
    w._refresh_selection_overlay = lambda: w.log.append("overlay")
    w._apply_visibility_state = lambda: w.log.append("visibility")
    return w


def test_line_widths_are_clamped_and_applied_to_existing_actors():
    w = _widths_viewer()
    w._openings_actor = None
    w.set_line_widths(2.5, 0, "3", 1)
    assert (w.linear_line_width, w.planar_line_width, w.opening_line_width, w.load_area_line_width) == (2.5, 0.1, 3.0, 1.0)
    assert w._lines_actor.GetProperty().GetLineWidth() == 2.5
    assert w._planar_actor.GetProperty().GetLineWidth() == pytest.approx(0.1)
    assert w._load_areas_actor.GetProperty().GetLineWidth() == 1.0
    assert w.log == ["overlay"]


def test_support_styles_update_widths_and_rebuild_point_supports():
    w = _widths_viewer()
    replaced = []
    w.support_punctual_color = (1, 0, 0)
    w._support_punctual_points = [(0, 0, 0)]
    w._support_punctual_indexes = [4]
    w._build_punctual_supports_polydata = lambda pts, element_indexes=None: ("pd", pts, element_indexes)
    w._make_wire_actor = lambda pd, color, width: (pd, color, width)
    w._replace_actor = lambda name, actor, role=None, pickable=False: replaced.append((name, actor, role, pickable))
    w.set_support_styles(0.01, 3, 0.05, 2)
    assert (w.support_punctual_size, w.support_punctual_line_width) == (0.05, 3.0)
    assert w._support_linear_actor.GetProperty().GetLineWidth() == pytest.approx(0.1)
    assert w._support_planar_centroid_actor.GetProperty().GetLineWidth() == 2.0
    assert replaced == [("_support_punctual_actor", (("pd", [(0, 0, 0)], [4]), (1, 0, 0), 3.0), "support_punctual", True)]
    assert w.log == ["visibility", "overlay"]
    w._support_punctual_points = []
    replaced.clear()
    w.set_support_styles(1, 1, 1, 1)
    assert replaced == []


def _display_viewer(mode="wireframe"):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.log = []
    w._display_mode = mode
    w.orientation_widget = types.SimpleNamespace(SetEnabled=lambda v: w.log.append(("marker", v)),
                                                 InteractiveOff=lambda: w.log.append("marker fixed"))
    w._apply_visibility_state = lambda: w.log.append("visibility")
    w._rebuild_filtered_structural_actors = lambda rebuild_profiles=True: w.log.append(("rebuild", rebuild_profiles))
    return w


def test_display_state_is_applied_in_one_pass():
    w = _display_viewer()
    w.apply_display_state(True, False, True, False, True, False, True, "full", 150, -3)
    assert (w._show_lines, w._show_planars, w._show_load_areas) == (True, False, True)
    assert (w._show_support_punctual, w._show_support_linear, w._show_support_planar) == (False, True, False)
    assert w._display_mode == "full" and w._transparency_percent == 100 and w._profiles_transparency_percent == 0
    assert w.log == [("marker", 1), "marker fixed", "visibility"]


def test_unknown_display_mode_falls_back_and_profile_switch_rebuilds_actors():
    w = _display_viewer("full")
    w.apply_display_state(*[False] * 7, "inconnu", 0)
    assert w._display_mode == "wireframe" and w.log == [("marker", 0), "visibility"]
    w = _display_viewer("full")
    w.apply_display_state(*[True] * 7, "profiles_full", 0)
    assert w.log[-1] == ("rebuild", True)
    w.orientation_widget = None
    w.log.clear()
    w.apply_display_state(*[True] * 7, "wireframe", 0)
    assert w.log == [("rebuild", True)]


def test_structural_filters_are_stored_as_text_sets():
    w = _display_viewer()
    w.set_structural_filters(section_names=["IPE 200", 300], material_names=[], rebuild_profiles=False)
    assert w._filter_section_names == {"IPE 200", "300"} and w._filter_thickness_names is None
    assert w._filter_material_names == set() and w.log == [("rebuild", False)]


def test_mesh_keeps_only_the_faces_of_visible_elements():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    loaded = []
    w.get_visible_planar_eids = lambda: [10]
    w.get_visible_linear_eids = lambda: [20]
    w.load_mesh = lambda nodes, faces: loaded.append((nodes, faces, w._show_mesh))
    w._show_mesh = False
    w.refresh_mesh(["n"], {"10": [[0, 1, 2]], 20: [[1, 2, 3], [2, 3, 4]], 30: [[9, 9, 9]]})
    assert loaded == [(["n"], [[0, 1, 2], [1, 2, 3], [2, 3, 4]], True)]


def test_planar_faces_are_flat_or_thickened_in_profile_modes():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    replaced = {}
    w._model_data = {"planars": ["P0", "P1"], "planar_thicknesses": [0.2, 0.3], "planar_eccentricities": [0.0, 0.1]}
    w._filtered_planar_indexes = lambda: [1]
    w.planar_color, w.planar_faces_base_opacity = "gris", 0.35
    w._build_faces_polydata = lambda items, element_indexes=None: ("flat", items, element_indexes)
    w._build_planar_thickness_polydata = lambda items, t, e, element_indexes=None: ("thick", items, t, e, element_indexes)
    w._build_planar_edges_polydata = lambda pd: ("edges", pd[0])
    w._make_surface_actor = lambda pd, color, opacity: ("surface", pd, color, opacity)
    w._make_wire_actor = lambda pd, color, width: ("wire", pd, color, width)
    w._replace_actor = lambda name, actor, role=None, pickable=False: replaced.__setitem__(name, (actor, role, pickable))
    w._planar_thickness_enabled, w._display_mode = True, "wire_hidden"
    w._rebuild_planar_faces_actor()
    assert replaced["_planar_faces_actor"] == (("surface", ("flat", ["P1"], [1]), "gris", 0.35), "planars", True)
    assert replaced["_planar_edges_actor"][0] == ("wire", ("edges", "flat"), (0.0, 0.0, 0.0), 1.0)
    w._display_mode = "profiles_full"
    w._rebuild_planar_faces_actor()
    assert replaced["_planar_faces_actor"][0][1] == ("thick", ["P1"], [0.3], [0.1], [1])


@pytest.mark.parametrize("role, color_attr, base_attr", [
    ("planars", "planar_color", "planar_faces_base_opacity"),
    ("load_areas", "load_area_color", "load_areas_faces_base_opacity"),
    ("support_planar", "support_planar_color", "support_planar_faces_base_opacity"),
])
def test_face_color_and_opacity_by_role(role, color_attr, base_attr):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._transparency_percent = 50
    setattr(w, color_attr, "couleur")
    setattr(w, base_attr, 0.4)
    assert w._base_face_color_opacity(role) == ("couleur", pytest.approx(0.2))
    w.selection_color = "sel"
    assert w._base_face_color_opacity("autre") == ("sel", pytest.approx(0.18))


def _scene():
    w = _viewer_stub()
    w._diagram_overlay_actors = []
    w._diagram_label_actors = []
    w._grid_actors = []
    renders = []
    w.render_window = types.SimpleNamespace(Render=lambda: renders.append(1))
    w.renders = renders
    return w


def test_removing_an_actor_forgets_it_everywhere():
    w = _scene()
    actor = _actor()
    w._add_actor(actor, role="lines", pickable=True)
    w._selection_overlay_actors.append(actor)
    w._diagram_overlay_actors.append(actor)
    w._remove_actor(actor)
    assert actor not in w._actors and w._pickable_actors == {}
    assert w._selection_overlay_actors == [] and w._diagram_overlay_actors == []
    assert w.renderer.GetActors().GetNumberOfItems() == 0
    w._remove_actor(None)


def test_clearing_the_result_diagram_removes_its_actors_and_labels():
    w = _scene()
    kept, diagram = _actor(), _actor()
    w._add_actor(kept)
    w._add_actor(diagram)
    w._diagram_overlay_actors = [diagram]
    w._diagram_label_actors = ["label"]
    w.clear_result_diagram()
    assert w._actors == [kept] and w._diagram_overlay_actors == [] and w._diagram_label_actors == []
    assert w.renders == [1]


def test_planar_support_centroid_cross_is_drawn_then_replaced():
    w = _scene()
    w.selection_color, w.support_planar_line_width = (1, 0, 0), 2.0
    w._support_planar_centroid_actor = None
    w._apply_visibility_state = lambda: w.renders.append("visibility")
    w.show_planar_support_result_centroid({"point": (1, 2, 3), "u": (2, 0, 0), "v": (0, 0, 0), "size": 1.0})
    actor = w._support_planar_centroid_actor
    pd = actor.GetMapper().GetInput()
    points = sorted(tuple(round(c, 9) for c in pd.GetPoint(i)) for i in range(pd.GetNumberOfPoints()))
    assert points == [(0.5, 2, 3), (1, 1.5, 3), (1, 2.5, 3), (1.5, 2, 3)]   # v nul -> axe y par defaut
    assert pd.GetNumberOfCells() == 2 and not actor.GetPickable()
    w.show_planar_support_result_centroid(None)
    assert w._support_planar_centroid_actor is None and actor not in w._actors
    assert w._build_centroid_cross_polydata(("a", 0, 0), None, None, 1.0) is None


def test_point_supports_are_rendered_as_spheres_scaled_by_their_size():
    w = _scene()
    w.support_punctual_color, w.support_punctual_line_width, w.support_punctual_size = (0, 0, 1), 2.0, 0.35
    actor = w._make_support_points_actor([(0, 0, 0), "bruit", (1, 1, 1)], element_indexes=[5, 6, 7])
    prop = actor.GetProperty()
    assert prop.GetRepresentation() == vtk.VTK_POINTS and prop.GetRenderPointsAsSpheres()
    assert prop.GetPointSize() == pytest.approx(3.5)
    assert actor.GetMapper().GetInput().GetNumberOfPoints() == 2
    assert w._make_support_points_actor([]) is None


@pytest.mark.parametrize("visible, corner, expected", [
    (True, "bottom_left", "BOTTOM_RIGHT"), (True, "bottom_right", "BOTTOM_LEFT"), (False, "bottom_left", "BOTTOM_LEFT"),
])
def test_axes_widget_moves_out_of_the_minimap_corner(visible, corner, expected):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    viewports = []
    w.orientation_widget = types.SimpleNamespace(SetViewport=lambda *v: viewports.append(v))
    w._minimap = types.SimpleNamespace(visible=visible, corner=corner)
    w._sync_orientation_widget_corner()
    assert viewports == [getattr(VTKViewerWidget, f"_ORIENTATION_WIDGET_VIEWPORT_{expected}")]
    w.orientation_widget = None
    w._sync_orientation_widget_corner()


def test_selection_overlay_is_rebuilt_and_profiles_recolored_in_profile_modes():
    w = _scene()
    old, new = _actor(), _actor()
    w._add_actor(old)
    w._selection_overlay_actors = [old]
    w._selected_items = [{"role": "lines", "index": 0}, {"role": "planars", "index": 1}]
    w._make_selection_overlay_actors = lambda role, index: [new] if role == "lines" else []
    calls = []
    w._apply_profiles_selection_colors = lambda: calls.append("recolor")
    w._apply_visibility_state = lambda: calls.append("visibility")
    w._display_mode = "profiles_full"
    w._refresh_selection_overlay()
    assert w._selection_overlay_actors == [new] and old not in w._actors and new in w._actors
    assert calls == ["recolor", "visibility"]


@pytest.mark.parametrize("dark", [False, True])
def test_window_rectangle_actor_is_created_once_with_a_theme_colour(dark):
    w = _scene()
    w._window_rect_actor = None
    original = viewer_config.VTK_BG
    viewer_config.VTK_BG = viewer_config._DARK_VTK_BG if dark else (1.0, 1.0, 1.0)
    try:
        w._ensure_window_rect_actor()
    finally:
        viewer_config.VTK_BG = original
    actor = w._window_rect_actor
    assert not actor.GetVisibility() and not actor.GetPickable()
    assert actor.GetProperty().GetColor() == pytest.approx((0.95,) * 3 if dark else (0.10,) * 3)
    w._ensure_window_rect_actor()
    assert w._window_rect_actor is actor and w.renderer.GetViewProps().GetNumberOfItems() == 1


def test_screenshot_is_written_at_the_exact_size_without_resizing_the_view(tmp_path):
    w = _scene()
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(200, 100)
    window.AddRenderer(w.renderer)
    w.render_window = window
    w._minimap = types.SimpleNamespace(visible=False, renderer=None)
    w._add_actor(_actor())
    path = str(tmp_path / "vue.png")
    w._save_screenshot_exact_size(path, (64, 48))
    reader = vtk.vtkPNGReader()
    reader.SetFileName(path)
    reader.Update()
    assert reader.GetOutput().GetDimensions()[:2] == (64, 48)
    assert window.GetSize() == (200, 100) and window.HasRenderer(w.renderer)


def test_clear_scene_empties_the_view_selection_filters_and_clip_box():
    w = _scene()
    w.render_window = None
    events = []
    w.clipBoxChanged = types.SimpleNamespace(emit=lambda active: events.append(("clip", active)))
    w._update_view_overlay = lambda render=True: events.append(("overlay", render))
    w._minimap = types.SimpleNamespace(clear_geometry=lambda: events.append("minimap"))
    w._apply_visibility_state = lambda: events.append("visibility")
    w._add_actor(_actor(), role="lines", pickable=True)
    w._clip.activate([0, 1, 0, 1, 0, 1])
    w._selected_items = [{"role": "lines", "index": 0}]
    w._isolated_selection = [{"role": "lines", "index": 0}]
    w._hidden_items = {("lines", 0)}
    w._filter_section_names = {"IPE"}
    w.lines_count = 3
    w.clear_scene()
    assert not w._clip.active and ("clip", False) in events
    assert w.renderer.GetActors().GetNumberOfItems() == 0 and w._actors == [] and w._pickable_actors == {}
    assert w._selected_items == [] and w._selected_item is None
    assert w._isolated_selection == [] and w._hidden_items == set() and w._filter_section_names is None
    assert w.lines_count == 0 and w._model_data["lines"] == [] and not w._has_model
    assert events[-1] == "visibility" and "minimap" in events
