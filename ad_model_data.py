# -*- coding: utf-8 -*-
"""
ad_model_data.py
Pipeline d'extraction du modèle, lecture des résultats, session de projet
et workers QThread pour le Viewer 3D Advance Design.

Dépend de :
  - viewer_config (constantes, i18n, exceptions, helpers)
  - ad_api_client (communication HTTP avec l'API Advance Design)
"""

import math
import requests
import traceback
from typing import Any, Optional, TypedDict
from PySide6.QtCore import QThread, Signal

from viewer_config import (
    tr_ui, tr_log,
    ApiUnavailableError, ProjectAlreadyOpenError,
    normalize_windows_path,
    PUNCTUAL_SUPPORT_TYPES, LINEAR_SUPPORT_TYPES, PLANAR_SUPPORT_TYPES,
    PLANAR_ELEMENT_TYPE_LABELS, LINEAR_BEAM_TYPE_LABELS,
    LINEAR_LOAD_COLOR,
    PLANAR_LOAD_COLOR,
)
from ad_api_client import *

def _get_username(obj: dict) -> str:
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("userName") or obj.get("UserName") or "").strip()


class ResultsCaseEntry(TypedDict, total=False):
    kind: str
    eid: Optional[int]
    label: str


class ModelDataDict(TypedDict, total=False):
    lines: list
    line_properties: list
    line_eids: list
    planars: list
    planar_eids: list
    planar_properties: list
    load_areas: list
    linear_takeoff: list
    linear_material_takeoff: list
    planar_takeoff: list
    planar_material_takeoff: list
    load_area_takeoff: list
    all_material_by_eid: dict
    punctual_supports: list
    punctual_support_eids: list
    punctual_support_properties: list
    linear_supports: list
    linear_support_eids: list
    linear_support_properties: list
    planar_supports: list
    planar_support_eids: list
    planar_support_properties: list
    linear_ids_count: int
    planar_ids_count: int
    load_area_ids_count: int
    punctual_support_ids_count: int
    linear_support_ids_count: int
    planar_support_ids_count: int
    linear_count: int
    planar_count: int
    load_area_count: int
    punctual_support_count: int
    linear_support_count: int
    planar_support_count: int
    openings_count: int
    materials_resolved_count: int
    materials_eids_count: int
    linear_sections_resolved_count: int
    linear_section_eids_count: int
    normalized_path: str
    results_cases_combinations: list
    project_closed: bool
    project_kept_open: bool
    has_analysis_results: bool
    fem_nodes: list       # liste de (x, y, z) — positions des nœuds FEM
    fem_by_eid: dict      # dict {eid: [[n0,n1,n2], ...]} — faces par EID d'élément
    punctual_loads: list  # liste de dicts {pos, fx, fy, fz, load_case_eid, load_case_label}
    punctual_load_cases: list  # liste de dicts {eid, label} — cas de charge uniques
    linear_loads: list   # liste de dicts {pt_start, pt_end, fx, fy, fz, mx, my, mz, coeff1, coeff2, user_id, load_case_eid, load_case_label}
    linear_load_cases: list  # liste de dicts {eid, label} — cas de charge uniques
    planar_loads: list   # liste de dicts {pts, fx, fy, fz, coeff1, coeff2, coeff3, user_id, load_case_eid, load_case_label}
    planar_load_cases: list  # liste de dicts {eid, label} — cas de charge uniques


def normalize_results_case_entry(kind: str, eid, label: str) -> ResultsCaseEntry:
    value = int(eid) if eid is not None else None
    return {
        "kind": str(kind or "").strip(),
        "eid": value,
        "id": value,
        "label": str(label or "").strip(),
    }


def build_model_data(payload: dict) -> ModelDataDict:
    data = dict(payload or {})
    list_keys = [
        "lines", "line_properties", "line_eids", "planars", "planar_eids", "planar_properties", "load_areas",
        "linear_takeoff", "linear_material_takeoff", "planar_takeoff", "planar_material_takeoff",
        "punctual_supports", "punctual_support_eids", "punctual_support_properties",
        "linear_supports", "linear_support_eids", "linear_support_properties",
        "planar_supports", "planar_support_eids", "planar_support_properties",
        "results_cases_combinations",
        "fem_nodes",
        "punctual_loads",
        "punctual_load_cases",
        "linear_loads",
        "linear_load_cases",
        "planar_loads",
        "planar_load_cases",
    ]
    for key in list_keys:
        value = data.get(key)
        data[key] = list(value) if isinstance(value, (list, tuple)) else []
    data["all_material_by_eid"] = dict(data.get("all_material_by_eid") or {})
    data["fem_by_eid"] = dict(data.get("fem_by_eid") or {})
    data["load_area_takeoff"] = data.get("load_area_takeoff") if data.get("load_area_takeoff") is not None else []
    data["normalized_path"] = normalize_windows_path(str(data.get("normalized_path") or "")) if data.get("normalized_path") else ""
    data["project_closed"] = bool(data.get("project_closed"))
    data["project_kept_open"] = bool(data.get("project_kept_open"))
    data["has_analysis_results"] = bool(data.get("has_analysis_results"))
    int_keys = [
        "linear_ids_count", "planar_ids_count", "load_area_ids_count", "punctual_support_ids_count",
        "linear_support_ids_count", "planar_support_ids_count", "linear_count", "planar_count",
        "load_area_count", "punctual_support_count", "linear_support_count", "planar_support_count",
        "openings_count", "materials_resolved_count", "materials_eids_count",
        "linear_sections_resolved_count", "linear_section_eids_count",
        "punctual_load_ids_count", "punctual_load_count",
        "linear_load_ids_count", "linear_load_count",
        "planar_load_ids_count", "planar_load_count",
    ]
    for key in int_keys:
        try:
            data[key] = int(data.get(key, 0) or 0)
        except Exception:
            data[key] = 0
    return data


def _build_results_cases_combinations(load_case_ids: list, load_case_objects: list, combination_ids: list, combination_objects: list) -> list:
    entries = []

    for eid, obj in zip(load_case_ids or [], load_case_objects or []):
        if not isinstance(obj, dict):
            continue
        user_id = obj.get("userID")
        user_name = _get_username(obj)
        if user_id in (None, "") and not user_name:
            continue
        label_left = str(user_id).strip() if user_id not in (None, "") else str(eid)
        label_right = user_name or str(obj.get("name") or "").strip() or str(eid)
        entries.append(normalize_results_case_entry(
            "load_case",
            eid,
            f"{label_left} : {label_right}",
        ))

    for eid, obj in zip(combination_ids or [], combination_objects or []):
        if not isinstance(obj, dict):
            continue
        comb_id = obj.get("idComb")
        user_name = _get_username(obj)
        if comb_id in (None, "") and not user_name:
            continue
        label_left = str(comb_id).strip() if comb_id not in (None, "") else str(eid)
        label_right = user_name or str(eid)
        entries.append(normalize_results_case_entry(
            "combination",
            eid,
            f"{label_left} : {label_right}",
        ))

    return entries


def _has_non_empty_results_data(data) -> bool:
    if data is None:
        return False
    if isinstance(data, dict):
        return bool(data)
    if isinstance(data, (list, tuple, set)):
        for item in data:
            if _has_non_empty_results_data(item):
                return True
        return False
    return True


def get_first_load_case_eid(host: str):
    ids = get_informational_ids(host, "LoadCase")
    return ids[0] if ids else None


def probe_results_for_element(host: str, element_eid: int, case_eid: int) -> bool:
    try:
        resp = requests.post(
            f"{host}/api/Model/analysis/GetResults",
            params={"eResType": "forces", "IDAnalysisCase": int(case_eid)},
            json=[int(element_eid)],
            timeout=30
        )
    except requests.exceptions.RequestException:
        return False

    try:
        payload = resp.json()
    except Exception:
        return False

    if resp.status_code != 200:
        return False

    details = payload.get("details") or {}
    if details.get("hasErrors"):
        return False

    return _has_non_empty_results_data(payload.get("data"))


def diagnose_results_availability(host: str) -> bool:
    case_eid = get_first_load_case_eid(host)
    if case_eid is None:
        return False

    for type_list in (PUNCTUAL_SUPPORT_TYPES, LINEAR_SUPPORT_TYPES, PLANAR_SUPPORT_TYPES):
        found_ids = []
        for support_type in type_list:
            found_ids = get_element_ids(host, support_type)
            if found_ids:
                break
        if not found_ids:
            continue
        try:
            if probe_results_for_element(host, found_ids[0], case_eid):
                return True
        except Exception:
            pass
    return False


def _resolve_name_map_by_eids(host: str, eids: set, fetcher) -> dict:
    if not eids:
        return {}
    ids = sorted(int(eid) for eid in eids if eid is not None)
    try:
        items = fetcher(host, ids)
    except Exception:
        return {}
    result = {}
    for eid, item in zip(ids, items):
        if isinstance(item, dict):
            name = str(item.get("name", "") or "").strip()
            if name:
                result[eid] = name
    return result


def _resolve_object_map_by_eids(host: str, eids: set, fetcher) -> dict:
    if not eids:
        return {}
    ids = sorted(int(eid) for eid in eids if eid is not None)
    try:
        items = fetcher(host, ids)
    except Exception:
        return {}
    return {
        eid: item
        for eid, item in zip(ids, items)
        if isinstance(item, dict)
    }


