# -*- coding: utf-8 -*-
"""
test_section_geometry.py
Verifie section_geometry : parsing des sections Advance Design, contours de
profil, polygones ouverts (non-regression) et fallback.

Aucune dependance : `python test_section_geometry.py`. Compatible pytest si
present.
"""

import section_geometry as sg


def _signed_area(loop):
    s = 0.0
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


_PARSE_CASES = [
    ("IPE 300",       "I"),
    ("HEA 200",       "I"),
    ("HEB 340",       "I"),
    ("UPN 200",       "U"),
    ("UPE 240",       "U"),
    ("L 100X100X10",  "ANGLE"),
    ("CHS 168.3X10",  "CIRCLETUBE"),
    ("RHS 200X100X8", "RECTTUBE"),
    ("SHS 120X120X6", "RECTTUBE"),
    ("RCT 300X500",   "RECT"),
]


def test_parse_section_dims_kinds():
    for name, expected in _PARSE_CASES:
        dims = sg.parse_section_dims({"name": name, "materialName": "S275"})
        assert dims is not None, name
        assert dims["kind"] == expected, (name, dims["kind"], expected)


def test_parse_section_dims_unknown_returns_none():
    assert sg.parse_section_dims({"name": "PLOP 42"}) is None


_POLY_CASES = {
    "RECT":         {"kind": "RECT", "width": 0.3, "depth": 0.5},
    "CIRCLE":       {"kind": "CIRCLE", "radius": 0.1},
    "CIRCLETUBE":   {"kind": "CIRCLETUBE", "radius": 0.1, "thickness": 0.01},
    "RECTTUBE":     {"kind": "RECTTUBE", "width": 0.2, "depth": 0.1, "thickness": 0.008},
    "I":            sg.parse_section_dims({"name": "IPE 300", "materialName": "S275"}),
    "U":            sg.parse_section_dims({"name": "UPN 200", "materialName": "S275"}),
    "ANGLE":        sg.parse_section_dims({"name": "L 80X80X8", "materialName": "S275"}),
    "T":            {"kind": "T", "width": 0.2, "depth": 0.3, "web": 0.01, "flange": 0.015},
    "TDISSYMETRIC": {"kind": "TDISSYMETRIC", "depth": 0.3, "web": 0.02,
                     "left_width": 0.1, "left_thickness": 0.02, "left_offset": 0.1,
                     "right_width": 0.1, "right_thickness": 0.02, "right_offset": 0.1},
    "Z":            {"kind": "Z", "depth": 0.2, "top_flange_width": 0.06,
                     "bottom_flange_width": 0.06, "thickness": 0.003},
    "OMEGA":        {"kind": "OMEGA", "depth": 0.14, "width": 0.06,
                     "top_flange_width": 0.06, "thickness": 0.003},
    "SIGMA":        {"kind": "SIGMA", "depth": 0.32, "width": 0.08},
}
_HOLLOW = {"CIRCLETUBE", "RECTTUBE"}


def test_profile_polygon_structure():
    for label, dims in _POLY_CASES.items():
        p = sg.profile_polygon(dims)
        assert p is not None, label
        outer = p["outer"]
        assert len(outer) >= 3, label
        assert abs(_signed_area(outer)) > 1e-6, label
        assert outer[0] != outer[-1], (label, "boucle fermee implicitement attendue")
        assert len(p["holes"]) == (1 if label in _HOLLOW else 0), (label, len(p["holes"]))
        for hole in p["holes"]:
            assert 1e-7 < abs(_signed_area(hole)) < abs(_signed_area(outer)), label


def test_profile_polygon_circle_sides():
    assert sg.CIRCLE_SIDES == 12
    assert len(sg.profile_polygon({"kind": "CIRCLE", "radius": 0.1})["outer"]) == 12
    tube = sg.profile_polygon({"kind": "CIRCLETUBE", "radius": 0.1, "thickness": 0.01})
    assert len(tube["outer"]) == 12
    assert len(tube["holes"][0]) == 12


def test_profile_polygon_rect_matches_dims():
    p = sg.profile_polygon({"kind": "RECT", "width": 0.3, "depth": 0.5})
    xs = [x for x, _ in p["outer"]]
    ys = [y for _, y in p["outer"]]
    assert (min(xs), max(xs)) == (-0.15, 0.15)
    assert (min(ys), max(ys)) == (-0.25, 0.25)


