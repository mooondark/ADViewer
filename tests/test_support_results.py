# -*- coding: utf-8 -*-
"""Resultats des appuis ponctuels : lignes affichees pour chaque famille,
quelle que soit la langue de l'interface."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ad_model_data as amd
import display_units
import viewer_config

NODE = {
    "resDisplacements": {"dx": 0.001, "dz": -0.002, "rx": 0.01},
    "resForces": {"fx": 1500.0, "mz": 2000.0},
    "resStresses": {"support": {"sx": 1.0e6}},
}


@pytest.fixture(autouse=True)
def _restore_language():
    display_units.reset()
    yield
    viewer_config.set_language("fr")
    display_units.reset()


@pytest.mark.parametrize("language", ["fr", "en"])
@pytest.mark.parametrize("family, result_type, names", [
    ("Déplacements", "displacement", ["dx", "dy", "dz", "d", "rx", "ry", "rz", "r"]),
    ("efforts", "forces", ["fx", "fy", "fz", "mx", "my", "mz"]),
    ("Stresses", "stresses", ["sx", "sy", "sz", "s"]),
])
def test_punctual_support_rows_in_every_language(monkeypatch, language, family, result_type, names):
    viewer_config.set_language(language)
    calls = []
    monkeypatch.setattr(amd, "get_results", lambda *args: calls.append(args) or [{"id": 7, "resNode": NODE}])
    rows = amd.read_punctual_support_results("h", 7, 3, family)
    assert calls == [("h", result_type, 3, [7])]
    assert [row["name"] for row in rows] == names


def test_force_row_is_formatted_in_display_units():
    rows = amd._build_analysis_rows("efforts", {"fx": 1500.0})
    assert rows[0] == {"name": "fx", "value": display_units.fmt(1500.0, "force")}


def test_unknown_family_gives_no_row(monkeypatch):
    monkeypatch.setattr(amd, "get_results", lambda *args: pytest.fail("pas d'appel API"))
    assert amd.read_punctual_support_results("h", 7, 3, "Torseurs") == []
