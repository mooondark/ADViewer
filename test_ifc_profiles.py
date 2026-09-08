# -*- coding: utf-8 -*-
"""
test_ifc_profiles.py
Non-regression : apres extraction de la geometrie de section vers
section_geometry, IfcWriter.profile_from_dims produit toujours les memes
entites IFC. Skip si ifcopenshell est absent.

Aucune dependance hors ifcopenshell : `python test_ifc_profiles.py`.
"""

import sys

try:
    import ifcopenshell  # noqa: F401
except ImportError:
    print("ifcopenshell absent -> test ignore")
    sys.exit(0)

from ad_ifc_exporter import IfcWriter
from section_geometry import parse_section_dims


def _profile(name):
    dims = parse_section_dims({"name": name, "materialName": "S275"})
    return IfcWriter().profile_from_dims(name, dims)


def test_i_shape():
    p = _profile("IPE 300")
    assert p.is_a() == "IfcIShapeProfileDef"
    assert round(p.OverallWidth, 6) == 0.15
    assert round(p.OverallDepth, 6) == 0.3


def test_circle_hollow():
    p = _profile("CHS 168.3X10")
    assert p.is_a() == "IfcCircleHollowProfileDef"
    assert round(p.Radius, 6) == round(0.1683 / 2, 6)
    assert round(p.WallThickness, 6) == 0.01


def test_rectangle_hollow():
    p = _profile("RHS 200X100X8")
    assert p.is_a() == "IfcRectangleHollowProfileDef"
    assert round(p.XDim, 6) == 0.1
    assert round(p.YDim, 6) == 0.2
    assert round(p.WallThickness, 6) == 0.008


def test_arbitrary_closed_channel():
    p = _profile("UPN 200")
    assert p.is_a() == "IfcArbitraryClosedProfileDef"
    assert len(p.OuterCurve.Points) == 9  # 8 sommets + fermeture


def test_rectangle_param():
    p = IfcWriter().profile_from_dims("R", {"kind": "RECT", "width": 0.3, "depth": 0.5})
    assert p.is_a() == "IfcRectangleProfileDef"
    assert round(p.XDim, 6) == 0.3
    assert round(p.YDim, 6) == 0.5


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for _fn in _tests:
        _fn()
        print("ok", _fn.__name__)
    print(f"\n{len(_tests)} tests OK")
