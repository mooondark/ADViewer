# -*- coding: utf-8 -*-
"""Pointage au clic sur les gros maillages (profiles) : seules les cellules proches
du pixel sont testees, avec le meme resultat que sur le maillage entier dans les
scenes ci-dessous ; et couleurs de selection identiques a la boucle cellule par cellule."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import vtk

import ad_model_data as md
import viewer_widget as vw
from test_clip_box import _viewer_stub
from test_profile_render import _profiles_widget_with_cache
from test_window_select_rect import _actor

_SECTIONS = {1: {"name": "IPE 300", "type": "I_SYMETRIC"}, 2: {"name": "CHS 114.3x5", "type": "CIRCULAR_TUBE"}}


def _scene(count, parallel=False, position=(-30.0, -60.0, 40.0), focal=(15.0, 12.0, 4.0), clip=None, opacity=1.0):
    """Poutres sur une grille 10 x 10 x n et une dalle, camera hors ecran 400 x 300."""
    w = _viewer_stub()
    w._display_mode = "profiles_hidden"
    w._color_by_section = False
    lines, sections = [], []
    for i in range(count):
        x, y, z = (i % 10) * 3.5, ((i // 10) % 10) * 2.5, (i // 100) * 1.5
        p1 = {"x": x, "y": y, "z": z}
        p2 = {"x": x + 3.0, "y": y, "z": z} if i % 3 else {"x": x, "y": y, "z": z + 1.2}
        element = {"generalBeamType": "Beam", "section": {"value": 1 + i % 2}, "sectionOrientationAngle": 0.0,
                   "geomPtStart": p1, "geomPtEnd": p2}
        sections.append(md._build_line_section_render(element, p1, p2, _SECTIONS))
        lines.append([tuple(p1.values()), tuple(p2.values())])
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(w._build_profiles_polydata(lines, sections, element_indexes=list(range(count))))
    profiles = vtk.vtkActor()
    profiles.SetMapper(mapper)
    profiles.GetProperty().SetOpacity(opacity)
    slab = _actor([(0, [(0, 0, -1), (35, 0, -1), (35, 25, -1), (0, 25, -1)])], "polys")
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(w.renderer)
    w._window = window
    for actor, role in ((profiles, "lines"), (slab, "planars")):
        w.renderer.AddActor(actor)
        w._pickable_actors[w._actor_key(actor)] = {"actor": actor, "role": role}
    camera = w.renderer.GetActiveCamera()
    camera.SetParallelProjection(parallel)
    camera.SetPosition(*position)
    camera.SetFocalPoint(*focal)
    camera.SetViewUp(0.0, 0.0, 1.0)
    camera.SetParallelScale(14.0)
    if clip:
        w._clip.activate(clip)
        for actor in (profiles, slab):
            w._clip.apply_to_actor(actor)
    w.renderer.ResetCameraClippingRange()
    window.Render()
    return w, profiles


def _clicks():
    return [(x, y) for x in range(40, 400, 45) for y in range(30, 300, 40)]


def _picked(w, clicks):
    return [[(c["role"], c["index"], c["key"], c["cell_id"], c["actor"]) for c in w._pick_selection_candidates(x, y)]
            for x, y in clicks]


@pytest.mark.parametrize("scene", [
    dict(parallel=True),
    dict(),
    # geometrie bien plus proche que le point focal : la tolerance de VTK couvre plus de pixels
    dict(position=(8.0, -6.0, 5.0), focal=(80.0, 120.0, -40.0)),
    dict(clip=[0.0, 18.0, 0.0, 14.0, -2.0, 4.0]),
    dict(opacity=0.01),   # Filaire 3D
], ids=["ortho", "perspective", "focal-lointain", "boite-de-coupe", "filaire-3d"])
def test_preselection_picks_exactly_what_the_full_mesh_picks(monkeypatch, scene):
    w, _profiles = _scene(300, **scene)
    pickables = dict(w._pickable_actors)
    monkeypatch.setattr(vw, "_PRESELECT_MIN_CELLS", 10 ** 9)
    expected = _picked(w, _clicks())
    assert sum(any(c[0] == "lines" for c in hits) for hits in expected) >= 5
    monkeypatch.setattr(vw, "_PRESELECT_MIN_CELLS", 0)
    assert _picked(w, _clicks()) == expected
    assert w._pickable_actors == pickables


def test_picking_a_large_profiles_mesh_is_fast():
    w, _profiles = _scene(5000)
    start = time.perf_counter()
    candidates = w._pick_selection_candidates(200, 150)
    assert time.perf_counter() - start < 0.25   # environ 0,7 s sur le maillage entier
    assert candidates


def _loop_colors(w):
    """Couleurs attendues, cellule par cellule (reference)."""
    pd = w._profiles_base_pd
    index = pd.GetCellData().GetArray(w.ELEMENT_INDEX_ARRAY)
    selected = {int(it["index"]) for it in w._selected_items if it.get("role") == "lines"}
    wire3d = w._display_mode == "profiles_wire"
    base = None if wire3d else w._profiles_base_colors
    chosen = tuple(round(c * 255.0) for c in w.selection_color)
    plain = tuple(round(c * 255.0) for c in (vw._WIRE3D_COLOR if wire3d else w.linear_color))
    colors = []
    for i in range(pd.GetNumberOfCells()):
        if int(index.GetTuple1(i)) in selected:
            colors.append(chosen)
        elif base is not None:
            colors.append(tuple(int(base.GetComponent(i, k)) for k in range(3)))
        else:
            colors.append(plain)
    return colors


@pytest.mark.parametrize("by_section, mode", [(True, "profiles_hidden"), (False, "profiles_hidden"), (True, "profiles_wire")],
                         ids=["couleurs-de-section", "couleur-unie", "filaire-3d"])
def test_selection_colors_match_the_per_cell_reference(by_section, mode):
    w = _profiles_widget_with_cache(color_by_section=by_section)
    w._display_mode = mode
    w._selected_items = [{"role": "lines", "index": 0}, {"role": "lines", "index": 2}, {"role": "planars", "index": 1}]
    w._apply_profiles_selection_colors()
    scalars = w._profiles_base_pd.GetCellData().GetScalars()
    assert scalars.GetName() == "section_colors" and scalars.GetDataType() == vtk.VTK_UNSIGNED_CHAR
    assert [tuple(int(v) for v in scalars.GetTuple3(i)) for i in range(scalars.GetNumberOfTuples())] == _loop_colors(w)
