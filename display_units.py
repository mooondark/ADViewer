# -*- coding: utf-8 -*-
"""display_units.py
Registre central des unites d'affichage et de leur precision.
Sans dependance Qt ni vers les autres modules du projet.
Importe par ad_model_data, viewer_widget, main_window.
"""

import math

_DEG_PER_RAD = 180.0 / math.pi

_DECIMALS_MIN = 0
_DECIMALS_MAX = 6

# kind -> {units: {label: facteur depuis l'unite d'entree API}, default_unit, default_decimals}
_REGISTRY = {
    "length":         {"units": {"mm": 1000.0, "cm": 100.0, "m": 1.0},        "default_unit": "m",    "default_decimals": 2},
    "section_length": {"units": {"mm": 1000.0, "cm": 100.0, "m": 1.0},        "default_unit": "cm",   "default_decimals": 2},
    "force":          {"units": {"N": 1.0, "daN": 0.1, "kN": 1.0e-3},         "default_unit": "kN",   "default_decimals": 2},
    "moment":         {"units": {"N.m": 1.0, "daN.m": 0.1, "kN.m": 1.0e-3},   "default_unit": "kN.m", "default_decimals": 2},
    "stress":         {"units": {"Pa": 1.0, "kPa": 1.0e-3, "MPa": 1.0e-6},    "default_unit": "MPa",  "default_decimals": 2},
    "angle":          {"units": {"deg": _DEG_PER_RAD, "rad": 1.0},            "default_unit": "deg",  "default_decimals": 2},
    "area":           {"units": {"cm2": 1.0e4, "m2": 1.0},                    "default_unit": "m2",   "default_decimals": 2},
}

_DISPLAY_LABEL = {"cm2": "cm²", "m2": "m²", "deg": "°"}

_state = {}


def reset():
    _state.clear()
    for kind, desc in _REGISTRY.items():
        _state[kind] = {"unit": desc["default_unit"], "decimals": desc["default_decimals"]}


reset()


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def units_for(kind):
    return list(_REGISTRY[kind]["units"].keys())


def state_for(kind):
    s = _state[kind]
    return s["unit"], s["decimals"]


def set_unit(kind, unit_label):
    if kind in _REGISTRY and unit_label in _REGISTRY[kind]["units"]:
        _state[kind]["unit"] = unit_label


def set_decimals(kind, n):
    if kind not in _REGISTRY:
        return
    try:
        n = int(n)
    except (TypeError, ValueError):
        return
    _state[kind]["decimals"] = max(_DECIMALS_MIN, min(_DECIMALS_MAX, n))


def scale(kind):
    return _REGISTRY[kind]["units"][_state[kind]["unit"]]


def unit(kind):
    u = _state[kind]["unit"]
    return _DISPLAY_LABEL.get(u, u)


def decimals(kind):
    return _state[kind]["decimals"]


def conv(value_api, kind):
    v = _to_float(value_api)
    if v is None:
        return None
    return v * scale(kind)


def _format_number(value, dec):
    if dec >= 1 and value != 0.0 and abs(value) < 10.0 ** (-dec):
        return f"{value:.2e}"
    return f"{value:.{dec}f}"


def fmt(value_api, kind):
    v = conv(value_api, kind)
    if v is None:
        return "N/A"
    label = unit(kind)
    text = _format_number(v, decimals(kind))
    return f"{text} {label}" if label else text


def get_state_ini():
    out = {}
    for kind in _REGISTRY:
        out[f"{kind}_unit"] = _state[kind]["unit"]
        out[f"{kind}_decimals"] = str(_state[kind]["decimals"])
    return out


def load_state_ini(mapping):
    mapping = mapping or {}
    for kind in _REGISTRY:
        u = mapping.get(f"{kind}_unit")
        if u in _REGISTRY[kind]["units"]:
            _state[kind]["unit"] = u
        d = mapping.get(f"{kind}_decimals")
        try:
            _state[kind]["decimals"] = max(_DECIMALS_MIN, min(_DECIMALS_MAX, int(d)))
        except (TypeError, ValueError):
            pass


if __name__ == "__main__":
    reset()
    assert fmt(1234.0, "force") == "1.23 kN", fmt(1234.0, "force")
    assert fmt(0.05, "section_length") == "5.00 cm", fmt(0.05, "section_length")
    assert fmt(1_000_000.0, "stress") == "1.00 MPa", fmt(1_000_000.0, "stress")
    assert fmt(math.pi, "angle") == "180.00 °", fmt(math.pi, "angle")
    assert fmt(2.0, "length") == "2.00 m", fmt(2.0, "length")
    assert fmt(4.0, "area") == "4.00 m²", fmt(4.0, "area")
    assert fmt(None, "force") == "N/A"
    assert fmt("x", "force") == "N/A"

    set_unit("force", "N")
    assert fmt(1234.0, "force") == "1234.00 N", fmt(1234.0, "force")
    set_unit("length", "mm")
    assert fmt(2.0, "length") == "2000.00 mm", fmt(2.0, "length")
    set_decimals("force", 0)
    assert fmt(1234.0, "force") == "1234 N", fmt(1234.0, "force")
    set_decimals("force", 99)
    assert state_for("force")[1] == 6
    set_decimals("force", -3)
    assert state_for("force")[1] == 0

    reset()
    assert fmt(1.0, "force") == "1.00e-03 kN", fmt(1.0, "force")  # 1 N -> 0.001 kN -> scientifique

    reset()
    ini = get_state_ini()
    assert ini["length_unit"] == "m" and ini["length_decimals"] == "2", ini
    load_state_ini({"length_unit": "cm", "length_decimals": "1"})
    assert state_for("length") == ("cm", 1), state_for("length")
    load_state_ini({"length_unit": "bogus", "length_decimals": "abc"})
    assert state_for("length") == ("cm", 1), state_for("length")  # invalides ignores
    reset()
    load_state_ini(get_state_ini())
    assert state_for("force") == ("kN", 2), state_for("force")  # round-trip stable
    assert conv(None, "length") is None
    assert abs(conv(2.0, "length") - 2.0) < 1e-9

    print("display_units self-check OK")