def _extract_ref_eid(el: dict, key: str):
    ref = el.get(key)
    if isinstance(ref, dict):
        value = ref.get("value")
    else:
        value = ref
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _normalize_enum_token(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.split(".")[-1]
    text = text.split("::")[-1]
    return text.strip().lower()


def _collect_string_values(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for value in obj.values():
            _collect_string_values(value, out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _collect_string_values(value, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def _find_linear_beam_type_label(el: dict) -> str:
    token_map = {k.lower(): v for k, v in LINEAR_BEAM_TYPE_LABELS.items()}

    linear_element_type = _normalize_enum_token(_dict_get_ci(el, "linearElementType"))
    general_beam_type = _normalize_enum_token(_dict_get_ci(el, "generalBeamType"))

    if linear_element_type == "elinearelementfemtypecompositebeam":
        composite_map = {
            "bar":                    LINEAR_BEAM_TYPE_LABELS["CompositeBeamSimpleBeam"],
            "beamwstandardbending":   LINEAR_BEAM_TYPE_LABELS["CompositeBeamSbeam"],
            "compositebeamsimplebeam": LINEAR_BEAM_TYPE_LABELS["CompositeBeamSimpleBeam"],
            "compositebeamsbeam":     LINEAR_BEAM_TYPE_LABELS["CompositeBeamSbeam"],
        }
        if general_beam_type in composite_map:
            return composite_map[general_beam_type]
        for key in ("compositeBeamType", "beamType", "linearElementSubType", "typeName", "className", "$type"):
            token = _normalize_enum_token(_dict_get_ci(el, key))
            if token in composite_map:
                return composite_map[token]
        for raw in _collect_string_values(el, []):
            token = _normalize_enum_token(raw)
            if token in composite_map:
                return composite_map[token]
        return tr_ui("label_element_linear")

    if linear_element_type == "elinearelementfemtypegeneral":
        if general_beam_type in token_map:
            return token_map[general_beam_type]
        for key in ("beamType", "linearElementSubType", "typeName", "className", "$type"):
            token = _normalize_enum_token(_dict_get_ci(el, key))
            if token in token_map:
                return token_map[token]

    candidates = []
    for key in (
        "generalBeamType", "compositeBeamType", "beamType", "linearElementSubType",
        "linearElementType", "typeName", "className", "$type"
    ):
        value = _dict_get_ci(el, key)
        if isinstance(value, str):
            candidates.append(value)
    candidates.extend(_collect_string_values(el, []))
    for raw in candidates:
        token = _normalize_enum_token(raw)
        if token in token_map:
            return token_map[token]
    for raw in candidates:
        token = _normalize_enum_token(raw)
        for key, label in token_map.items():
            if token.endswith(key):
                return label
    return tr_ui("label_element_linear")


def _radians_to_degrees(value):
    try:
        return math.degrees(float(value))
    except Exception:
        return None


def _format_angle_degrees(value) -> str:
    angle_deg = _radians_to_degrees(value)
    if angle_deg is None:
        return "N/A"
    return f"{angle_deg:.6g} °"


def _extract_release_flags(connection) -> dict:
    if not isinstance(connection, dict):
        return {"TX": False, "TY": False, "TZ": False, "RX": False, "RY": False, "RZ": False}
    return {
        "TX": _to_bool(_dict_get_ci(connection, "relaxationTx", "tx", "TX", default=False)),
        "TY": _to_bool(_dict_get_ci(connection, "relaxationTy", "ty", "TY", default=False)),
        "TZ": _to_bool(_dict_get_ci(connection, "relaxationTz", "tz", "TZ", default=False)),
        "RX": _to_bool(_dict_get_ci(connection, "relaxationRx", "rx", "RX", default=False)),
        "RY": _to_bool(_dict_get_ci(connection, "relaxationRy", "ry", "RY", default=False)),
        "RZ": _to_bool(_dict_get_ci(connection, "relaxationRz", "rz", "RZ", default=False)),
    }


def _format_release_connection(connection) -> str:
    flags = _extract_release_flags(connection)
    rows = [label for label, checked in flags.items() if checked]
    return ", ".join(rows) if rows else tr_ui("label_no_release")


def _contains_true_value(obj) -> bool:
    if isinstance(obj, bool):
        return obj is True
    if isinstance(obj, dict):
        return any(_contains_true_value(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_contains_true_value(v) for v in obj)
    return False


def _extract_user_id(el: dict):
    if not isinstance(el, dict):
        return None
    value = _dict_get_ci(el, "userID", "userid", "userId")
    if isinstance(value, dict):
        value = _dict_get_ci(value, "value", default=value)
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except Exception:
        text = str(value or "").strip()
        return text or None


def _label_with_user_id(base_label: str, user_id) -> str:
    label = str(base_label or "").strip() or tr_ui("label_element_generic")
    if user_id is None or str(user_id).strip() == "":
        return label
    return f"{label} n°{user_id}"


def extract_linear_element_properties(el: dict, material_by_eid: dict, section_by_eid: dict):
    if not isinstance(el, dict):
        return {
            "kind": "linear_element",
            "type_label": tr_ui("prop_linear_element"),
            "rows": [(tr_ui("prop_material_na"), "N/A"), (tr_ui("prop_section_na"), "N/A")],
            "start_relaxation": {"TX": False, "TY": False, "TZ": False, "RX": False, "RY": False, "RZ": False},
            "end_relaxation": {"TX": False, "TY": False, "TZ": False, "RX": False, "RY": False, "RZ": False},
        }

    material_eid = _extract_ref_eid(el, "material")
    section_eid = _extract_ref_eid(el, "section")
    material = material_by_eid.get(material_eid, "N/A") if material_eid is not None else "N/A"
    section = section_by_eid.get(section_eid, "N/A") if section_eid is not None else "N/A"
    orientation = _format_angle_degrees(_dict_get_ci(el, "sectionOrientationAngle"))

    relaxation = _dict_get_ci(el, "relaxationTotale")
    start_relaxation = _extract_release_flags(_dict_get_ci(relaxation, "startBoundaryConnection"))
    end_relaxation = _extract_release_flags(_dict_get_ci(relaxation, "endBoundaryConnection"))

    rows = [
        (tr_ui("prop_material"), material),
        (tr_ui("prop_section"), section),
        (tr_ui("prop_orientation"), orientation),
    ]

    relaxation_elastique = _dict_get_ci(el, "relaxationElastique")
    if _contains_true_value(relaxation_elastique):
        rows.append((tr_ui("prop_relaxation_elastic"), tr_ui("prop_relaxation_elastic_present")))

    type_label = _find_linear_beam_type_label(el)
    user_id = _extract_user_id(el)
    start_pt = _point3d_from_api(_dict_get_ci(el, "geomPtStart"))
    end_pt = _point3d_from_api(_dict_get_ci(el, "geomPtEnd"))
    orientation_angle = _dict_get_ci(el, "sectionOrientationAngle")
    local_axes = _build_ad_local_axes(start_pt, end_pt, orientation_angle) if start_pt is not None and end_pt is not None else None

    return {
        "kind": "linear_element",
        "type_label": _label_with_user_id(type_label, user_id),
        "base_type_label": type_label,
        "user_id": user_id,
        "rows": rows,
        "start_relaxation": start_relaxation,
        "end_relaxation": end_relaxation,
        "material": material,
        "section": section,
        "material_eid": material_eid,
        "section_eid": section_eid,
        "section_orientation_angle_deg": float(orientation_angle or 0.0) if orientation_angle not in (None, "") else 0.0,
        "local_axes": local_axes or {},
    }


def _point3d_from_api(pt):
    if not isinstance(pt, dict):
        return None
    try:
        return (float(pt.get("x", 0.0)), float(pt.get("y", 0.0)), float(pt.get("z", 0.0)))
    except Exception:
        return None

def _normalize_vector3(vec):
    try:
        x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
    except Exception:
        return None
    norm = math.sqrt(x * x + y * y + z * z)
    if norm <= 1e-12:
        return None
    return (x / norm, y / norm, z / norm)


def _cross_vector3(a, b):
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _dot_vector3(a, b) -> float:
    return float(a[0]) * float(b[0]) + float(a[1]) * float(b[1]) + float(a[2]) * float(b[2])


def _rotate_vector_around_axis(vec, axis, angle_rad: float):
    u = _normalize_vector3(axis)
    v = _normalize_vector3(vec)
    if u is None or v is None:
        return None
    c = math.cos(float(angle_rad))
    s = math.sin(float(angle_rad))
    uxv = _cross_vector3(u, v)
    udotv = _dot_vector3(u, v)
    return (
        v[0] * c + uxv[0] * s + u[0] * udotv * (1.0 - c),
        v[1] * c + uxv[1] * s + u[1] * udotv * (1.0 - c),
        v[2] * c + uxv[2] * s + u[2] * udotv * (1.0 - c),
    )


def _build_ad_local_axes(start_pt, end_pt, section_orientation_angle_deg=0.0):
    x_local = _normalize_vector3((
        float(end_pt[0]) - float(start_pt[0]),
        float(end_pt[1]) - float(start_pt[1]),
        float(end_pt[2]) - float(start_pt[2]),
    ))
    if x_local is None:
        return None

    global_z = (0.0, 0.0, 1.0)
    global_y = (0.0, 1.0, 0.0)
    helper = global_z if abs(_dot_vector3(x_local, global_z)) < 0.999 else global_y

    z_local_0 = _normalize_vector3(_cross_vector3(x_local, helper))
    if z_local_0 is None:
        helper = global_y if helper == global_z else global_z
        z_local_0 = _normalize_vector3(_cross_vector3(x_local, helper))
    if z_local_0 is None:
        return None

    y_local_0 = _normalize_vector3(_cross_vector3(z_local_0, x_local))
    if y_local_0 is None:
        return None

    angle_rad = math.radians(float(section_orientation_angle_deg or 0.0))
    y_local = _rotate_vector_around_axis(y_local_0, x_local, angle_rad) if abs(angle_rad) > 1e-12 else y_local_0
    z_local = _rotate_vector_around_axis(z_local_0, x_local, angle_rad) if abs(angle_rad) > 1e-12 else z_local_0
    y_local = _normalize_vector3(y_local)
    z_local = _normalize_vector3(z_local)
    if y_local is None or z_local is None:
        return None

    return {
        "x": x_local,
        "y": y_local,
        "z": z_local,
    }


def _distance_3d(p1, p2) -> float:
    return math.sqrt(
        (float(p2[0]) - float(p1[0])) ** 2 +
        (float(p2[1]) - float(p1[1])) ** 2 +
        (float(p2[2]) - float(p1[2])) ** 2
    )


def _polygon_area_3d(points) -> float:
    pts = [p for p in (points or []) if p is not None]
    if len(pts) < 3:
        return 0.0
    area_x = 0.0
    area_y = 0.0
    area_z = 0.0
    count = len(pts)
    for i in range(count):
        x1, y1, z1 = pts[i]
        x2, y2, z2 = pts[(i + 1) % count]
        area_x += y1 * z2 - z1 * y2
        area_y += z1 * x2 - x1 * z2
        area_z += x1 * y2 - y1 * x2
    return 0.5 * math.sqrt(area_x * area_x + area_y * area_y + area_z * area_z)


def _format_area_m2(value) -> str:
    try:
        return f"{float(value):.6g} m²"
    except Exception:
        return "N/A"


def _format_numeric(value) -> str:
    try:
        return f"{float(value):.6g}"
    except Exception:
        return "N/A"


def _format_fixed_unit(value, unit: str, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f} {unit}"
    except Exception:
        return "N/A"


def _format_length_cm_fixed(value, decimals: int = 2) -> str:
    try:
        return f"{float(value) * 100.0:.{decimals}f} cm"
    except Exception:
        return "N/A"


def _extract_material_density(material: dict):
    if not isinstance(material, dict):
        return None
    for key in ("ro", "rho", "massDensity", "density", "unitWeight", "ms", "Ms"):
        value = _dict_get_ci(material, key)
        try:
            return float(value)
        except Exception:
            continue
    return None


def _build_linear_length_takeoff(linear_elements: list, key_fn) -> list:
    """Metré de longueur des filaires, groupe selon key_fn(el) -> str."""
    totals: dict = {}
    for el in linear_elements or []:
        p1 = _point3d_from_api(_dict_get_ci(el, "geomPtStart"))
        p2 = _point3d_from_api(_dict_get_ci(el, "geomPtEnd"))
        if p1 is None or p2 is None:
            continue
        key = key_fn(el)
        totals[key] = totals.get(key, 0.0) + _distance_3d(p1, p2)
    return [
        {"name": name, "value": value, "value_text": _format_fixed_unit(value, "m", 2)}
        for name, value in sorted(totals.items(), key=lambda item: str(item[0]).lower())
    ]


def _build_linear_takeoff(linear_elements: list, section_by_eid: dict) -> list:
    def key_fn(el):
        eid = _extract_ref_eid(el, "section")
        return section_by_eid.get(eid, "N/A") if eid is not None else "N/A"
    return _build_linear_length_takeoff(linear_elements, key_fn)


def _build_linear_material_takeoff(linear_elements: list, material_by_eid: dict) -> list:
    def key_fn(el):
        eid = _extract_ref_eid(el, "material")
        return material_by_eid.get(eid, "N/A") if eid is not None else "N/A"
    return _build_linear_length_takeoff(linear_elements, key_fn)


def _compute_planar_net_area(el: dict):
    """Calcule l'aire nette d'un element surfacique (exterieur moins ouvertures).

    Retourne None si l'element n'a pas assez de sommets, sinon un float >= 0.
    """
    outer = [_point3d_from_api(pt) for pt in (_dict_get_ci(el, "geomPtsList") or [])]
    outer = [pt for pt in outer if pt is not None]
    if len(outer) < 3:
        return None
    area = _polygon_area_3d(outer)
    for opening in (_dict_get_ci(el, "openings") or []):
        hole = [_point3d_from_api(pt) for pt in (opening or [])]
        hole = [pt for pt in hole if pt is not None]
        if len(hole) >= 3:
            area -= _polygon_area_3d(hole)
    return max(0.0, area)


def _build_planar_takeoff(planar_elements: list) -> list:
    totals: dict = {}
    for el in planar_elements or []:
        area = _compute_planar_net_area(el)
        if area is None:
            continue
        thickness_value = _dict_get_ci(el, "thicknessIn1stVertex", "thickness")
        sort_value = None
        try:
            sort_value = float(thickness_value) * 100.0
        except Exception:
            pass
        thickness_text = _format_length_cm_fixed(thickness_value, 2)
        bucket = totals.setdefault(thickness_text, {"sort_value": sort_value, "area": 0.0})
        if bucket.get("sort_value") is None and sort_value is not None:
            bucket["sort_value"] = sort_value
        bucket["area"] += area
    ordered = sorted(
        totals.items(),
        key=lambda item: (float("inf") if item[1].get("sort_value") is None else item[1].get("sort_value"), str(item[0]).lower())
    )
    return [
        {"name": name, "area": data["area"], "area_text": _format_fixed_unit(data["area"], "m\u00b2", 2)}
        for name, data in ordered
    ]


def _build_planar_material_takeoff(planar_elements: list, material_by_eid: dict) -> list:
    totals: dict = {}
    for el in planar_elements or []:
        area = _compute_planar_net_area(el)
        if area is None:
            continue
        material_eid = _extract_ref_eid(el, "material")
        material_name = material_by_eid.get(material_eid, "N/A") if material_eid is not None else "N/A"
        totals[material_name] = totals.get(material_name, 0.0) + area
    return [
        {"name": name, "area": area, "area_text": _format_fixed_unit(area, "m\u00b2", 2)}
        for name, area in sorted(totals.items(), key=lambda item: str(item[0]).lower())
    ]


def _build_load_area_takeoff(load_area_elements: list):
    total_area = 0.0
    found_any = False
    for el in load_area_elements or []:
        outer = [_point3d_from_api(pt) for pt in (_dict_get_ci(el, "geomPtsList") or [])]
        outer = [pt for pt in outer if pt is not None]
        if len(outer) < 3:
            continue
        found_any = True
        total_area += _polygon_area_3d(outer)
    return total_area if found_any else None


def _find_planar_type_label(el: dict) -> str:
    token_map = {k.lower(): v for k, v in PLANAR_ELEMENT_TYPE_LABELS.items()}
    candidates = []
    for key in ("elementType", "type", "typeName", "className", "$type"):
        value = _dict_get_ci(el, key)
        if isinstance(value, str):
            candidates.append(value)
    candidates.extend(_collect_string_values(el, []))
    for raw in candidates:
        token = _normalize_enum_token(raw)
        if token in token_map:
            return token_map[token]
    return tr_ui("label_element_planar")


def _format_length_cm(value) -> str:
    try:
        return f"{float(value) * 100.0:.6g} cm"
    except Exception:
        return "N/A"


def _format_thickness_smart(value) -> str:
    """Affiche en cm (1 décimale) si >= 1 cm, sinon en mm (1 décimale)."""
    try:
        m = float(value)
        cm = m * 100.0
        if cm >= 1.0:
            return f"{cm:.1f} cm"
        return f"{m * 1000.0:.1f} mm"
    except Exception:
        return "N/A"


def _format_eccentricity_cm(value) -> str:
    try:
        return f"{float(value) * 100.0:.2f} cm"
    except Exception:
        return "N/A"


def _mesh_type_label(raw) -> str:
    mapping = {
        "complete":      "prop_mesh_type_complete",
        "triangulation": "prop_mesh_type_triangulation",
        "none":          "prop_mesh_type_none",
    }
    key = mapping.get((raw or "").lower())
    return tr_ui(key) if key else (raw or "N/A")


def _mesh_density_label(raw) -> str:
    mapping = {
        "global":       "prop_mesh_density_global",
        "simplified":   "prop_mesh_density_simplified",
        "detailed":     "prop_mesh_density_detailed",
        "element_size": "prop_mesh_density_element_size",
    }
    key = mapping.get((raw or "").lower())
    return tr_ui(key) if key else (raw or "N/A")


def extract_planar_element_properties(el: dict, material_by_eid: dict):
    if not isinstance(el, dict):
        return {
            "kind": "planar_element",
            "type_label": tr_ui("prop_planar_element"),
            "prop_rows": [(tr_ui("prop_material_na"), "text", "N/A"),
                          (tr_ui("prop_thickness"),   "text", "N/A"),
                          (tr_ui("prop_slope_x"),     "text", "N/A"),
                          (tr_ui("prop_slope_y"),     "text", "N/A")],
            "mesh_rows": [],
            "rows": [],
            "thickness": "N/A",
        }

    material_eid = _extract_ref_eid(el, "material")
    material = material_by_eid.get(material_eid, "N/A") if material_eid is not None else "N/A"
    thickness = _format_thickness_smart(_dict_get_ci(el, "thicknessIn1stVertex", "thickness"))
    slope_x = _format_numeric(_dict_get_ci(el, "slopeX"))
    slope_y = _format_numeric(_dict_get_ci(el, "slopeY"))
    eccentricity = _format_eccentricity_cm(_dict_get_ci(el, "eccentricity"))
    eccentricity_fem = bool(_dict_get_ci(el, "eccentricityCOnsideredAlsoForFEM",
                                         "eccentricityConsideredAlsoForFEM") or False)
    vertices_count = str(len(el.get("geomPtsList") or []))

    mesh = _dict_get_ci(el, "meshProperties")
    if isinstance(mesh, dict):
        mesh_auto    = bool(mesh.get("automaticMesh", True))
        mesh_type    = _mesh_type_label(mesh.get("meshType"))
        mesh_density = _mesh_density_label(mesh.get("meshDensity"))
    else:
        mesh_auto    = True
        mesh_type    = "N/A"
        mesh_density = "N/A"

    type_label = _find_planar_type_label(el)
    user_id = _extract_user_id(el)

    prop_rows = [
        (tr_ui("prop_vertices"),        "text", vertices_count),
        (tr_ui("prop_material"),        "text", material),
        (tr_ui("prop_thickness"),       "text", thickness),
        (tr_ui("prop_slope_x"),         "text", slope_x),
        (tr_ui("prop_slope_y"),         "text", slope_y),
        (tr_ui("prop_eccentricity"),    "text", eccentricity),
        (tr_ui("prop_eccentricity_fem"), "bool", eccentricity_fem),
    ]
    mesh_rows = [
        (tr_ui("prop_mesh_automatic"), "bool", mesh_auto),
        (tr_ui("prop_mesh_type"),      "text", mesh_type),
        (tr_ui("prop_mesh_density"),   "text", mesh_density),
    ]

    return {
        "kind": "planar_element",
        "type_label": _label_with_user_id(type_label, user_id),
        "base_type_label": type_label,
        "user_id": user_id,
        "prop_rows": prop_rows,
        "mesh_rows": mesh_rows,
        # Champs legacy conservés pour filtres / métrés
        "rows": [
            (tr_ui("prop_material"),  material),
            (tr_ui("prop_thickness"), thickness),
            (tr_ui("prop_slope_x"),   slope_x),
            (tr_ui("prop_slope_y"),   slope_y),
        ],
        "material": material,
        "material_eid": material_eid,
        "thickness": thickness,
    }


def extract_planar_geometry(el: dict):
    pts = el.get("geomPtsList") or []
    outer = []
    for pt in pts:
        outer.append((float(pt["x"]), float(pt["y"]), float(pt["z"])))

    openings = []
    for opening in (el.get("openings") or []):
        hole = []
        for pt in opening:
            hole.append((float(pt["x"]), float(pt["y"]), float(pt["z"])))
        if len(hole) >= 3:
            openings.append(hole)

    if len(outer) < 3:
        return None

    return {
        "outer": outer,
        "openings": openings
    }


def extract_load_area_geometry(el: dict):
    pts = el.get("geomPtsList") or []
    outer = []

    for pt in pts:
        try:
            outer.append((float(pt["x"]), float(pt["y"]), float(pt["z"])))
        except Exception:
            pass

    if len(outer) < 3:
        return None

    return {
        "outer": outer,
        "openings": []
    }


_CLIMATIC_TYPE_TR_KEYS = {
    "CG_LOADAREA_BUILDING":                  "prop_load_area_climatic_building",
    "CG_LOADAREA_PROTRUDING_ROOF":           "prop_load_area_climatic_protruding_roof",
    "CG_LOADAREA_PARAPET":                   "prop_load_area_climatic_parapet",
    "CG_LOADAREA_ISOLATED_1_SLOPED_ROOF":    "prop_load_area_climatic_isolated_1_sloped",
    "CG_LOADAREA_ISOLATED_2_SLOPED_ROOF":    "prop_load_area_climatic_isolated_2_sloped",
    "CG_LOADAREA_PANEL":                     "prop_load_area_climatic_panel",
    "CG_LOADAREA_FOR_SCAFFOLDING":           "prop_load_area_climatic_scaffolding",
    "CG_LOADAREA_SHED_VERTICAL_ROOF":        "prop_load_area_climatic_shed_vertical",
    "CG_LOADAREA_AWNING":                    "prop_load_area_climatic_awning",
    "CG_LOADAREA_VAULTED_ROOFS_AND_DOME":    "prop_load_area_climatic_vaulted",
    "CG_LOADAREA_LOWER_ANGLE_INCLINED_WALL": "prop_load_area_climatic_inclined_wall",
    "CG_LOADAREA_FREE_STANDING_WALL":        "prop_load_area_climatic_free_standing_wall",
}

_TRANSFER_METHOD_TR_KEYS = {
    "eLoadTransferMethodFailureLines": "prop_load_area_transfer_failure_lines",
    "eLoadTransferMethodFemTransfer":  "prop_load_area_transfer_fem",
    "eLoadTransferMethodAuto":         "prop_load_area_transfer_auto",
}

_SPAN_DIRECTION_TR_KEYS = {
    "eFloorDeckLoadSpanDirectionX":  "prop_load_area_span_x",
    "eFloorDeckLoadSpanDirectionY":  "prop_load_area_span_y",
    "eFloorDeckLoadSpanDirectionXY": "prop_load_area_span_xy",
}


def extract_load_area_properties(el: dict) -> dict:
    """Extrait les propriétés d'une paroi (ElementLoadArea) pour l'onglet Propriétés.

    Structure JSON réelle retournée par l'API :
        el.loadTransferProperties.loadTransferMethodType
        el.loadTransferProperties.loadTransferSpanDirectionType
        el.mechanicalProperties.rigidDiafragm
        el.mechanicalProperties.selfWeightAuto
        el.climaticProperties.climaticType
        el.climaticProperties.availableForSnow
        el.climaticProperties.availableForWind
    """
    user_id = _extract_user_id(el)

    lt   = _dict_get_ci(el, "loadTransferProperties") or {}
    mech = _dict_get_ci(el, "mechanicalProperties")   or {}
    clim = _dict_get_ci(el, "climaticProperties")     or {}

    climatic_raw = str(_dict_get_ci(clim, "climaticType", default="") or "")
    transfer_raw = str(_dict_get_ci(lt,   "loadTransferMethodType", default="") or "")
    span_raw     = str(_dict_get_ci(lt,   "loadTransferSpanDirectionType",
                                    default="eFloorDeckLoadSpanDirectionXY") or "eFloorDeckLoadSpanDirectionXY")

    rigid_diafragm = _to_bool(_dict_get_ci(mech, "rigidDiafragm", default=False))
    self_weight    = _to_bool(_dict_get_ci(mech, "selfWeightAuto", "selfWeight", "hasSelfWeight", default=False))
    snow           = _to_bool(_dict_get_ci(clim, "availableForSnow", default=False))
    wind           = _to_bool(_dict_get_ci(clim, "availableForWind", default=False))

    return {
        "kind":            "load_area",
        "user_id":         user_id,
        "climatic_tr_key": _CLIMATIC_TYPE_TR_KEYS.get(climatic_raw, ""),
        "climatic_raw":    climatic_raw,
        "transfer_tr_key": _TRANSFER_METHOD_TR_KEYS.get(transfer_raw, ""),
        "transfer_raw":    transfer_raw,
        "span_tr_key":     _SPAN_DIRECTION_TR_KEYS.get(span_raw, ""),
        "span_raw":        span_raw,
        "rigid_diafragm":  rigid_diafragm,
        "self_weight":     self_weight,
        "snow":            snow,
        "wind":            wind,
    }


def _dict_get_ci(data, *names, default=None):
    """Recherche insensible à la casse dans un dict.

    Stratégie en deux passes :
    1. Correspondance exacte sur toutes les clés demandées — O(1) par clé, sans
       allocation. Couvre l'immense majorité des cas (les clés JSON de l'API AD
       sont stables et correspondent exactement aux noms attendus).
    2. Si aucune correspondance exacte, construction du lower_map une seule fois
       puis recherche insensible à la casse sur toutes les clés demandées.

    Cette approche évite de reconstruire le lower_map à chaque appel, ce qui
    était le principal coût de la version précédente (la fonction est invoquée
    des centaines de fois par élément lors du chargement du modèle).
    """
    if not isinstance(data, dict):
        return default

    # Passe 1 : correspondance exacte (pas d'allocation)
    for name in names:
        if name in data:
            return data[name]

    # Passe 2 : correspondance insensible à la casse (lower_map construit une seule fois)
    lower_map = {str(k).lower(): v for k, v in data.items()}
    for name in names:
        if (key := str(name).lower()) in lower_map:
            return lower_map[key]

    return default


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "oui")
    return False


def _to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _format_tc_behavior(value):
    raw = str(value or "").strip().lower()
    if raw.startswith("tr"):
        return tr_ui("label_tc_traction")
    if raw.startswith("co"):
        return tr_ui("label_tc_compression")
    if raw:
        return str(value)
    return ""


# Libellés i18n par famille d'appui (unsupported/advanced/rigid/elastic/stop)
_PUNCTUAL_SUPPORT_LABELS = {
    "unsupported": "prop_support_punctual_unsupported",
    "advanced":    "prop_support_punctual_advanced",
    "rigid":       "prop_support_punctual_rigid",
    "elastic":     "prop_support_punctual_elastic",
    "stop":        "prop_support_punctual_stop",
}
_LINEAR_SUPPORT_LABELS = {
    "unsupported": "prop_support_linear_unsupported",
    "advanced":    "prop_support_linear_advanced",
    "rigid":       "prop_support_linear_rigid",
    "elastic":     "prop_support_linear_elastic",
    "stop":        "prop_support_linear_stop",
}
_PLANAR_SUPPORT_LABELS = {
    "unsupported": "prop_support_planar_unsupported",
    "advanced":    "prop_support_planar_advanced",
    "rigid":       "prop_support_planar_rigid",
    "elastic":     "prop_support_planar_elastic",
    "stop":        "prop_support_planar_stop",
}


def _extract_support_properties(el: dict, lbl: dict) -> dict:
    """Factory commune pour les trois familles d'appuis (ponctuel/lineaire/surfacique).

    ``lbl`` est un dict de cles i18n avec les entrees :
    unsupported, advanced, rigid, elastic, stop.
    """
    if not isinstance(el, dict):
        return {"kind": "unsupported", "type_label": tr_ui(lbl["unsupported"]), "message": tr_ui("prop_not_supported")}

    raw_type = " ".join(
        str(_dict_get_ci(el, key, default="") or "")
        for key in ("elementType", "type", "typeName", "className", "$type")
    ).lower()
    restraints = _dict_get_ci(el, "restraints")
    stiffness  = _dict_get_ci(el, "stiffness")
    tc_behavior = _dict_get_ci(el, "tcBehavior")

    if "advanced" in raw_type:
        return {"kind": "advanced", "type_label": tr_ui(lbl["advanced"]), "message": tr_ui("prop_not_supported")}

    if isinstance(restraints, dict):
        user_id = _extract_user_id(el)
        return {
            "kind": "rigid",
            "type_label": _label_with_user_id(tr_ui(lbl["rigid"]), user_id),
            "base_type_label": tr_ui(lbl["rigid"]),
            "user_id": user_id,
            "section_title": tr_ui("label_section_blocking"),
            "restraints": {
                "TX": _to_bool(_dict_get_ci(restraints, "tx", "TX")),
                "TY": _to_bool(_dict_get_ci(restraints, "ty", "TY")),
                "TZ": _to_bool(_dict_get_ci(restraints, "tz", "TZ")),
                "RX": _to_bool(_dict_get_ci(restraints, "rx", "RX")),
                "RY": _to_bool(_dict_get_ci(restraints, "ry", "RY")),
                "RZ": _to_bool(_dict_get_ci(restraints, "rz", "RZ")),
            },
        }

    if isinstance(stiffness, dict):
        is_tc = (tc_behavior is not None or "tcpunctualsupport" in raw_type)
        user_id = _extract_user_id(el)
        base_type_label = tr_ui(lbl["stop"]) if is_tc else tr_ui(lbl["elastic"])
        return {
            "kind": "tc" if is_tc else "elastic",
            "type_label": _label_with_user_id(base_type_label, user_id),
            "base_type_label": base_type_label,
            "user_id": user_id,
            "section_title": tr_ui("label_section_stiffness"),
            "tc_behavior": _format_tc_behavior(tc_behavior),
            "stiffness": {
                "KTX": _to_float(_dict_get_ci(stiffness, "ktx", "KTX")),
                "KTY": _to_float(_dict_get_ci(stiffness, "kty", "KTY")),
                "KTZ": _to_float(_dict_get_ci(stiffness, "ktz", "KTZ")),
                "KRX": _to_float(_dict_get_ci(stiffness, "krx", "KRX")),
                "KRY": _to_float(_dict_get_ci(stiffness, "kry", "KRY")),
                "KRZ": _to_float(_dict_get_ci(stiffness, "krz", "KRZ")),
            },
        }

    if "advanced" in raw_type:
        return {"kind": "advanced", "type_label": tr_ui(lbl["advanced"]), "message": tr_ui("prop_not_supported")}
    return {"kind": "unsupported", "type_label": tr_ui(lbl["unsupported"]), "message": tr_ui("prop_not_supported")}


def extract_punctual_support_properties(el: dict) -> dict:
    return _extract_support_properties(el, _PUNCTUAL_SUPPORT_LABELS)


def extract_linear_support_properties(el: dict) -> dict:
    return _extract_support_properties(el, _LINEAR_SUPPORT_LABELS)


def extract_planar_support_properties(el: dict) -> dict:
    return _extract_support_properties(el, _PLANAR_SUPPORT_LABELS)


def get_results(host: str, result_type: str, analysis_case_id: int, element_ids: list) -> list:
    return get_api_client(host).get_results(result_type, analysis_case_id, element_ids)


def _find_first_dict_path(obj, preferred_keys=None):
    if isinstance(obj, dict):
        if preferred_keys:
            for key in preferred_keys:
                value = _dict_get_ci(obj, key)
                if isinstance(value, dict):
                    return value
        for value in obj.values():
            found = _find_first_dict_path(value, preferred_keys)
            if isinstance(found, dict):
                return found
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found = _find_first_dict_path(value, preferred_keys)
            if isinstance(found, dict):
                return found
    return None


def _fmt_result_value(value, factor=1.0):
    try:
        numeric = float(value) * float(factor)
    except Exception:
        return "N/A"
    if abs(numeric) < 0.01 and numeric != 0.0:
        return f"{numeric:.2e}"
    return f"{numeric:.2f}"


def _build_analysis_rows(result_family: str, result_payload: dict) -> list:
    rows = []
    family = str(result_family or "").strip().lower()
    payload = result_payload or {}
    if family == "déplacements":
        rows = [
            ("dx", f"{_fmt_result_value(_dict_get_ci(payload, 'dx'), 100.0)} cm"),
            ("dy", f"{_fmt_result_value(_dict_get_ci(payload, 'dy'), 100.0)} cm"),
            ("dz", f"{_fmt_result_value(_dict_get_ci(payload, 'dz'), 100.0)} cm"),
            ("d", f"{_fmt_result_value(_dict_get_ci(payload, 'd'), 100.0)} cm"),
            ("rx", f"{_fmt_result_value(_radians_to_degrees(_dict_get_ci(payload, 'rx')), 1.0)} °"),
            ("ry", f"{_fmt_result_value(_radians_to_degrees(_dict_get_ci(payload, 'ry')), 1.0)} °"),
            ("rz", f"{_fmt_result_value(_radians_to_degrees(_dict_get_ci(payload, 'rz')), 1.0)} °"),
            ("r", f"{_fmt_result_value(_radians_to_degrees(_dict_get_ci(payload, 'r')), 1.0)} °"),
        ]
    elif family == "efforts":
        rows = [
            ("fx", f"{_fmt_result_value(_dict_get_ci(payload, 'fx'), 1.0e-3)} kN"),
            ("fy", f"{_fmt_result_value(_dict_get_ci(payload, 'fy'), 1.0e-3)} kN"),
            ("fz", f"{_fmt_result_value(_dict_get_ci(payload, 'fz'), 1.0e-3)} kN"),
            ("mx", f"{_fmt_result_value(_dict_get_ci(payload, 'mx'), 1.0e-3)} kN.m"),
            ("my", f"{_fmt_result_value(_dict_get_ci(payload, 'my'), 1.0e-3)} kN.m"),
            ("mz", f"{_fmt_result_value(_dict_get_ci(payload, 'mz'), 1.0e-3)} kN.m"),
        ]
    elif family == "contraintes":
        rows = [
            ("sx", f"{_fmt_result_value(_dict_get_ci(payload, 'sx'), 1.0e-6)} MPa"),
            ("sy", f"{_fmt_result_value(_dict_get_ci(payload, 'sy'), 1.0e-6)} MPa"),
            ("sz", f"{_fmt_result_value(_dict_get_ci(payload, 'sz'), 1.0e-6)} MPa"),
            ("s", f"{_fmt_result_value(_dict_get_ci(payload, 's'), 1.0e-6)} MPa"),
        ]
    return [{"name": name, "value": value} for name, value in rows]


def read_punctual_support_results(host: str, support_eid: int, analysis_case_id: int, family_label: str) -> list:
    result_type_map = {
        "deplacements": "displacement",
        "efforts": "forces",
        "contraintes": "stresses",
    }
    family_key = _normalize_result_family_key(family_label)
    result_type = result_type_map.get(family_key)
    if not result_type:
        return []

    payloads = get_results(host, result_type, analysis_case_id, [support_eid])

    item = payloads[0] if payloads else {}
    if not isinstance(item, dict):
        return []

    node = _find_first_dict_path(item, preferred_keys=["resNode", "resnode"])
    if not isinstance(node, dict):
        return []

    if family_key == "deplacements":
        payload = _dict_get_ci(node, "resDisplacements", default={}) or {}
    elif family_key == "efforts":
        payload = _dict_get_ci(node, "resForces", default={}) or {}
    else:
        stresses = _dict_get_ci(node, "resStresses", default={}) or {}
        payload = _dict_get_ci(stresses, "support", default={}) or {}

    if not isinstance(payload, dict):
        return []
    return _build_analysis_rows(_analysis_result_display_label(family_label), payload)


def _find_first_dict_with_any_key(obj, keys) -> dict:
    wanted = {str(k).strip().lower() for k in (keys or []) if str(k).strip()}
    if not wanted:
        return {}
    if isinstance(obj, dict):
        existing = {str(k).strip().lower() for k in obj.keys()}
        if wanted & existing:
            return obj
        for value in obj.values():
            found = _find_first_dict_with_any_key(value, wanted)
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found = _find_first_dict_with_any_key(value, wanted)
            if found:
                return found
    return {}


def _to_float_or_none(value):
    if isinstance(value, dict):
        value = _dict_get_ci(value, "value", default=value)
    try:
        return float(value)
    except Exception:
        return None


def _format_force_kn(value) -> str:
    numeric = _to_float_or_none(value)
    if numeric is None:
        return "N/A"
    return f"{numeric / 1000.0:.2f} kN"


def _format_moment_knm(value) -> str:
    numeric = _to_float_or_none(value)
    if numeric is None:
        return "N/A"
    return f"{numeric / 1000.0:.2f} kN.m"


def _format_length_m(value) -> str:
    numeric = _to_float_or_none(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.2f} m"


def _extract_result_item_by_id(payloads, support_eid: int) -> dict:
    item = {}
    for candidate in payloads or []:
        if not isinstance(candidate, dict):
            continue
        candidate_id = _extract_ref_eid(candidate, "id")
        if candidate_id is None:
            try:
                candidate_id = int(candidate.get("id")) if candidate.get("id") is not None else None
            except Exception:
                candidate_id = None
        if candidate_id == int(support_eid):
            item = candidate
            break
    if not item and payloads:
        item = payloads[0] if isinstance(payloads[0], dict) else {}
    return item if isinstance(item, dict) else {}


def _build_support_torsor_rows(item: dict) -> list:
    if not isinstance(item, dict) or not item:
        return []
    return [
        {"name": "Fx", "value": _format_force_kn(_dict_get_ci(item, "torsorsFx"))},
        {"name": "Fy", "value": _format_force_kn(_dict_get_ci(item, "torsorsFy"))},
        {"name": "Fz", "value": _format_force_kn(_dict_get_ci(item, "torsorsFz"))},
        {"name": "Mx", "value": _format_moment_knm(_dict_get_ci(item, "torsorsMx"))},
        {"name": "My", "value": _format_moment_knm(_dict_get_ci(item, "torsorsMy"))},
        {"name": "Mz", "value": _format_moment_knm(_dict_get_ci(item, "torsorsMz"))},
    ]


def read_linear_support_results(host: str, support_eid: int, analysis_case_id: int, family_label: str) -> list:
    family_key = _normalize_result_family_key(family_label)
    if family_key != "efforts":
        return []

    payloads = get_results(host, "resultantforces", analysis_case_id, [support_eid])
    item = _extract_result_item_by_id(payloads, support_eid)
    return _build_support_torsor_rows(item)


def read_planar_support_results(host: str, support_eid: int, analysis_case_id: int, family_label: str) -> list:
    family_key = _normalize_result_family_key(family_label)
    if family_key != "efforts":
        return []

    payloads = get_results(host, "resultantforces", analysis_case_id, [support_eid])
    item = _extract_result_item_by_id(payloads, support_eid)
    return _build_support_torsor_rows(item)


def _pick_planar_torsor_value(item: dict, *keys):
    for key in keys:
        value = _dict_get_ci(item, key)
        if value is not None:
            return value
    return None


def _build_planar_element_torsor_block(title: str, torsor: dict, suffix: str) -> list:
    if not isinstance(torsor, dict):
        return []
    return [
        {"kind": "section_title", "name": title},
        {"name": "N", "value": _format_force_kn(_pick_planar_torsor_value(torsor, f"n_{suffix}", f"n{suffix}"))},
        {"name": "Mz", "value": _format_moment_knm(_pick_planar_torsor_value(torsor, f"mz_{suffix}", f"mz{suffix}"))},
        {"name": "Mf", "value": _format_moment_knm(_pick_planar_torsor_value(torsor, f"mf_{suffix}", f"mf{suffix}"))},
        {"name": "Txy", "value": _format_force_kn(_pick_planar_torsor_value(torsor, f"txy_{suffix}", f"txy{suffix}"))},
        {"name": "Tyz", "value": _format_force_kn(_pick_planar_torsor_value(torsor, f"tyz_{suffix}", f"tyz{suffix}"))},
    ]


def _build_planar_element_dimensions_block(torsor: dict) -> list:
    if not isinstance(torsor, dict):
        return []
    return [
        {"kind": "section_title", "name": "Dimensions"},
        {"name": tr_ui("prop_wall_height"), "value": _format_length_m(_pick_planar_torsor_value(torsor, "tW_Length_LR", "tWLengthLR"))},
        {"name": tr_ui("prop_wall_width"), "value": _format_length_m(_pick_planar_torsor_value(torsor, "tW_Length_BT", "tWLengthBT"))},
    ]


def read_planar_element_results(host: str, element_eid: int, analysis_case_id: int, family_label: str) -> list:
    family_key = _normalize_result_family_key(family_label)
    if family_key != "efforts":
        return []

    selected_item = {}
    torsors = []
    for result_type in ("resultantforces", "forces", "stresses", "displacement"):
        payloads = get_results(host, result_type, analysis_case_id, [element_eid])
        item = _extract_result_item_by_id(payloads, element_eid)
        if not item:
            continue
        selected_item = item
        torsors = list(_dict_get_ci(item, "resTorsors") or [])
        if torsors:
            break

    if not selected_item or not torsors:
        return []

    torsor_1 = torsors[0] if len(torsors) >= 1 and isinstance(torsors[0], dict) else {}
    torsor_2 = torsors[1] if len(torsors) >= 2 and isinstance(torsors[1], dict) else {}

    rows = []
    if torsor_1:
        rows.extend(_build_planar_element_torsor_block(tr_ui("prop_torsor_bottom"), torsor_1, "BottomTop"))
    if torsor_2:
        rows.extend(_build_planar_element_torsor_block(tr_ui("prop_torsor_top"), torsor_2, "BottomTop"))
    if torsor_1:
        rows.extend(_build_planar_element_torsor_block(tr_ui("prop_torsor_left"), torsor_1, "LeftRight"))
    if torsor_2:
        rows.extend(_build_planar_element_torsor_block(tr_ui("prop_torsor_right"), torsor_2, "LeftRight"))
    rows.extend(_build_planar_element_dimensions_block(torsor_1 or torsor_2))
    return rows


def _normalize_result_family_key(value: str) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "à": "a",
        "â": "a",
        "ù": "u",
        "û": "u",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ç": "c",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    aliases = {
        "displacements": "deplacements",
        "forces": "efforts",
        "stresses": "contraintes",
    }
    return aliases.get(text, text)


def _analysis_result_display_label(value: str) -> str:
    family_key = _normalize_result_family_key(value)
    if family_key == "deplacements":
        return tr_ui("analysis_result_displacements")
    if family_key == "efforts":
        return tr_ui("analysis_result_forces")
    if family_key == "contraintes":
        return tr_ui("analysis_result_stresses")
    return str(value or "").strip()


def _linear_result_scale_and_unit(family_key: str, value_key: str):
    normalized_family = _normalize_result_family_key(family_key)
    value_key = str(value_key or "").strip()
    if normalized_family == "deplacements":
        return 100.0, "cm"
    if normalized_family == "efforts":
        return (0.001, "kN.m") if value_key in ("mx", "my", "mz") else (0.001, "kN")
    if normalized_family == "contraintes":
        return 1e-6, "MPa"
    return 1.0, ""


def _coerce_abscissa_value_series(raw_values, family_key: str = "", value_key: str = "") -> list:
    if isinstance(raw_values, dict):
        for key in ("values", "items", "data", "points"):
            nested = _dict_get_ci(raw_values, key)
            if isinstance(nested, list):
                raw_values = nested
                break
    scale, _ = _linear_result_scale_and_unit(family_key, value_key)
    points = []
    for entry in list(raw_values or []):
        if not isinstance(entry, dict):
            continue
        abscissa = _to_float_or_none(_dict_get_ci(entry, "abscissa"))
        value = _to_float_or_none(_dict_get_ci(entry, "value"))
        if abscissa is None or value is None:
            continue
        points.append({"abscissa": float(abscissa), "value": float(value) * float(scale)})
    points.sort(key=lambda item: item["abscissa"])
    return points


def _linear_result_unit(family_key: str, value_key: str) -> str:
    return _linear_result_scale_and_unit(family_key, value_key)[1]


def _postprocess_linear_diagram_series(series: list, family_label: str, value_label: str) -> list:
    normalized_family = _normalize_result_family_key(family_label)
    component_key = str(value_label or "").strip().lower()
    if normalized_family == "deplacements" and component_key == "dz":
        return [
            {"abscissa": float((entry or {}).get("abscissa", 0.0)), "value": -float((entry or {}).get("value", 0.0))}
            for entry in list(series or [])
            if isinstance(entry, dict)
        ]
    return list(series or [])


def _extract_linear_diagram_series(item: dict, family_label: str, value_label: str) -> list:
    diagrams = _dict_get_ci(item, "resDiagrams")
    if not isinstance(diagrams, dict):
        return []
    normalized_family = _normalize_result_family_key(family_label)
    if normalized_family == "deplacements":
        section = _dict_get_ci(diagrams, "resDisplacements")
    elif normalized_family == "efforts":
        section = _dict_get_ci(diagrams, "resForces")
    elif normalized_family == "contraintes":
        section = _dict_get_ci(diagrams, "resStresses")
    else:
        section = None
    if not isinstance(section, dict):
        return []
    raw_values = _dict_get_ci(section, value_label)
    series = _coerce_abscissa_value_series(raw_values, family_label, value_label)
    return _postprocess_linear_diagram_series(series, family_label, value_label)


def read_linear_element_diagram_results(host: str, element_eid: int, analysis_case_id: int, family_label: str, value_label: str) -> dict:
    normalized_family = _normalize_result_family_key(family_label)
    result_types_map = {
        "deplacements": ["displacement"],
        "efforts": ["forces", "resultantforces"],
        "contraintes": ["stresses"],
    }
    search_types = list(result_types_map.get(normalized_family, []))
    for fallback in ("displacement", "forces", "resultantforces", "stresses"):
        if fallback not in search_types:
            search_types.append(fallback)

    selected_item = {}
    series = []
    for result_type in search_types:
        payloads = get_results(host, result_type, analysis_case_id, [element_eid])
        item = _extract_result_item_by_id(payloads, element_eid)
        if not item:
            continue
        selected_item = item
        series = _extract_linear_diagram_series(item, family_label, value_label)
        if series:
            break

    return {
        "kind": "linear_diagram",
        "element_eid": int(element_eid),
        "family_label": _analysis_result_display_label(family_label),
        "value_label": str(value_label or "").strip(),
        "unit": _linear_result_unit(family_label, value_label),
        "series": series,
        "title": f"{str(family_label or '').strip()} - {str(value_label or '').strip()}",
        "source_found": bool(selected_item),
    }


def read_linear_element_family_export(host: str, element_eid: int, analysis_case_id: int, family_label: str) -> dict:
    family_key = _normalize_result_family_key(family_label)
    export_components_map = {
        "deplacements": ["dx", "dy", "dz", "d"],
        "efforts": ["fx", "fy", "fz", "mx", "my", "mz"],
        "contraintes": ["sxxMin", "sxxMax", "sxyMin", "sxyMax", "sxzMin", "sxzMax", "sv"],
    }
    result_types_map = {
        "deplacements": ["displacement"],
        "efforts": ["forces", "resultantforces"],
        "contraintes": ["stresses"],
    }
    components = list(export_components_map.get(family_key, []))
    search_types = list(result_types_map.get(family_key, []))
    if not components or not search_types:
        return {"family_key": family_key, "components": [], "rows": []}
    payloads = []
    item = {}
    for result_type in search_types:
        payloads = get_results(host, result_type, analysis_case_id, [element_eid])
        item = _extract_result_item_by_id(payloads, element_eid)
        if isinstance(item, dict) and item:
            break
    if not isinstance(item, dict):
        item = {}
    series_map = {key: _extract_linear_diagram_series(item, family_key, key) for key in components}
    all_abscissas = sorted({float((entry or {}).get("abscissa", 0.0)) for values in series_map.values() for entry in values if isinstance(entry, dict)})
    rows = []
    for abscissa in all_abscissas:
        row = {"abscissa": float(abscissa)}
        for key in components:
            value = ""
            for entry in series_map.get(key, []):
                if abs(float((entry or {}).get("abscissa", 0.0)) - abscissa) <= 1e-9:
                    value = float((entry or {}).get("value", 0.0))
                    break
            row[key] = value
        rows.append(row)
    return {"family_key": family_key, "components": components, "rows": rows}


def read_linear_element_all_families_export(host: str, element_eid: int, analysis_case_id: int) -> dict:
    payloads = {}
    for family_key in ("deplacements", "efforts", "contraintes"):
        payloads[family_key] = read_linear_element_family_export(host, element_eid, analysis_case_id, family_key)
    return payloads


class ProjectSessionManager:
    def __init__(self, host: str, fto_path: str = ""):
        self.host = str(host or "").strip().rstrip("/")
        self.fto_path = normalize_windows_path(fto_path) if fto_path else ""
        self.api = get_api_client(self.host)
        self.is_open = False
        self.keep_open = False
        self.has_results = False

    def open(self, fto_path: str = "") -> str:
        if fto_path:
            self.fto_path = normalize_windows_path(fto_path)
        self.api.open_project(self.fto_path)
        self.is_open = True
        return self.fto_path

    def close(self) -> bool:
        if not self.is_open and not self.fto_path:
            self.keep_open = False
            self.has_results = False
            return False
        closed = self.api.close_project()
        if closed:
            self.is_open = False
            self.keep_open = False
            self.has_results = False
            self.fto_path = ""
        return closed

    def reset_api_session(self) -> bool:
        session_closed = self.api.close_session()
        self.is_open = False
        self.keep_open = False
        self.has_results = False
        self.fto_path = ""
        return session_closed

    def mark_results_state(self, has_results: bool):
        self.has_results = bool(has_results)
        self.keep_open = bool(has_results)

    def can_read_results(self, expected_path: str = "") -> bool:
        expected = normalize_windows_path(expected_path) if expected_path else ""
        if not self.is_open or not self.keep_open or not self.has_results or not self.fto_path:
            return False
        if expected and normalize_windows_path(self.fto_path) != expected:
            return False
        return True

    def export_state(self) -> dict:
        return {
            "normalized_path": self.fto_path,
            "project_closed": not self.is_open,
            "project_kept_open": self.keep_open and self.is_open,
            "has_analysis_results": self.has_results,
        }


def create_project_session(host: str, fto_path: str = "") -> ProjectSessionManager:
    return ProjectSessionManager(host, fto_path)


def _read_model_identifiers(host: str) -> dict:
    linear_ids = get_element_ids(host, "ElementLinear")
    planar_ids = get_element_ids(host, "ElementPlanar")
    load_area_ids = get_element_ids(host, "ElementLoadArea")
    punctual_support_ids = get_element_ids_for_types(host, PUNCTUAL_SUPPORT_TYPES)
    linear_support_ids = get_element_ids_for_types(host, LINEAR_SUPPORT_TYPES)
    planar_support_ids = get_element_ids_for_types(host, PLANAR_SUPPORT_TYPES)
    punctual_load_ids = get_element_ids(host, "ElementLoadPunctual")
    linear_load_ids = get_element_ids(host, "ElementLoadLinear")
    planar_load_ids = get_element_ids(host, "ElementLoadPlanar")
    return {
        "linear_ids": linear_ids,
        "planar_ids": planar_ids,
        "load_area_ids": load_area_ids,
        "punctual_support_ids": punctual_support_ids,
        "linear_support_ids": linear_support_ids,
        "planar_support_ids": planar_support_ids,
        "punctual_load_ids": punctual_load_ids,
        "linear_load_ids": linear_load_ids,
        "planar_load_ids": planar_load_ids,
    }


def _read_model_objects(host: str, ids_data: dict) -> dict:
    linear_elements = get_elements_objects(host, ids_data.get("linear_ids", []))
    planar_elements = get_elements_objects(host, ids_data.get("planar_ids", []))
    load_area_elements = get_elements_objects(host, ids_data.get("load_area_ids", []))
    punctual_support_elements = get_elements_objects(host, ids_data.get("punctual_support_ids", []))
    linear_support_elements = get_elements_objects(host, ids_data.get("linear_support_ids", []))
    planar_support_elements = get_elements_objects(host, ids_data.get("planar_support_ids", []))
    punctual_load_elements = get_elements_objects(host, ids_data.get("punctual_load_ids", []))
    linear_load_elements = get_elements_objects(host, ids_data.get("linear_load_ids", []))
    planar_load_elements = get_elements_objects(host, ids_data.get("planar_load_ids", []))
    return {
        "linear_elements": linear_elements,
        "planar_elements": planar_elements,
        "load_area_elements": load_area_elements,
        "punctual_support_elements": punctual_support_elements,
        "linear_support_elements": linear_support_elements,
        "planar_support_elements": planar_support_elements,
        "punctual_load_elements": punctual_load_elements,
        "linear_load_elements": linear_load_elements,
        "planar_load_elements": planar_load_elements,
    }


def _resolve_model_references(host: str, linear_elements: list, planar_elements: list) -> dict:
    linear_material_eids = set()
    linear_section_eids = set()
    for el in linear_elements:
        mat_eid = _extract_ref_eid(el, "material")
        sec_eid = _extract_ref_eid(el, "section")
        if mat_eid is not None:
            linear_material_eids.add(mat_eid)
        if sec_eid is not None:
            linear_section_eids.add(sec_eid)

    planar_material_eids = set()
    for el in planar_elements:
        mat_eid = _extract_ref_eid(el, "material")
        if mat_eid is not None:
            planar_material_eids.add(mat_eid)

    linear_material_by_eid = _resolve_name_map_by_eids(host, linear_material_eids, get_materials)
    linear_section_by_eid = _resolve_name_map_by_eids(host, linear_section_eids, get_sections)
    planar_material_by_eid = _resolve_name_map_by_eids(host, planar_material_eids, get_materials)
    all_material_by_eid = _resolve_object_map_by_eids(host, linear_material_eids | planar_material_eids, get_materials)

    return {
        "linear_material_eids": linear_material_eids,
        "linear_section_eids": linear_section_eids,
        "planar_material_eids": planar_material_eids,
        "linear_material_by_eid": linear_material_by_eid,
        "linear_section_by_eid": linear_section_by_eid,
        "planar_material_by_eid": planar_material_by_eid,
        "all_material_by_eid": all_material_by_eid,
    }


def _read_results_cases_data(host: str) -> list:
    load_case_ids = get_informational_ids(host, "LoadCase")
    load_case_objects = get_informational_elements_objects(host, load_case_ids)
    combination_ids = get_informational_ids(host, "Combination")
    combination_objects = get_informational_elements_objects(host, combination_ids)
    return _build_results_cases_combinations(
        load_case_ids,
        load_case_objects,
        combination_ids,
        combination_objects,
    )


def _resolve_load_case_labels(host: str, elements: list) -> dict:
    """Resout les libelles des cas de charge references par une liste d'elements.

    Retourne un dict {eid_int: label_str} pour tous les cas trouves.
    Utilise GetInformationalElementsObject dans un ordre deterministe (insertion).
    """
    lc_eids_needed: set = set()
    for el in elements:
        if not isinstance(el, dict):
            continue
        lc_ref = el.get("loadCase") or {}
        lc_eid = lc_ref.get("value") if isinstance(lc_ref, dict) else lc_ref
        if lc_eid is not None:
            try:
                lc_eids_needed.add(int(lc_eid))
            except (TypeError, ValueError):
                pass

    lc_by_eid: dict = {}
    if lc_eids_needed:
        try:
            ordered_eids = list(lc_eids_needed)   # ordre d'insertion - stable Python 3.7+
            lc_objects = get_informational_elements_objects(host, ordered_eids)
            for lc_eid, lc_obj in zip(ordered_eids, lc_objects or []):
                if not isinstance(lc_obj, dict):
                    continue
                user_id = lc_obj.get("userID")
                name = _get_username(lc_obj) or str(lc_obj.get("name") or "").strip()
                left = str(user_id).strip() if user_id not in (None, "") else str(lc_eid)
                label = f"{left} : {name}" if name else left
                lc_by_eid[int(lc_eid)] = label
        except Exception:
            pass
    return lc_by_eid


def _get_element_float(el: dict, key: str) -> float:
    """Lit une composante numerique depuis un dict API en gerant la casse (fx/Fx, etc.)."""
    key_cap = key[0].upper() + key[1:]
    return float(el.get(key) or el.get(key_cap) or 0.0)


def _get_moment_float(el: dict, moment_dict, key: str) -> float:
    """Lit un moment depuis le sous-dict 'moment' ou directement depuis l'element."""
    key_cap = key[0].upper() + key[1:]
    if isinstance(moment_dict, dict):
        return float(
            moment_dict.get(key) or moment_dict.get(key_cap)
            or el.get(key) or el.get(key_cap) or 0.0
        )
    return float(el.get(key) or el.get(key_cap) or 0.0)


def _build_punctual_loads_payload(host: str, ids_data: dict, objects_data: dict) -> dict:
    """Construit la liste des charges ponctuelles avec résolution des cas de charge.

    Retourne un dict avec :
    - ``punctual_loads``      : liste de dicts par charge (position, forces, cas)
    - ``punctual_load_cases`` : liste de dicts {eid, label} — cas uniques triés
    - ``punctual_load_ids_count`` / ``punctual_load_count`` : compteurs
    """
    punctual_load_ids = list(ids_data.get("punctual_load_ids", []) or [])
    punctual_load_elements = list(objects_data.get("punctual_load_elements", []) or [])

    if not punctual_load_ids or not punctual_load_elements:
        return {
            "punctual_loads": [],
            "punctual_load_cases": [],
            "punctual_load_ids_count": len(punctual_load_ids),
            "punctual_load_count": 0,
        }

    lc_by_eid = _resolve_load_case_labels(host, punctual_load_elements)

    # Construire la liste des charges
    punctual_loads = []
    seen_lc_eids = {}  # eid -> label, pour ordre d'apparition
    for el in punctual_load_elements:
        if not isinstance(el, dict):
            continue
        pt = el.get("geomPt") or {}
        if not pt:
            continue
        try:
            x = float(pt.get("x", 0.0))
            y = float(pt.get("y", 0.0))
            z = float(pt.get("z", 0.0))
        except (TypeError, ValueError):
            continue

        fx = _get_element_float(el, "fx") / 1000.0   # N -> kN
        fy = _get_element_float(el, "fy") / 1000.0
        fz = _get_element_float(el, "fz") / 1000.0

        # Moments — l'API retourne un sous-dict {"mx": ..., "my": ..., "mz": ...}
        # sous la cle "moment", mais peut aussi les exposer a plat selon la version.
        moment_dict = el.get("moment") or {}
        mx = _get_moment_float(el, moment_dict, "mx") / 1000.0
        my = _get_moment_float(el, moment_dict, "my") / 1000.0
        mz = _get_moment_float(el, moment_dict, "mz") / 1000.0

        # Identifiant utilisateur
        user_id = el.get("userID") or el.get("userId") or el.get("userid")

        # Cas de charge
        lc_ref = el.get("loadCase") or {}
        lc_eid = lc_ref.get("value") if isinstance(lc_ref, dict) else lc_ref
        lc_eid_int = None
        lc_label = ""
        if lc_eid is not None:
            try:
                lc_eid_int = int(lc_eid)
                lc_label = lc_by_eid.get(lc_eid_int, str(lc_eid_int))
                if lc_eid_int not in seen_lc_eids:
                    seen_lc_eids[lc_eid_int] = lc_label
            except (TypeError, ValueError):
                pass

        punctual_loads.append({
            "pos": (x, y, z),
            "fx": fx,
            "fy": fy,
            "fz": fz,
            "mx": mx,
            "my": my,
            "mz": mz,
            "user_id": user_id,
            "load_case_eid": lc_eid_int,
            "load_case_label": lc_label,
        })

    # Cas de charge uniques, dans l'ordre d'apparition
    punctual_load_cases = [
        {"eid": eid, "label": label}
        for eid, label in seen_lc_eids.items()
    ]

    return {
        "punctual_loads": punctual_loads,
        "punctual_load_cases": punctual_load_cases,
        "punctual_load_ids_count": len(punctual_load_ids),
        "punctual_load_count": len(punctual_loads),
    }


def _build_linear_loads_payload(host: str, ids_data: dict, objects_data: dict) -> dict:
    """Construit la liste des charges linéaires avec résolution des cas de charge.

    Retourne un dict avec :
    - ``linear_loads``      : liste de dicts par charge (points, forces, moments, variation, cas)
    - ``linear_load_cases`` : liste de dicts {eid, label} — cas uniques triés
    - ``linear_load_ids_count`` / ``linear_load_count`` : compteurs
    """
    linear_load_ids = list(ids_data.get("linear_load_ids", []) or [])
    linear_load_elements = list(objects_data.get("linear_load_elements", []) or [])

    if not linear_load_ids or not linear_load_elements:
        return {
            "linear_loads": [],
            "linear_load_cases": [],
            "linear_load_ids_count": len(linear_load_ids),
            "linear_load_count": 0,
        }

    lc_by_eid = _resolve_load_case_labels(host, linear_load_elements)

    # Construire la liste des charges linéaires
    linear_loads = []
    seen_lc_eids = {}
    for el in linear_load_elements:
        if not isinstance(el, dict):
            continue
        pt1 = el.get("geomPtStart") or {}
        pt2 = el.get("geomPtEnd") or {}
        if not pt1 or not pt2:
            continue
        try:
            x1 = float(pt1.get("x", 0.0))
            y1 = float(pt1.get("y", 0.0))
            z1 = float(pt1.get("z", 0.0))
            x2 = float(pt2.get("x", 0.0))
            y2 = float(pt2.get("y", 0.0))
            z2 = float(pt2.get("z", 0.0))
        except (TypeError, ValueError):
            continue

        # Forces (N/m -> kN/m)
        fx = _get_element_float(el, "fx") / 1000.0
        fy = _get_element_float(el, "fy") / 1000.0
        fz = _get_element_float(el, "fz") / 1000.0

        # Moments (N.m/m -> kN.m/m) — sous-dict "moment"
        moment_dict = el.get("moment") or {}
        mx = _get_moment_float(el, moment_dict, "mx") / 1000.0
        my = _get_moment_float(el, moment_dict, "my") / 1000.0
        mz = _get_moment_float(el, moment_dict, "mz") / 1000.0

        # Variation (coefficients de début et fin)
        variation = el.get("variation")
        if isinstance(variation, dict):
            coeff1 = float(variation.get("coefficient1") if variation.get("coefficient1") is not None else 1.0)
            coeff2 = float(variation.get("coefficient2") if variation.get("coefficient2") is not None else 1.0)
        else:
            coeff1 = 1.0
            coeff2 = 1.0

        # Identifiant utilisateur
        user_id = el.get("userID") or el.get("userId") or el.get("userid")

        # Cas de charge
        lc_ref = el.get("loadCase") or {}
        lc_eid = lc_ref.get("value") if isinstance(lc_ref, dict) else lc_ref
        lc_eid_int = None
        lc_label = ""
        if lc_eid is not None:
            try:
                lc_eid_int = int(lc_eid)
                lc_label = lc_by_eid.get(lc_eid_int, str(lc_eid_int))
                if lc_eid_int not in seen_lc_eids:
                    seen_lc_eids[lc_eid_int] = lc_label
            except (TypeError, ValueError):
                pass

        linear_loads.append({
            "pt_start": (x1, y1, z1),
            "pt_end": (x2, y2, z2),
            "fx": fx,
            "fy": fy,
            "fz": fz,
            "mx": mx,
            "my": my,
            "mz": mz,
            "coeff1": coeff1,
            "coeff2": coeff2,
            "user_id": user_id,
            "load_case_eid": lc_eid_int,
            "load_case_label": lc_label,
        })

    linear_load_cases = [
        {"eid": eid, "label": label}
        for eid, label in seen_lc_eids.items()
    ]

    return {
        "linear_loads": linear_loads,
        "linear_load_cases": linear_load_cases,
        "linear_load_ids_count": len(linear_load_ids),
        "linear_load_count": len(linear_loads),
    }


def _build_planar_loads_payload(host: str, ids_data: dict, objects_data: dict) -> dict:
    """Construit la liste des charges surfaciques avec resolution des cas de charge.

    Retourne un dict avec :
    - ``planar_loads``      : liste de dicts par charge (points, forces, variation, cas)
    - ``planar_load_cases`` : liste de dicts {eid, label} - cas uniques
    - ``planar_load_ids_count`` / ``planar_load_count`` : compteurs
    """
    planar_load_ids = list(ids_data.get("planar_load_ids", []) or [])
    planar_load_elements = list(objects_data.get("planar_load_elements", []) or [])

    if not planar_load_ids or not planar_load_elements:
        return {
            "planar_loads": [],
            "planar_load_cases": [],
            "planar_load_ids_count": len(planar_load_ids),
            "planar_load_count": 0,
        }

    lc_by_eid = _resolve_load_case_labels(host, planar_load_elements)

    # Construire la liste des charges surfaciques
    planar_loads = []
    seen_lc_eids = {}
    for el in planar_load_elements:
        if not isinstance(el, dict):
            continue

        # Points geometriques (polygone de la charge)
        geom_pts_raw = el.get("geomPtsList") or []
        pts = []
        for pt in geom_pts_raw:
            if not isinstance(pt, dict):
                continue
            try:
                x = float(pt.get("x", 0.0))
                y = float(pt.get("y", 0.0))
                z = float(pt.get("z", 0.0))
                pts.append((x, y, z))
            except (TypeError, ValueError):
                continue

        if len(pts) < 3:
            continue

        # Forces (N/m2 -> kN/m2)
        fx = _get_element_float(el, "fx") / 1000.0
        fy = _get_element_float(el, "fy") / 1000.0
        fz = _get_element_float(el, "fz") / 1000.0

        # Variation (coefficients 1/2/3 pour les 3 premiers points)
        variation = el.get("variation")
        if isinstance(variation, dict):
            coeff1 = float(variation.get("coefficient1") if variation.get("coefficient1") is not None else 1.0)
            coeff2 = float(variation.get("coefficient2") if variation.get("coefficient2") is not None else 1.0)
            coeff3 = float(variation.get("coefficient3") if variation.get("coefficient3") is not None else 1.0)
        else:
            coeff1 = 1.0
            coeff2 = 1.0
            coeff3 = 1.0

        # Identifiant utilisateur
        user_id = el.get("userID") or el.get("userId") or el.get("userid")

        # Cas de charge
        lc_ref = el.get("loadCase") or {}
        lc_eid = lc_ref.get("value") if isinstance(lc_ref, dict) else lc_ref
        lc_eid_int = None
        lc_label = ""
        if lc_eid is not None:
            try:
                lc_eid_int = int(lc_eid)
                lc_label = lc_by_eid.get(lc_eid_int, str(lc_eid_int))
                if lc_eid_int not in seen_lc_eids:
                    seen_lc_eids[lc_eid_int] = lc_label
            except (TypeError, ValueError):
                pass

        planar_loads.append({
            "pts": pts,
            "fx": fx,
            "fy": fy,
            "fz": fz,
            "coeff1": coeff1,
            "coeff2": coeff2,
            "coeff3": coeff3,
            "user_id": user_id,
            "load_case_eid": lc_eid_int,
            "load_case_label": lc_label,
        })

    planar_load_cases = [
        {"eid": eid, "label": label}
        for eid, label in seen_lc_eids.items()
    ]

    return {
        "planar_loads": planar_loads,
        "planar_load_cases": planar_load_cases,
        "planar_load_ids_count": len(planar_load_ids),
        "planar_load_count": len(planar_loads),
    }


def _build_geometry_payload(ids_data: dict, objects_data: dict, refs_data: dict) -> dict:
    linear_elements = list(objects_data.get("linear_elements", []) or [])
    planar_elements = list(objects_data.get("planar_elements", []) or [])
    load_area_elements = list(objects_data.get("load_area_elements", []) or [])
    punctual_support_elements = list(objects_data.get("punctual_support_elements", []) or [])
    linear_support_elements = list(objects_data.get("linear_support_elements", []) or [])
    planar_support_elements = list(objects_data.get("planar_support_elements", []) or [])

    linear_ids = list(ids_data.get("linear_ids", []) or [])
    planar_ids = list(ids_data.get("planar_ids", []) or [])
    load_area_ids = list(ids_data.get("load_area_ids", []) or [])
    punctual_support_ids = list(ids_data.get("punctual_support_ids", []) or [])
    linear_support_ids = list(ids_data.get("linear_support_ids", []) or [])
    planar_support_ids = list(ids_data.get("planar_support_ids", []) or [])

    linear_material_by_eid = dict(refs_data.get("linear_material_by_eid", {}) or {})
    linear_section_by_eid = dict(refs_data.get("linear_section_by_eid", {}) or {})
    planar_material_by_eid = dict(refs_data.get("planar_material_by_eid", {}) or {})
    all_material_by_eid = dict(refs_data.get("all_material_by_eid", {}) or {})
    linear_material_eids = set(refs_data.get("linear_material_eids", set()) or set())
    planar_material_eids = set(refs_data.get("planar_material_eids", set()) or set())
    linear_section_eids = set(refs_data.get("linear_section_eids", set()) or set())

    lines = []
    line_properties = []
    planars = []
    planar_eids = []
    planar_properties = []
    load_areas = []
    load_area_properties = []
    punctual_supports = []
    punctual_support_eids = []
    punctual_support_properties = []
    linear_supports = []
    linear_support_eids = []
    linear_support_properties = []
    planar_supports = []
    planar_support_eids = []
    planar_support_properties = []

    linear_takeoff = _build_linear_takeoff(linear_elements, linear_section_by_eid)
    linear_material_takeoff = _build_linear_material_takeoff(linear_elements, linear_material_by_eid)
    planar_takeoff = _build_planar_takeoff(planar_elements)
    planar_material_takeoff = _build_planar_material_takeoff(planar_elements, planar_material_by_eid)
    load_area_takeoff = _build_load_area_takeoff(load_area_elements)

    for el in linear_elements:
        p1 = el.get("geomPtStart")
        p2 = el.get("geomPtEnd")
        if p1 and p2:
            lines.append([
                (float(p1["x"]), float(p1["y"]), float(p1["z"])),
                (float(p2["x"]), float(p2["y"]), float(p2["z"]))
            ])
            line_properties.append(extract_linear_element_properties(el, linear_material_by_eid, linear_section_by_eid))

    for planar_eid, el in zip(planar_ids, planar_elements):
        geom = extract_planar_geometry(el)
        if not geom:
            continue
        planars.append(geom)
        planar_eids.append(int(planar_eid) if planar_eid is not None else None)
        planar_properties.append(extract_planar_element_properties(el, planar_material_by_eid))

    for el in load_area_elements:
        geom = extract_load_area_geometry(el)
        if not geom:
            continue
        load_areas.append(geom)
        load_area_properties.append(extract_load_area_properties(el))

    for support_eid, el in zip(punctual_support_ids, punctual_support_elements):
        pt = el.get("geomPt")
        if pt:
            punctual_supports.append((float(pt["x"]), float(pt["y"]), float(pt["z"])))
            punctual_support_eids.append(int(support_eid) if support_eid is not None else None)
            punctual_support_properties.append(extract_punctual_support_properties(el))

    for support_eid, el in zip(linear_support_ids, linear_support_elements):
        p1 = el.get("geomPtStart")
        p2 = el.get("geomPtEnd")
        if p1 and p2:
            linear_supports.append([
                (float(p1["x"]), float(p1["y"]), float(p1["z"])),
                (float(p2["x"]), float(p2["y"]), float(p2["z"]))
            ])
            linear_support_eids.append(int(support_eid) if support_eid is not None else None)
            linear_support_properties.append(extract_linear_support_properties(el))

    for support_eid, el in zip(planar_support_ids, planar_support_elements):
        pts = el.get("geomPtsList") or []
        outer = []
        for pt in pts:
            outer.append((float(pt["x"]), float(pt["y"]), float(pt["z"])))
        if len(outer) >= 3:
            planar_supports.append({"outer": outer, "openings": []})
            planar_support_eids.append(int(support_eid) if support_eid is not None else None)
            planar_support_properties.append(extract_planar_support_properties(el))

    openings_count = sum(len(p["openings"]) for p in planars)

    return {
        "lines": lines,
        "line_properties": line_properties,
        "line_eids": [int(eid) if eid is not None else None for eid in linear_ids],
        "planars": planars,
        "planar_eids": planar_eids,
        "planar_properties": planar_properties,
        "load_areas": load_areas,
        "load_area_properties": load_area_properties,
        "linear_takeoff": linear_takeoff,
        "linear_material_takeoff": linear_material_takeoff,
        "planar_takeoff": planar_takeoff,
        "planar_material_takeoff": planar_material_takeoff,
        "load_area_takeoff": load_area_takeoff,
        "all_material_by_eid": all_material_by_eid,
        "punctual_supports": punctual_supports,
        "punctual_support_eids": punctual_support_eids,
        "punctual_support_properties": punctual_support_properties,
        "linear_supports": linear_supports,
        "linear_support_eids": linear_support_eids,
        "linear_support_properties": linear_support_properties,
        "planar_supports": planar_supports,
        "planar_support_eids": planar_support_eids,
        "planar_support_properties": planar_support_properties,
        "linear_ids_count": len(linear_ids),
        "planar_ids_count": len(planar_ids),
        "load_area_ids_count": len(load_area_ids),
        "punctual_support_ids_count": len(punctual_support_ids),
        "linear_support_ids_count": len(linear_support_ids),
        "planar_support_ids_count": len(planar_support_ids),
        "linear_count": len(lines),
        "planar_count": len(planars),
        "load_area_count": len(load_areas),
        "punctual_support_count": len(punctual_supports),
        "linear_support_count": len(linear_supports),
        "planar_support_count": len(planar_supports),
        "openings_count": openings_count,
        "materials_resolved_count": len(all_material_by_eid),
        "materials_eids_count": len(linear_material_eids | planar_material_eids),
        "linear_sections_resolved_count": len(linear_section_by_eid),
        "linear_section_eids_count": len(linear_section_eids),
    }


def read_fem_mesh(host: str, element_eids: list = None) -> tuple:
    """Récupère les nœuds et la connectivité du maillage FEM depuis l'API.

    Retourne un tuple ``(nodes, mesh_by_eid)`` :
    - ``nodes``      : liste de tuples ``(x, y, z)`` — positions des nœuds.
    - ``mesh_by_eid``: dict ``{eid: [[n0,n1,n2], ...]}`` — faces par EID d'élément.

    En cas d'erreur ou de maillage vide, retourne ``([], {})``.
    """
    try:
        raw_nodes = get_mesh_nodes(host)
    except Exception:
        return [], {}

    if not raw_nodes:
        return [], {}

    nodes = []
    for pt in raw_nodes:
        if not isinstance(pt, dict):
            continue
        try:
            nodes.append((float(pt.get("x", 0.0)), float(pt.get("y", 0.0)), float(pt.get("z", 0.0))))
        except (TypeError, ValueError):
            nodes.append((0.0, 0.0, 0.0))

    try:
        raw_conn = get_mesh_connectivity(host, element_eids)
    except Exception:
        return nodes, {}

    # Chaque MeshElement : { "id": {"value": eid}, "connectivity": Int32Matrix }
    # Int32Matrix (column-major) : { "_data": [...], "rows": nœuds/élément, "cols": nb éléments }
    mesh_by_eid: dict = {}
    for elem in (raw_conn or []):
        if not isinstance(elem, dict):
            continue

        # Récupération de l'EID
        id_obj = elem.get("id") or {}
        eid = int(id_obj.get("value", 0)) if isinstance(id_obj, dict) else None
        if not eid:
            continue

        matrix = elem.get("connectivity") or {}
        if not isinstance(matrix, dict):
            continue

        raw_data = matrix.get("_data") or []
        rows = int(matrix.get("rows") or 0)   # nœuds par face
        cols = int(matrix.get("cols") or 0)   # nombre de faces

        if not raw_data or rows < 3:
            continue

        if cols <= 0 and rows > 0:
            cols = len(raw_data) // rows

        faces = []
        for j in range(cols):
            start = j * rows
            face = [int(raw_data[start + i]) for i in range(rows) if start + i < len(raw_data)]
            if len(face) >= 3:
                faces.append(face)

        if faces:
            mesh_by_eid[eid] = faces

    return nodes, mesh_by_eid


def extract_model_geometry(host: str, fto_path: str, progress_callback=None, session_manager=None) -> ModelDataDict:
    def progress(value: int, message: str = ""):
        if callable(progress_callback):
            progress_callback(value, message)

    fto_path = normalize_windows_path(fto_path)
    result = None
    session = session_manager if isinstance(session_manager, ProjectSessionManager) else create_project_session(host, fto_path)

    progress(10, tr_ui("progress_open_project"))
    session.open(fto_path)

    try:
        progress(18, tr_ui("progress_read_ids"))
        ids_data = _read_model_identifiers(host)

        progress(40, tr_ui("progress_read_objects"))
        objects_data = _read_model_objects(host, ids_data)

        progress(50, tr_ui("progress_resolve_refs"))
        refs_data = _resolve_model_references(
            host,
            objects_data.get("linear_elements", []),
            objects_data.get("planar_elements", []),
        )

        progress(66, tr_ui("progress_read_cases"))
        results_cases_combinations = _read_results_cases_data(host)

        progress(70, tr_ui("progress_check_results"))
        has_analysis_results = diagnose_results_availability(host)
        session.mark_results_state(has_analysis_results)

        # Lecture du maillage FEM si des résultats sont disponibles
        fem_nodes: list = []
        fem_by_eid: dict = {}
        if has_analysis_results:
            progress(71, tr_ui("progress_read_fem_mesh"))
            linear_ids = [int(eid) for eid in (ids_data.get("linear_ids") or []) if eid is not None]
            planar_ids = [int(eid) for eid in (ids_data.get("planar_ids") or []) if eid is not None]
            all_element_eids = linear_ids + planar_ids
            try:
                fem_nodes, fem_by_eid = read_fem_mesh(host, element_eids=all_element_eids)
            except Exception:
                fem_nodes, fem_by_eid = [], {}

        progress(72, tr_ui("progress_convert_geometry"))
        geometry_payload = _build_geometry_payload(ids_data, objects_data, refs_data)

        progress(80, tr_ui("progress_read_punctual_loads"))
        punctual_loads_payload = _build_punctual_loads_payload(host, ids_data, objects_data)

        progress(84, tr_ui("progress_read_linear_loads"))
        linear_loads_payload = _build_linear_loads_payload(host, ids_data, objects_data)

        progress(86, tr_ui("progress_read_planar_loads"))
        planar_loads_payload = _build_planar_loads_payload(host, ids_data, objects_data)

        progress(88, tr_ui("progress_prepare_results"))
        result = build_model_data({
            **geometry_payload,
            **punctual_loads_payload,
            **linear_loads_payload,
            **planar_loads_payload,
            "normalized_path": session.fto_path,
            "results_cases_combinations": results_cases_combinations,
            "fem_nodes": fem_nodes,
            "fem_by_eid": fem_by_eid,
        })
        result.update(session.export_state())
        result = build_model_data(result)
        return result

    finally:
        if not session.keep_open:
            progress(95, tr_ui("progress_close_project"))
            closed = session.close()
            if isinstance(result, dict):
                result["project_closed"] = closed
                result["project_kept_open"] = False


class LoadModelWorker(QThread):
    log = Signal(str, str)
    progress = Signal(int, str)
    success = Signal(dict)
    error = Signal(str)

    def __init__(self, host: str, fto_path: str):
        super().__init__()
        self.host = host.rstrip("/")
        self.fto_path = normalize_windows_path(fto_path)
        self.session_manager = create_project_session(self.host, self.fto_path)

    def _emit_progress(self, value: int, message: str = ""):
        self.progress.emit(max(0, min(100, int(value))), message)

    def run(self):
        try:
            self._emit_progress(2, tr_log("checking_api"))
            self.log.emit(tr_log("checking_api"), "info")
            check_port(self.host)
            self._emit_progress(6, tr_log("api_ok"))
            self.log.emit(tr_log("api_ok"), "ok")
            self.log.emit(tr_log("normalized_path", path=self.fto_path), "info")
            self.log.emit(tr_log("opening_project_reading"), "info")

            model_data = extract_model_geometry(
                self.host,
                self.fto_path,
                progress_callback=self._emit_progress,
                session_manager=self.session_manager,
            )

            if model_data.get("project_kept_open"):
                self.log.emit(tr_log("project_kept_open_for_results"), "ok")
            elif model_data.get("project_closed", False):
                self.log.emit(tr_log("project_closed_after_read"), "ok")

            self._emit_progress(97, tr_log("progress_finalizing"))
            self.log.emit(tr_log("ids_linear", count=model_data["linear_ids_count"]), "info")
            self.log.emit(tr_log("ids_planar", count=model_data["planar_ids_count"]), "info")
            self.log.emit(tr_log("ids_load_area", count=model_data["load_area_ids_count"]), "info")
            self.log.emit(tr_log("ids_support_punctual", count=model_data["punctual_support_ids_count"]), "info")
            self.log.emit(tr_log("ids_punctual_loads", count=model_data["punctual_load_ids_count"]), "info")
            self.log.emit(tr_log("ids_linear_loads", count=model_data["linear_load_ids_count"]), "info")
            self.log.emit(tr_log("ids_planar_loads", count=model_data["planar_load_ids_count"]), "info")
            self.log.emit(tr_log("ids_support_linear", count=model_data["linear_support_ids_count"]), "info")
            self.log.emit(tr_log("ids_support_planar", count=model_data["planar_support_ids_count"]), "info")
            self.log.emit(
                tr_log(
                    "resolved_materials",
                    resolved=model_data["materials_resolved_count"],
                    total=model_data["materials_eids_count"],
                ),
                "info"
            )
            self.log.emit(
                tr_log(
                    "resolved_linear_sections",
                    resolved=model_data["linear_sections_resolved_count"],
                    total=model_data["linear_section_eids_count"],
                ),
                "info"
            )

            self.log.emit(
                tr_log(
                    "loaded_geometry",
                    linear=model_data["linear_count"],
                    planar=model_data["planar_count"],
                    load_areas=model_data["load_area_count"],
                    openings=model_data["openings_count"],
                ),
                "ok"
            )
            self.log.emit(
                tr_log(
                    "loaded_supports",
                    punctual=model_data["punctual_support_count"],
                    linear=model_data["linear_support_count"],
                    planar=model_data["planar_support_count"],
                ),
                "ok"
            )
            self.log.emit(
                tr_log("results_available") if model_data.get("has_analysis_results") else tr_log("results_unavailable"),
                "ok" if model_data.get("has_analysis_results") else "error"
            )

            self._emit_progress(100, tr_log("progress_load_done"))
            self.success.emit(model_data)

        except ApiUnavailableError as e:
            self.error.emit(str(e))
        except ProjectAlreadyOpenError as e:
            self.error.emit(str(e))
        except Exception:
            self.error.emit(traceback.format_exc())