def test_profile_polygon_none_and_fallback():
    assert sg.profile_polygon(None) is None
    fb = sg.profile_polygon({"kind": "NOPE", "width": 0.1, "depth": 0.2})
    assert len(fb["outer"]) == 4
    assert fb["holes"] == []


def test_open_section_polygons_golden():
    i = sg.i_section_polygon({"width": 0.15, "depth": 0.30, "web": 0.006, "flange": 0.010})
    assert len(i) == 12
    assert (min(x for x, _ in i), max(x for x, _ in i)) == (-0.075, 0.075)
    assert (min(y for _, y in i), max(y for _, y in i)) == (-0.15, 0.15)

    u = sg.u_section_polygon({"width": 0.075, "depth": 0.20, "web": 0.007, "flange": 0.011})
    assert len(u) == 8
    u_mirror = sg.u_section_polygon(
        {"width": 0.075, "depth": 0.20, "web": 0.007, "flange": 0.011}, open_left=False
    )
    assert u_mirror == [[-x, y] for x, y in u]

    a = sg.angle_section_polygon({"width": 0.08, "depth": 0.08, "thickness": 0.008})
    assert a == [[0.0, 0.0], [0.08, 0.0], [0.08, 0.008],
                 [0.008, 0.008], [0.008, 0.08], [0.0, 0.08]]


def test_default_linear_dims_fallback():
    assert sg.default_linear_dims({}, "column") == {"kind": "RECT", "width": 0.25, "depth": 0.25}
    assert sg.default_linear_dims({}, "beam") == {"kind": "RECT", "width": 0.12, "depth": 0.30}
    assert sg.default_linear_dims({"name": "IPE 300", "materialName": "S275"}, "beam")["kind"] == "I"


def test_excentration_offsets():
    dims = {"kind": "RECT", "width": 0.2, "depth": 0.4}
    assert sg.section_excentration_translation_local(
        {"sectionExcentration": {"option": "center_alignment"}}, dims
    ) == (0.0, 0.0)
    dy, dz = sg.section_excentration_translation_local(
        {"sectionExcentration": {"option": "droite_haut"}}, dims
    )
    assert (dy, dz) == (-0.1, 0.2)


def test_parse_combined_section():
    assert sg.parse_combined_section({"name": "IPE 300"}) is None
    d = sg.parse_combined_section({"name": "CS3 HEA160 HEA160", "type": "COMBINED"})
    assert d == {"code": "CS3", "primary_name": "HEA160", "secondary_name": "HEA160"}
    d = sg.parse_combined_section({"name": "CS 7 L80X80X8 L80X80X8"})
    assert d["code"] == "CS7"


_COMBINED_CASES = {
    "CS1 IPE200 IPE200": (12, 12),
    "CS2 IPE200 IPE200": (12, 12),
    "CS3 HEA160 HEA160": (12, 12),
    "CS4 IPE200 UPN160": (12, 8),
    "CS5 IPE200 UPN160": (12, 8),
    "CS6 UPN200 UPN200": (8, 8),
    "CS7 L80X80X8 L80X80X8": (6, 6),
}


def test_combined_member_polygons():
    for name, counts in _COMBINED_CASES.items():
        combo = sg.combined_member_polygons(sg.parse_combined_section({"name": name, "type": "COMBINED"}))
        assert combo is not None, name
        polys = combo["polygons"]
        assert tuple(len(p) for p in polys) == counts, (name, [len(p) for p in polys])
        for p in polys:
            assert abs(_signed_area(p)) > 1e-7, name
    # mauvaise combinaison de familles -> None
    assert sg.combined_member_polygons(
        sg.parse_combined_section({"name": "CS1 UPN200 UPN200", "type": "COMBINED"})
    ) is None


def test_parse_catalog_profile_dims():
    assert sg.parse_catalog_profile_dims("IPE 300")["kind"] == "I"
    assert sg.parse_catalog_profile_dims("UPN200")["kind"] == "U"
    assert sg.parse_catalog_profile_dims("L80X80X8")["kind"] == "ANGLE"
    assert sg.parse_catalog_profile_dims("QQQ") is None


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for _fn in _tests:
        _fn()
        print("ok", _fn.__name__)
    print(f"\n{len(_tests)} tests OK")
