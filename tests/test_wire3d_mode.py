# -*- coding: utf-8 -*-
"""Mode d'affichage "Filaire 3D" (profiles_wire) : solides de profils et
surfaciques epaissis rendus en aretes seules, sans faces, en transparence
totale, mais toujours selectionnables."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

import viewer_widget
from clip_box import ClipBoxController
from viewer_widget import VTKViewerWidget

WIRE = "profiles_wire"


def _cube_actor():
    src = vtk.vtkCubeSource()
    src.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def _scene_widget(mode):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.renderer = vtk.vtkRenderer()
    w.render_window = types.SimpleNamespace(Render=lambda: None)
    w._display_mode = mode
    for name in (
        "_lines_actor", "_planar_actor", "_openings_actor", "_load_areas_actor", "_load_areas_faces_actor",
        "_support_punctual_actor", "_support_linear_actor", "_support_planar_actor",
        "_support_planar_faces_actor", "_support_planar_centroid_actor", "_mesh_actor",
    ):
        setattr(w, name, None)
    w._profiles_actor = _cube_actor()
    w._planar_faces_actor = _cube_actor()
    w._planar_edges_actor = _cube_actor()
    w._load_areas_faces_actor = _cube_actor()
    w._support_planar_faces_actor = _cube_actor()
    w._show_lines = w._show_planars = w._show_load_areas = True
    w._show_support_punctual = w._show_support_linear = w._show_support_planar = True
    w._show_mesh = False
    w._selection_overlay_actors = []
    w._selected_item = None
    w._selected_items = []
    w._transparency_percent = 0
    w._profiles_transparency_percent = 0
    w.planar_faces_base_opacity = 0.35
    w.load_areas_faces_base_opacity = 0.30
    w.support_planar_faces_base_opacity = 0.35
    w.linear_color = (0.5, 0.5, 0.5)
    w.selection_color = (1.0, 0.0, 0.0)
    w._profiles_wire_applied = False
    w._profiles_base_pd = None
    w._profiles_base_colors = None
    w._clip = ClipBoxController(w)
    return w


def test_wire3d_is_a_profile_mode_and_a_known_display_mode():
    assert WIRE in viewer_widget._PROFILE_MODES
    assert WIRE in viewer_widget._ALL_DISPLAY_MODES
    assert viewer_widget._ALL_DISPLAY_MODES[-1] == WIRE


def test_wire3d_profiles_actor_is_unlit_wireframe_without_hidden_line_removal():
    w = _scene_widget(WIRE)
    w._apply_visibility_state()
    prop = w._profiles_actor.GetProperty()
    assert prop.GetRepresentation() == vtk.VTK_WIREFRAME
    assert not prop.GetLighting()
    assert prop.GetEdgeVisibility() == 0
    assert w.renderer.GetUseHiddenLineRemoval() == 0
    assert w._profiles_actor.GetVisibility() == 1


def test_leaving_wire3d_restores_surface_lit_profiles():
    w = _scene_widget(WIRE)
    w._apply_visibility_state()
    w._display_mode = "profiles_full"
    w._apply_visibility_state()
    prop = w._profiles_actor.GetProperty()
    assert prop.GetRepresentation() == vtk.VTK_SURFACE
    assert prop.GetLighting()
    assert prop.GetEdgeVisibility() == 1


def test_wire3d_planar_faces_invisible_but_still_pickable_and_edges_shown():
    w = _scene_widget(WIRE)
    w._apply_visibility_state()
    for actor in (w._planar_faces_actor, w._load_areas_faces_actor, w._support_planar_faces_actor):
        assert actor.GetVisibility() == 1
        opacity = actor.GetProperty().GetOpacity()
        assert 0.0 < opacity <= 0.02  # strictement > 0 : vtkCellPicker ignore les acteurs d'opacite nulle
    assert w._planar_edges_actor.GetVisibility() == 1


def test_wire3d_edges_use_the_wire_gray_and_full_mode_keeps_black():
    w = _scene_widget(WIRE)
    w._apply_visibility_state()
    assert tuple(w._planar_edges_actor.GetProperty().GetColor()) == viewer_widget._WIRE3D_COLOR
    assert tuple(w._profiles_actor.GetProperty().GetColor()) == viewer_widget._WIRE3D_COLOR
    w._display_mode = "profiles_full"
    w._apply_visibility_state()
    assert tuple(w._planar_edges_actor.GetProperty().GetColor()) == (0.0, 0.0, 0.0)


def test_wire3d_recolors_a_profiles_actor_rebuilt_while_already_in_wire3d():
    w = _scene_widget(WIRE)
    w._apply_visibility_state()
    w._profiles_actor = _cube_actor()  # reconstruction (filtre, isolation, rechargement) : nouvel acteur, couleur par defaut
    w._profiles_actor.GetProperty().SetColor(*w.linear_color)
    w._apply_visibility_state()
    assert tuple(w._profiles_actor.GetProperty().GetColor()) == viewer_widget._WIRE3D_COLOR


def test_wire3d_ignores_section_colors_but_selection_still_colored():
    w = _scene_widget(WIRE)
    pd = w._profiles_actor.GetMapper().GetInput()
    idx = vtk.vtkIntArray()
    idx.SetName(w.ELEMENT_INDEX_ARRAY)
    sc = vtk.vtkUnsignedCharArray()
    sc.SetName("section_colors")
    sc.SetNumberOfComponents(3)
    for _ in range(pd.GetNumberOfCells()):
        idx.InsertNextValue(0)
        sc.InsertNextTuple3(10, 200, 30)
    pd.GetCellData().AddArray(idx)
    w._profiles_base_pd = pd
    w._profiles_base_colors = sc
    w._apply_visibility_state()
    mapper = w._profiles_actor.GetMapper()
    assert mapper.GetScalarVisibility() == 0

    w._selected_items = [{"role": "lines", "index": 0}]
    w._apply_profiles_selection_colors()
    assert mapper.GetScalarVisibility() == 1
    first = pd.GetCellData().GetScalars().GetTuple3(0)
    assert first == tuple(float(round(c * 255.0)) for c in w.selection_color)


def test_non_wire_modes_still_use_section_colors():
    w = _scene_widget("profiles_full")
    pd = w._profiles_actor.GetMapper().GetInput()
    idx = vtk.vtkIntArray()
    idx.SetName(w.ELEMENT_INDEX_ARRAY)
    sc = vtk.vtkUnsignedCharArray()
    sc.SetName("section_colors")
    sc.SetNumberOfComponents(3)
    for _ in range(pd.GetNumberOfCells()):
        idx.InsertNextValue(0)
        sc.InsertNextTuple3(10, 200, 30)
    pd.GetCellData().AddArray(idx)
    w._profiles_base_pd = pd
    w._profiles_base_colors = sc
    w._apply_profiles_selection_colors()
    assert w._profiles_actor.GetMapper().GetScalarVisibility() == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
