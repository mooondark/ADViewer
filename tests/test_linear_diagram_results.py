# -*- coding: utf-8 -*-
"""GetResults sur un element filaire : l'id renvoye ne correspond pas a l'EID
demande, et la reponse "displacement" melange des entrees ResNode et une seule
entree ResElementLinear (qui porte resDiagrams). On doit retrouver cette
derniere par $type, pas par id ni par position."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd

RES_NODE = {
    "$type": "ResNode",
    "resDisplacements": {"dx": 0.001, "dy": 0.0, "dz": -0.0002, "d": 0.001},
    "id": {"value": 12},
}

RES_ELEMENT_LINEAR = {
    "$type": "ResElementLinear",
    "resNodes": [RES_NODE],
    "resDiagrams": {
        "resDisplacements": {
            "dx": [{"abscissa": 0, "value": 0.0019}, {"abscissa": 8, "value": 0.0018}],
            "dy": [], "dz": [], "d": [],
        },
        "resForces": {"fx": [], "fy": [], "fz": [], "mx": [], "my": [], "mz": []},
        "resStresses": {"sxxMin": [], "sxxMax": [], "sxyMin": [], "sxyMax": [], "sxzMin": [], "sxzMax": [], "sv": []},
    },
    "id": {"value": 79891},
}


def test_extract_element_linear_result_item_skips_leading_nodes():
    payloads = [RES_NODE, RES_NODE, RES_ELEMENT_LINEAR]
    assert amd._extract_element_linear_result_item(payloads) is RES_ELEMENT_LINEAR


def test_extract_element_linear_result_item_fallback_when_no_element():
    payloads = [RES_NODE]
    assert amd._extract_element_linear_result_item(payloads) is RES_NODE


def test_extract_element_linear_result_item_empty_payloads():
    assert amd._extract_element_linear_result_item([]) == {}


def test_read_linear_element_diagram_results_finds_displacement_series():
    calls = []
    original = amd.get_results
    amd.get_results = lambda host, result_type, case_id, eids: calls.append(result_type) or [
        RES_NODE, RES_NODE, RES_ELEMENT_LINEAR
    ]
    try:
        payload = amd.read_linear_element_diagram_results("host", 7229, 1, "deplacements", "dx")
    finally:
        amd.get_results = original
    assert payload["series"] == [{"abscissa": 0.0, "value": 0.19}, {"abscissa": 8.0, "value": 0.18}]
    assert payload["source_found"] is True
    assert calls == ["displacement"], "ne doit interroger que displacement, pas tomber en cascade sur forces/stresses"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}()")
    print(f"OK {len(tests)} tests")
