# -*- coding: utf-8 -*-
"""Non-regression du maillage des profils 3D : nombre de cellules et volume
signe par element (le signe traduit le sens final des normales), releves sur
l'implementation d'avant la vectorisation numpy."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viewer_widget import VTKViewerWidget
import ad_model_data as md
import test_profile_render as tpr

GOLDEN = {  # element_index: (cellules, volume signe)
    100: (32, -0.0200251), 101: (6, 0.107999901), 102: (72, 0.00491851217),
    103: (14, -0.000911972225), 104: (20, -0.0161694453), 105: (32, -0.0215616669),
    106: (32, -0.0135362128), 107: (32, -0.0225603547), 108: (32, 0.00297040125),
    109: (100, -2.6884498), 110: (32, -0.0305367038), 111: (64, -0.0174415707),
    112: (28, -2.74658206e-07),
}
GOLDEN_CELLS, GOLDEN_POINTS = 496, 350


def _sec(name, typ, p1, p2, angle=0.0, exc=None):
    el = {"generalBeamType": "Beam", "section": {"value": 1}, "sectionOrientationAngle": angle,
          "geomPtStart": dict(zip("xyz", p1)), "geomPtEnd": dict(zip("xyz", p2))}
    if exc:
        el["sectionExcentration"] = {"option": exc}
    return md._build_line_section_render(el, el["geomPtStart"], el["geomPtEnd"], {1: {"name": name, "type": typ}})


def _model():
    simple = [
        ((0, 0, 0), (4, 1, 0.5), ("IPE 300", "I_SYMETRIC", 0.3, None)),
        ((0, 2, 0), (3, 2, 0), ("TUBE 100x100x5", "RECTANGULAR_TUBE", 0.0, None)),
        ((0, 4, 0), (0, 4, 3), ("CHS 114.3x5", "CIRCULAR_TUBE", 0.0, None)),
        ((2, 6, 0), (2, 6, 3), ("R 30x50", "RECTANGLE", 0.0, None)),
        ((0, 8, 0), (5, 8, 0), ("UPN 200", "U", math.pi / 2, "droite_haut")),
        ((0, 18, 0), (4, 18, 2), ("IPE 300", "I_SYMETRIC", 1.0, None)),
        ((0, 20, 0), (3, 20, 0), ("HEA 200", "I_SYMETRIC", 0.0, None)),
        ((3, 20, 0), (6, 20, 0), ("HEA 200", "I_SYMETRIC", 0.0, None)),
        ((1, 22, 1), (1, 22, 1), ("IPE 300", "I_SYMETRIC", 0.0, None)),
    ]
    lines = [[a, b] for a, b, _ in simple]
    secs = [_sec(n, t, a, b, ang, exc) for a, b, (n, t, ang, exc) in simple]
    for s, seg in ((tpr._haunched("haut_et_bas", "bas"), ((0, 10, 0), (6, 10, 0))),
                   (tpr._variable_section("VariableBeam"), ((0, 12, 0), (4, 12, 0))),
                   (tpr._combined("CS1 IPE200 IPE200"), ((0, 14, 0), (4, 14, 0))),
                   (tpr._combined("CS7 L80X80X8 L80X80X8"), ((0, 16, 0), (4, 16, 0)))):
        secs.append(s)
        lines.append(list(seg))
    secs.append(None)
    lines.append([(0, 0, 0), (1, 0, 0)])
    return lines, secs


def _widget(color_by_section=False):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._color_by_section = color_by_section
    return w


def _stats(pd):
    ei = pd.GetCellData().GetArray("element_index")
    stats = {}
    for c in range(pd.GetNumberOfCells()):
        ids = pd.GetCell(c).GetPointIds()
        pts = [pd.GetPoint(ids.GetId(k)) for k in range(ids.GetNumberOfIds())]
        vol = 0.0
        for k in range(1, len(pts) - 1):
            a, b, d = pts[0], pts[k], pts[k + 1]
            vol += (a[0] * (b[1] * d[2] - b[2] * d[1]) - a[1] * (b[0] * d[2] - b[2] * d[0])
                    + a[2] * (b[0] * d[1] - b[1] * d[0])) / 6.0
        e = int(ei.GetTuple1(c))
        n, v = stats.get(e, (0, 0.0))
        stats[e] = (n + 1, v + vol)
    return stats


def test_mesh_matches_golden():
    lines, secs = _model()
    pd = _widget()._build_profiles_polydata(lines, secs, element_indexes=[100 + i for i in range(len(lines))])
    assert pd.GetNumberOfCells() == GOLDEN_CELLS
    assert pd.GetNumberOfPoints() == GOLDEN_POINTS
    stats = _stats(pd)
    assert set(stats) == set(GOLDEN)
    for e, (cells, vol) in GOLDEN.items():
        assert stats[e][0] == cells, (e, stats[e])
        # tolerance : bruit float32 d'un autre decoupage (valide) des capuchons
        # concaves ; une normale inversee changerait le volume bien davantage
        assert abs(stats[e][1] - vol) <= 1e-8 + 1e-6 * abs(vol), (e, stats[e])


def test_section_colors_follow_element():
    lines, secs = _model()
    w = _widget(color_by_section=True)
    w._line_section_name = lambda idx: f"S{idx % 3}"
    w._get_section_color = lambda name: {"S0": (255, 0, 0), "S1": (0, 255, 0), "S2": (0, 0, 255)}[name]
    pd = w._build_profiles_polydata(lines, secs, element_indexes=[100 + i for i in range(len(lines))])
    sc = pd.GetCellData().GetScalars()
    ei = pd.GetCellData().GetArray("element_index")
    assert sc is not None and sc.GetName() == "section_colors"
    assert sc.GetNumberOfTuples() == pd.GetNumberOfCells()
    for c in range(pd.GetNumberOfCells()):
        e = int(ei.GetTuple1(c))
        assert tuple(int(sc.GetComponent(c, k)) for k in range(3)) == w._get_section_color(f"S{e % 3}")


def test_no_valid_element_returns_none():
    w = _widget()
    assert w._build_profiles_polydata([], [], element_indexes=[]) is None
    assert w._build_profiles_polydata([[(0, 0, 0), (1, 0, 0)]], [None], element_indexes=[0]) is None


if __name__ == "__main__":
    for _k, _fn in sorted(globals().items()):
        if _k.startswith("test_") and callable(_fn):
            _fn()
            print("ok", _k)
