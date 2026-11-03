# -*- coding: utf-8 -*-
"""Recouvrement de selection : pour chaque role, quels acteurs sont produits
(contour, ouvertures, face, charge redessinee), avec quelles couleurs,
epaisseurs et opacites. Les constructeurs VTK sont remplaces par des
enregistreurs : seule la decision est verifiee ici."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget

SEL = (1.0, 0.0, 1.0)


class _Mapper:
    def __init__(self):
        self.calls = []

    def SetResolveCoincidentTopologyToPolygonOffset(self):
        self.calls.append("offset")

    def SetRelativeCoincidentTopologyPolygonOffsetParameters(self, a, b):
        self.calls.append(("params", a, b))


class _Actor:
    def __init__(self, kind, pd, color, value):
        self.desc = (kind, pd, color, value)
        self.mapper = _Mapper()

    def GetMapper(self):
        return self.mapper


def _viewer(display_mode="wire_hidden", thickness=False):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._model_data = {
        "lines": ["L0", "L1"],
        "planars": [{"outer": "P0", "openings": ["O0"]}, {"outer": "P1"}],
        "planar_thicknesses": [0.2], "planar_eccentricities": [0.05],
        "load_areas": [{"outer": "A0", "openings": []}],
        "punctual_supports": ["SP0"], "linear_supports": ["SL0"], "planar_supports": [{"outer": "SS0"}],
    }
    w._display_mode = display_mode
    w._planar_thickness_enabled = thickness
    w._transparency_percent = 50
    w.selection_color = SEL
    w.selection_line_width = 2.0
    for name, width in (("linear", 3.0), ("planar", 1.0), ("load_area", 1.0), ("support_punctual", 4.0),
                        ("support_linear", 1.0), ("support_planar", 1.0)):
        setattr(w, f"{name}_color", name)
        setattr(w, f"{name}_line_width", width)
    w._build_lines_polydata = lambda items, element_indexes=None, include_section_colors=True: ("lines", list(items), include_section_colors)
    w._build_loops_wire_polydata = lambda items, openings=False, element_indexes=None: ("loops", items, openings)
    w._build_faces_polydata = lambda items, element_indexes=None: ("faces", items)
    w._build_planar_thickness_polydata = lambda items, thicknesses, eccentricities: ("thick", items, thicknesses, eccentricities)
    w._build_punctual_supports_polydata = lambda items, element_indexes=None: ("points", list(items))
    w._make_wire_actor = lambda pd, color, width: _Actor("wire", pd, color, width)
    w._make_surface_actor = lambda pd, color, opacity: _Actor("surface", pd, color, round(opacity, 6))
    w.load_auto_scale = False
    for kind, cases in (("punctual", [1, 2]), ("linear", [1]), ("planar", [3, 3])):
        setattr(w, f"_{kind}_load_data", [{"id": f"{kind}{i}", "load_case_eid": c} for i, c in enumerate(cases)])
        setattr(w, f"_{kind}_load_case_filter", None)
        setattr(w, f"{kind}_load_scale", 1.5)
        setattr(w, f"{kind}_load_color", kind)
        setattr(w, f"{kind}_load_line_width", 2.5)

        def build(loads, scale, color, line_width=1.5, norm_loads=None, global_data=None, kind=kind):
            return [((kind, [ld["id"] for ld in loads], scale, color, line_width,
                      [ld["id"] for ld in norm_loads], global_data is not None), -1)]

        setattr(w, f"_build_{kind}_load_actors", build)
    return w


def _overlay(w, role, index):
    return [a.desc if isinstance(a, _Actor) else a for a in w._make_selection_overlay_actors(role, index)]


def test_line_overlay_without_section_colors_and_hidden_in_profile_modes():
    assert _overlay(_viewer(), "lines", 1) == [("wire", ("lines", ["L1"], False), SEL, 4.0)]
    assert _overlay(_viewer("profiles_full"), "lines", 1) == []


def test_planar_overlay_outline_openings_and_offset_face():
    w = _viewer()
    actors = w._make_selection_overlay_actors("planars", 0)
    item = {"outer": "P0", "openings": ["O0"]}
    assert [a.desc for a in actors] == [
        ("wire", ("loops", [{"outer": "P0", "openings": ["O0"]}], False), SEL, 2.0),
        ("wire", ("loops", [{"outer": [], "openings": ["O0"]}], True), SEL, 2.0),
        ("surface", ("faces", [item]), SEL, 0.18),
    ]
    assert actors[2].mapper.calls == ["offset", ("params", -4, -4)]
    assert actors[0].mapper.calls == []


@pytest.mark.parametrize("index, expected", [(0, [0.2], ), (1, [0.0])])
def test_planar_face_follows_the_thickened_solid_in_profile_modes(index, expected):
    w = _viewer("profiles_full", thickness=True)
    face = w._make_selection_overlay_actors("planars", index)[2].desc
    eccentricity = [0.05] if index == 0 else [0.0]
    assert face[1] == ("thick", [w._model_data["planars"][index]], expected, eccentricity)
    assert _viewer("profiles_full")._make_selection_overlay_actors("planars", 0)[2].desc[1][0] == "faces"


def test_area_like_overlays_outline_and_face():
    w = _viewer()
    w._transparency_percent = 0
    assert _overlay(w, "load_areas", 0) == [
        ("wire", ("loops", [{"outer": "A0", "openings": []}], False), SEL, 2.0),
        ("surface", ("faces", [{"outer": "A0", "openings": []}]), SEL, 0.3),
    ]
    assert _overlay(w, "support_planar", 0) == [
        ("wire", ("loops", [{"outer": "SS0", "openings": []}], False), SEL, 2.0),
        ("surface", ("faces", [{"outer": "SS0"}]), SEL, 0.3),
    ]


def test_support_overlays():
    w = _viewer()
    assert _overlay(w, "support_punctual", 0) == [("wire", ("points", ["SP0"]), SEL, 5.0)]
    assert _overlay(w, "support_linear", 0) == [("wire", ("lines", ["SL0"], True), SEL, 2.0)]


def test_load_overlay_is_normalised_on_the_visible_cases():
    w = _viewer()
    w._punctual_load_case_filter = {2}
    assert _overlay(w, "punctual_load", 0) == [("punctual", ["punctual0"], 1.5, SEL, 3.5, ["punctual1"], False)]
    assert _overlay(w, "planar_load", 1) == [("planar", ["planar1"], 1.5, SEL, 3.5, ["planar0", "planar1"], True)]


@pytest.mark.parametrize("role, index", [
    ("lines", 5), ("planars", -1), ("load_areas", 1), ("support_punctual", 3), ("support_linear", 1),
    ("support_planar", 2), ("linear_load", 4), ("inconnu", 0),
])
def test_out_of_range_index_or_unknown_role_gives_no_overlay(role, index):
    assert _viewer()._make_selection_overlay_actors(role, index) == []
