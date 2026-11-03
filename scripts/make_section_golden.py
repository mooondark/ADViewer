"""Corpus de sections Advance Design et sorties de reference de parse_section_dims
et profile_bounds_from_dims (code actuel), ecrits dans tests/data/section_dims_golden.json."""
import itertools
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from section_geometry import parse_section_dims, profile_bounds_from_dims

NAMES = [
    "", "IPE 200", "IPE200", "IPN 160", "HEA 300", "HEB 100", "HEM 200", "HEA 260,5",
    "UPE 200", "UPN 120", "UNP 100", "UAP 150", "U 100", "U", "CHANNEL 10 4", "CHANNEL",
    "L 50X50X5", "L50X30X4", "L 10", "L", "ANGLE 10 8 1", "ANGLE 10", "ANGLE 10 8",
    "V 32 8 8 4.5 1.6 4 0.3 0.2", "V 32", "V",
    "W 14 6 6 0.2 0.2", "W14", "W 14 6",
    "Z20X6X6X0.2X1X1X45X45 0.3", "Z20X6X6X0.2X1X1 0.3", "Z20X6X5X0.2 0.25", "Z20X6X5X0.2",
    "Z 20", "Z", "Z20X6X5 0.2",
    "RCT 20 10", "RCT", "RHS 100 50 5", "RHS 100 50", "RHS", "SHS 80", "SHSH 80 80 4",
    "CHS 100 5", "CHS 100", "CHS",
    "T 30 1 20 1.5", "T 30", "T",
    "TUBE RECT 20 10 1", "TUBE RECT 20", "TUBE RECT", "TUBE CIRC 20 1", "TUBE CIRC",
    "ROND 20", "Ø 16", "DIAM 12", "DIAM TUBE 12", "CIRC 30", "CIRC",
    "RECT 30 20", "RECT 30", "SQUARE 25", "RECT", "POUTRE 30X50", "BETON",
]
TYPES = [
    "", "ST_CIRCULAR", "STCIRCULAR", "CIRCULAR", "ST_ANGLE", "ST_UNEQUAL_ANGLE", "ANGLE",
    "ST_RECTANGULAR_TUBE", "ST_SQUARE_TUBE", "ST_CIRCULAR_TUBE", "ST_T", "ST_U",
    "ST_RECTANGULAR", "ST_SQUARE", "T_DISSYMETRIC", "I_SYMETRIC", "IASYMETRIC", "OMEGA",
    "ZED", "SIGMA", "CIRCULARTUBE",
]
FAMILIES = ["", "V", "W", "Z", "RHSC", "RHSH", "SHSC", "SHSH", "CHSC", "CHSH", "RCT", "IPE", "AUTRE"]
MATERIALS = ["", "S235", "ACIER", "C25/30"]
NUMBERS = ["", "20", "20 10", "20 10 1", "20 10 1 2 3", "30 1 20 1.5 4 2 1 5", "32 8 8 4.5 1.6 4 0.3 0.2 9"]


def cases():
    seen = set()

    def add(sec):
        key = json.dumps(sec, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            yield sec

    for name, material in itertools.product(NAMES, MATERIALS):
        yield from add({"name": name, "materialName": material})
    for sec_type, nums, material in itertools.product(TYPES, NUMBERS, ["", "S235"]):
        yield from add({"name": nums, "type": sec_type, "materialName": material})
    for family, nums in itertools.product(FAMILIES, NUMBERS):
        yield from add({"name": nums, "familyCode": family})
        yield from add({"name": "", "familyCode": family, "catalogName": nums})
    yield from add({"name": "IPE 200", "material": "S355"})
    yield from add({})
    yield from add({"name": None, "type": None, "familyCode": None, "catalogName": None, "materialName": None})


EXTRA_DIMS = [
    None, {}, {"kind": "PIPE", "radius": 0.1}, {"kind": "CHS", "radius": 0}, {"kind": "CHS", "width": 0.2, "depth": 0.2},
    {"kind": "RHS", "width": 0.2, "depth": 0.1}, {"kind": "SHS", "width": 0.1, "depth": 0.1}, {"kind": "C", "width": 0.1, "depth": 0.2},
    {"kind": "T_DISSYM", "width": 0.3, "depth": 0.5}, {"kind": "RECT", "width": 0, "depth": 0.5}, {"kind": "rect", "width": 0.2, "depth": 0.5},
    {"kind": "OMEGA", "width": 0.06, "depth": 0.14}, {"kind": "OMEGA", "width": 0.06, "depth": 0.14, "top_flange_width": 0.04, "overall_width": 0},
    {"kind": "SIGMA", "width": 0.08, "depth": 0.3}, {"kind": "SIGMA", "width": 0.01, "depth": 0.3, "web_offset": 0.02, "thickness": 0.003, "return_lip": 0.0},
    {"kind": "ZED", "depth": 0.2}, {"kind": "Z", "depth": None, "width": None}, {"kind": None}, {"kind": "INCONNU", "width": 1, "depth": 1},
]


def main():
    section_cases = [{"sec": sec, "dims": parse_section_dims(sec)} for sec in cases()]
    dims_inputs = [c["dims"] for c in section_cases] + EXTRA_DIMS
    unique = []
    seen = set()
    for dims in dims_inputs:
        key = json.dumps(dims, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(dims)
    bounds_cases = [{"dims": dims, "bounds": profile_bounds_from_dims(dims)} for dims in unique]
    out = os.path.join(ROOT, "tests", "data", "section_dims_golden.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"sections": section_cases, "bounds": bounds_cases}, fh, ensure_ascii=False, indent=0)
    print(len(section_cases), "sections,", len(bounds_cases), "dims,", os.path.getsize(out) // 1024, "Ko")


if __name__ == "__main__":
    main()
