# export_advance_design_ifc_v3.py
# Version migrée vers IfcOpenShell pour l'écriture IFC.

#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import socket
import sys
import urllib.parse
import uuid
from collections import defaultdict

import requests

from section_geometry import *  # geometrie de section pure, sans ifcopenshell

DEFAULT_HOST = "http://localhost:52000"
DEFAULT_OUT = "export_advance_design_ifc_v3.ifc"
VERSION = "2026_09_06.01"

LINEAR_TYPES = [
    "ElementLinear",
]
PLANAR_TYPES = [
    "ElementPlanar",
]
SUPPORT_TYPES = [
    "ElementRigidPunctualSupport",
    "ElementElasticPunctualSupport",
    "ElementTCPunctualSupport",
    "ElementAdvancedPunctualSupport",
    "ElementRigidLinearSupport",
    "ElementElasticLinearSupport",
    "ElementTCLinearSupport",
    "ElementAdvancedLinearSupport",
    "ElementRigidPlanarSupport",
    "ElementElasticPlanarSupport",
    "ElementTCPlanarSupport",
    "ElementAdvancedPlanarSupport",
]
LOAD_TYPES = [
    "ElementLoadPunctual",
    "ElementLoadLinear",
    "ElementLoadPlanar",
    "ElementImposedDisplacement",
]
EXCLUDED_TYPES = {"ElementSinglePile", "ElementLoadArea"}


class ApiUnavailableError(RuntimeError):
    pass


class ProjectAlreadyOpenError(RuntimeError):
    pass


def check_port(host: str) -> None:
    parsed = urllib.parse.urlparse(host)
    hostname = parsed.hostname
    port = parsed.port
    if hostname is None:
        raise ApiUnavailableError(f"URL API invalide: {host}")
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex((hostname, port))
    finally:
        sock.close()
    if result != 0:
        raise ApiUnavailableError(f"API non joignable sur {hostname}:{port}. Vérifiez qu'Advance Design est lancé et que l'API REST est active.")


def check_fto_path(fto_path: str) -> str:
    fto_path = os.path.abspath(os.path.normpath(str(fto_path).strip().strip('"').strip("'")))
    if not os.path.exists(fto_path):
        raise FileNotFoundError(f"Fichier .fto introuvable: {fto_path}")
    if not os.path.isfile(fto_path):
        raise FileNotFoundError(f"Le chemin ne désigne pas un fichier: {fto_path}")
    if not os.access(fto_path, os.R_OK):
        raise PermissionError(f"Fichier .fto non lisible: {fto_path}")
    return fto_path


def extract_diagnostics(details: dict) -> str:
    diagnostics = (details or {}).get("diagnostics") or []
    parts = []
    for d in diagnostics:
        sev = str(d.get("severity") or "").strip()
        code = str(d.get("code") or "").strip()
        msg = str(d.get("message") or "").strip()
        src = str(d.get("source") or "").strip()
        blob = " | ".join(x for x in [sev, code, msg, src] if x)
        if blob:
            parts.append(blob)
    return " ; ".join(parts)


def is_already_open_diagnostic(details: dict) -> bool:
    diagnostics = (details or {}).get("diagnostics") or []
    for d in diagnostics:
        blob = " ".join([str(d.get("code") or ""), str(d.get("message") or ""), str(d.get("source") or "")]).lower()
        if any(s in blob for s in ["already open", "already opened", "deja ouvert", "déjà ouvert", "file is open", "project is open", "used by another process", "being used by another process", "cannot access the file", "verrouill"]):
            return True
    return False


def check_response(resp: requests.Response, label: str) -> dict:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:1000]
        raise RuntimeError(f"{label} HTTP {resp.status_code} sur {resp.request.method} {resp.url}: {body}") from e
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"{label} a retourné une réponse non JSON") from e
    details = data.get("details") or {}
    if details and not details.get("success", True):
        diag = extract_diagnostics(details)
        if label == "OpenProject" and is_already_open_diagnostic(details):
            raise ProjectAlreadyOpenError(f"Le fichier est déjà ouvert dans Advance Design ou verrouillé par un autre processus. {diag}".strip())
        raise RuntimeError(f"{label} échec API: {diag or data}")
    return data


DEBUG_ROUTES = False


def api_post(host: str, endpoint: str, payload=None, params=None, timeout=30, label=None) -> dict:
    url = f"{host}{endpoint}"
    if DEBUG_ROUTES:
        print(f"POST {url} params={params}")
    try:
        resp = requests.post(url, json=payload, params=params, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ApiUnavailableError(f"Impossible de contacter l'API Advance Design ({host}).") from e
    return check_response(resp, label or endpoint)


def api_get(host: str, endpoint: str, timeout=30) -> dict:
    url = f"{host}{endpoint}"
    if DEBUG_ROUTES:
        print(f"GET {url}")
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ApiUnavailableError(f"Impossible de contacter l'API Advance Design ({host}).") from e
    return check_response(resp, endpoint)


def open_project(host: str, fto_path: str) -> None:
    api_post(host, "/api/Model/management/OpenProject", payload={}, params={"filename": fto_path}, label="OpenProject")


def close_project(host: str) -> None:
    try:
        api_post(host, "/api/Model/management/CloseProject", payload={}, timeout=15, label="CloseProject")
    except Exception:
        pass


def get_ids_for_type(host: str, element_type: str):
    payload = [{"$type": "QueryElementsModel", "elementType": element_type}]
    return api_post(host, "/api/Model/elements/GetElementsID", payload).get("data") or []


def get_elements(host: str, ids):
    if not ids:
        return []
    return api_post(host, "/api/Model/elements/GetElementsObject", ids).get("data") or []


def get_materials(host: str):
    ids = api_get(host, "/api/Model/materials/GetListMaterials").get("data") or []
    if not ids:
        return {}
    mats = api_post(host, "/api/Model/materials/GetMaterials", ids).get("data") or []
    out = {}
    for eid, item in zip(ids, mats):
        if item:
            out[eid] = item
    return out


def get_sections(host: str):
    ids = api_get(host, "/api/Model/sections/GetListSections").get("data") or []
    if not ids:
        return {}
    secs = api_post(host, "/api/Model/sections/GetSections", ids).get("data") or []
    out = {}
    for eid, item in zip(ids, secs):
        if item:
            out[eid] = item
    return out


def eid_value(ref):
    if isinstance(ref, dict):
        return ref.get("value")
    return ref


def f3(v):
    return round(float(v), 6)


def vec_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vec_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vec_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def vec_len(v):
    return math.sqrt(vec_dot(v, v))


def vec_norm(v):
    n = vec_len(v)
    if n < 1e-12:
        return [1.0, 0.0, 0.0]
    return [v[0] / n, v[1] / n, v[2] / n]


def any_perp(v):
    x, y, z = [abs(c) for c in v]
    if x <= y and x <= z:
        base = [1.0, 0.0, 0.0]
    elif y <= z:
        base = [0.0, 1.0, 0.0]
    else:
        base = [0.0, 0.0, 1.0]
    return vec_norm(vec_cross(v, base))


def point3(obj):
    return [float(obj.get("x", 0.0)), float(obj.get("y", 0.0)), float(obj.get("z", 0.0))]


def planar_basis(pts3):
    origin = pts3[0]
    u = None
    for i in range(1, len(pts3)):
        cand = vec_sub(pts3[i], origin)
        if vec_len(cand) > 1e-9:
            u = vec_norm(cand)
            break
    if u is None:
        u = [1, 0, 0]
    n = None
    for i in range(1, len(pts3) - 1):
        a = vec_sub(pts3[i], origin)
        b = vec_sub(pts3[i + 1], origin)
        cand = vec_cross(a, b)
        if vec_len(cand) > 1e-9:
            n = vec_norm(cand)
            break
    if n is None:
        n = [0, 0, 1]
    v = vec_norm(vec_cross(n, u))
    if vec_len(v) < 1e-9:
        v = any_perp(u)
        n = vec_norm(vec_cross(u, v))
    u = vec_norm(vec_cross(v, n))
    return origin, u, v, n


def to_local_2d(pt, origin, u, v):
    d = vec_sub(pt, origin)
    return [vec_dot(d, u), vec_dot(d, v)]


def support_kind_name(t):
    if "Punctual" in t:
        return "PunctualSupport"
    if "Linear" in t:
        return "LinearSupport"
    if "Planar" in t:
        return "PlanarSupport"
    return "Support"


def guid22():
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
    n = uuid.uuid4().int
    out = []
    for _ in range(22):
        out.append(chars[n % len(chars)])
        n //= len(chars)
    return "".join(out)



class IfcWriter:
    ENTITY_NAME_MAP = {
        "IFCARBITRARYCLOSEDPROFILEDEF": "IfcArbitraryClosedProfileDef",
        "IFCAXIS2PLACEMENT3D": "IfcAxis2Placement3D",
        "IFCBEAM": "IfcBeam",
        "IFCBUILDING": "IfcBuilding",
        "IFCBUILDINGELEMENTPROXY": "IfcBuildingElementProxy",
        "IFCBUILDINGSTOREY": "IfcBuildingStorey",
        "IFCCARTESIANPOINT": "IfcCartesianPoint",
        "IFCCOLUMN": "IfcColumn",
        "IFCDIRECTION": "IfcDirection",
        "IFCEXTRUDEDAREASOLID": "IfcExtrudedAreaSolid",
        "IFCEXTRUDEDAREASOLIDTAPERED": "IfcExtrudedAreaSolidTapered",
        "IFCGEOMETRICREPRESENTATIONCONTEXT": "IfcGeometricRepresentationContext",
        "IFCISHAPEPROFILEDEF": "IfcIShapeProfileDef",
        "IFCLOCALPLACEMENT": "IfcLocalPlacement",
        "IFCMEMBER": "IfcMember",
        "IFCMATERIAL": "IfcMaterial",
        "IFCOPENINGELEMENT": "IfcOpeningElement",
        "IFCPOLYLINE": "IfcPolyline",
        "IFCPRODUCTDEFINITIONSHAPE": "IfcProductDefinitionShape",
        "IFCPROJECT": "IfcProject",
        "IFCPROPERTYSET": "IfcPropertySet",
        "IFCPROPERTYSINGLEVALUE": "IfcPropertySingleValue",
        "IFCRECTANGLEPROFILEDEF": "IfcRectangleProfileDef",
        "IFCRELAGGREGATES": "IfcRelAggregates",
        "IFCRELASSOCIATESMATERIAL": "IfcRelAssociatesMaterial",
        "IFCRELCONTAINEDINSPATIALSTRUCTURE": "IfcRelContainedInSpatialStructure",
        "IFCRELDEFINESBYPROPERTIES": "IfcRelDefinesByProperties",
        "IFCRELVOIDSELEMENT": "IfcRelVoidsElement",
        "IFCSHAPEREPRESENTATION": "IfcShapeRepresentation",
        "IFCSIUNIT": "IfcSIUnit",
        "IFCSITE": "IfcSite",
        "IFCSLAB": "IfcSlab",
        "IFCUNITASSIGNMENT": "IfcUnitAssignment",
        "IFCWALL": "IfcWall",
    }

    def __init__(self):
        try:
            import ifcopenshell
            import ifcopenshell.guid
        except ImportError as exc:
            raise RuntimeError(
                "IfcOpenShell est requis pour cette version v4.6.16. Installez-le avec 'pip install ifcopenshell'."
            ) from exc
        self.ifcopenshell = ifcopenshell
        self.guid = ifcopenshell.guid
        self.model = ifcopenshell.file(schema="IFC4X3_ADD2")
        self.cache = {}
        self.owner_history = None
        self.context = None
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        self.contained = []
        self.material_cache = {}

    def _guid(self):
        return self.guid.new()

    def _camel(self, raw):
        return self.ENTITY_NAME_MAP.get(raw.upper(), raw)

    def _ifc_typed_value(self, value):
        if value is None:
            return None
        if hasattr(value, 'is_a'):
            return value
        if isinstance(value, bool):
            return self.model.createIfcBoolean(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return self.model.createIfcInteger(value)
        if isinstance(value, float):
            return self.model.createIfcReal(value)
        return self.model.createIfcText(str(value))

    def _decode(self, value):
        if value is None:
            return None
        if hasattr(value, 'is_a'):
            return value
        if isinstance(value, (bool, int, float, tuple, list)):
            return value
        if not isinstance(value, str):
            return value
        txt = value.strip()
        if txt == '$':
            return None
        if txt == '.T.':
            return True
        if txt == '.F.':
            return False
        if txt.startswith("'") and txt.endswith("'") and len(txt) >= 2:
            return txt[1:-1].replace("''", "'")
        if txt.startswith('.') and txt.endswith('.') and len(txt) >= 3:
            return txt[1:-1]
        if re.fullmatch(r'[-+]?\d+', txt):
            return int(txt)
        if re.fullmatch(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?', txt):
            return float(txt)
        return txt

    def add(self, entity, *args):
        name = self._camel(entity)
        vals = [self._decode(a) for a in args]
        return self.model.create_entity(name, *vals)

    def s(self, val):
        if val is None:
            return '$'
        txt = str(val).replace("'", "''")
        return f"'{txt}'"

    def num(self, val):
        return f"{float(val):.6f}".rstrip('0').rstrip('.') or '0'

    def bool(self, val):
        return '.T.' if val else '.F.'

    def enum(self, name):
        return f'.{name}.'

    def tup(self, items):
        return '(' + ','.join(items) + ')'

    def pt2(self, x, y):
        key = ('pt2', f3(x), f3(y))
        if key not in self.cache:
            self.cache[key] = self.model.create_entity('IfcCartesianPoint', (float(x), float(y)))
        return self.cache[key]

    def pt3(self, x, y, z):
        key = ('pt3', f3(x), f3(y), f3(z))
        if key not in self.cache:
            self.cache[key] = self.model.create_entity('IfcCartesianPoint', (float(x), float(y), float(z)))
        return self.cache[key]

    def dir3(self, x, y, z):
        key = ('dir3', f3(x), f3(y), f3(z))
        if key not in self.cache:
            self.cache[key] = self.model.create_entity('IfcDirection', (float(x), float(y), float(z)))
        return self.cache[key]

    def axis2placement3d(self, origin, axis=None, refdir=None):
        return self.model.create_entity(
            'IfcAxis2Placement3D',
            self.pt3(*origin),
            self.dir3(*axis) if axis is not None else None,
            self.dir3(*refdir) if refdir is not None else None,
        )

    def local_placement(self, rel_to=None, origin=(0, 0, 0), axis=None, refdir=None):
        return self.model.create_entity('IfcLocalPlacement', rel_to, self.axis2placement3d(origin, axis, refdir))

    def setup(self, project_name='Advance Design Export'):
        world = self.axis2placement3d([0, 0, 0], [0, 0, 1], [1, 0, 0])
        self.context = self.model.create_entity(
            'IfcGeometricRepresentationContext',
            None, 'Model', 3, 1.0e-05, world, None
        )
        metre = self.model.create_entity('IfcSIUnit', None, 'LENGTHUNIT', None, 'METRE')
        area = self.model.create_entity('IfcSIUnit', None, 'AREAUNIT', None, 'SQUARE_METRE')
        volume = self.model.create_entity('IfcSIUnit', None, 'VOLUMEUNIT', None, 'CUBIC_METRE')
        rad = self.model.create_entity('IfcSIUnit', None, 'PLANEANGLEUNIT', None, 'RADIAN')
        units = self.model.create_entity('IfcUnitAssignment', [metre, area, volume, rad])
        project_placement = self.local_placement(None, [0, 0, 0])
        site_placement = self.local_placement(project_placement, [0, 0, 0])
        building_placement = self.local_placement(site_placement, [0, 0, 0])
        storey_placement = self.local_placement(building_placement, [0, 0, 0])
        self.project = self.model.create_entity(
            'IfcProject', self._guid(), self.owner_history, project_name, None, None, None, None, [self.context], units
        )
        self.site = self.model.create_entity(
            'IfcSite', self._guid(), self.owner_history, 'Site', None, None, site_placement, None, None,
            'ELEMENT', None, None, None, None
        )
        self.building = self.model.create_entity(
            'IfcBuilding', self._guid(), self.owner_history, 'Building', None, None, building_placement, None, None,
            'ELEMENT', None, None, None
        )
        self.storey = self.model.create_entity(
            'IfcBuildingStorey', self._guid(), self.owner_history, 'Storey 0', None, None, storey_placement,
            None, None, 'ELEMENT', 0.0
        )
        self.model.create_entity('IfcRelAggregates', self._guid(), self.owner_history, None, None, self.project, [self.site])
        self.model.create_entity('IfcRelAggregates', self._guid(), self.owner_history, None, None, self.site, [self.building])
        self.model.create_entity('IfcRelAggregates', self._guid(), self.owner_history, None, None, self.building, [self.storey])

    def polyline2(self, pts):
        return self.model.create_entity('IfcPolyline', [self.pt2(*p) for p in pts])

    def polyline3(self, pts):
        return self.model.create_entity('IfcPolyline', [self.pt3(*p) for p in pts])

    def rect_profile_def(self, name, width, depth):
        return self.model.create_entity('IfcRectangleProfileDef', 'AREA', name, None, float(width), float(depth))

    def circle_profile_def(self, name, radius):
        return self.model.create_entity('IfcCircleProfileDef', 'AREA', name, None, float(radius))

    def circle_hollow_profile_def(self, name, radius, thickness):
        return self.model.create_entity('IfcCircleHollowProfileDef', 'AREA', name, None, float(radius), float(thickness))

    def rect_hollow_profile_def(self, name, width, depth, thickness):
        return self.model.create_entity(
            'IfcRectangleHollowProfileDef', 'AREA', name, None,
            float(width), float(depth), float(thickness), None, None
        )

    def arbitrary_profile_def(self, name, pts2):
        if pts2[0] != pts2[-1]:
            pts2 = pts2 + [pts2[0]]
        curve = self.polyline2(pts2)
        return self.model.create_entity('IfcArbitraryClosedProfileDef', 'AREA', name, curve)

    def i_profile_def(self, name, dims):
        width = float(dims.get('width', dims.get('overall_width', 0.15)))
        depth = float(dims.get('depth', dims.get('overall_depth', 0.30)))
        web = float(dims.get('web', dims.get('web_thickness', 0.006)))
        flange = float(dims.get('flange', dims.get('flange_thickness', 0.010)))
        return self.model.create_entity(
            'IfcIShapeProfileDef', 'AREA', name, None,
            width, depth, web, flange, None, None
        )

    def profile_from_dims(self, name, dims):
        kind = str(dims.get('kind', 'RECT')).upper()
        if kind == 'RECT':
            return self.rect_profile_def(name or 'RectProfile', dims['width'], dims['depth'])
        if kind == 'CIRCLE':
            return self.circle_profile_def(name or 'CircleProfile', dims['radius'])
        if kind == 'CIRCLETUBE':
            return self.circle_hollow_profile_def(name or 'CircleTubeProfile', dims['radius'], dims['thickness'])
        if kind == 'RECTTUBE':
            return self.rect_hollow_profile_def(name or 'RectTubeProfile', dims['width'], dims['depth'], dims['thickness'])
        if kind == 'T':
            return self.arbitrary_profile_def(name or 'TProfile', t_profile_polygon(dims))
        if kind == 'TDISSYMETRIC':
            return self.arbitrary_profile_def(name or 'TDissymProfile', t_dissym_profile_polygon(dims))
        if kind == 'U':
            return self.arbitrary_profile_def(name or 'UProfile', u_profile_polygon(dims))
        if kind in {'Z', 'ZED', 'ZED_SLOPED'}:
            return self.arbitrary_profile_def(name or 'ZedProfile', zed_profile_polygon(dims))
        if kind == 'OMEGA':
            return self.arbitrary_profile_def(name or 'OmegaProfile', omega_profile_polygon(dims))
        if kind == 'SIGMA':
            return self.arbitrary_profile_def(name or 'SigmaProfile', sigma_profile_polygon(dims))
        if kind == 'ANGLE':
            return self.arbitrary_profile_def(name or 'AngleProfile', l_profile_polygon(dims))
        if kind == 'I':
            return self.i_profile_def(name, dims)
        return self.rect_profile_def(name or 'RectProfile', dims.get('width', 0.20), dims.get('depth', 0.20))

    def extruded_profile_solid(self, profile, solid_pos, depth, axis_dir=(0, 0, 1)):
        return self.model.create_entity(
            'IfcExtrudedAreaSolid', profile, solid_pos, self.dir3(*axis_dir), float(depth)
        )

    def extruded_profile_solid_tapered(self, start_profile, end_profile, solid_pos, depth, axis_dir=(0, 0, 1)):
        return self.model.create_entity(
            'IfcExtrudedAreaSolidTapered', start_profile, solid_pos, self.dir3(*axis_dir), float(depth), end_profile
        )

    def shape_axis_curve(self, pts3):
        axis = self.model.create_entity('IfcShapeRepresentation', self.context, 'Axis', 'Curve3D', [self.polyline3(pts3)])
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [axis])

    def shape_axis_and_body(self, local_axis_pts, body_item):
        axis = self.model.create_entity('IfcShapeRepresentation', self.context, 'Axis', 'Curve3D', [self.polyline3(local_axis_pts)])
        body = self.model.create_entity('IfcShapeRepresentation', self.context, 'Body', 'SweptSolid', [body_item])
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [axis, body])

    def shape_axis_and_body_items(self, axis_pts3, body_items, body_type='Brep'):
        axis = self.model.create_entity('IfcShapeRepresentation', self.context, 'Axis', 'Curve3D', [self.polyline3(axis_pts3)])
        body = self.model.create_entity('IfcShapeRepresentation', self.context, 'Body', body_type, list(body_items))
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [axis, body])

    def shape_body_items(self, body_items, body_type='Brep'):
        body = self.model.create_entity('IfcShapeRepresentation', self.context, 'Body', body_type, list(body_items))
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [body])

    def extruded_closed_body(self, pts2, depth, solid_pos):
        if pts2[0] != pts2[-1]:
            pts2 = pts2 + [pts2[0]]
        curve = self.polyline2(pts2)
        profile = self.model.create_entity('IfcArbitraryClosedProfileDef', 'AREA', None, curve)
        body_item = self.model.create_entity('IfcExtrudedAreaSolid', profile, solid_pos, self.dir3(0, 0, 1), float(depth))
        body = self.model.create_entity('IfcShapeRepresentation', self.context, 'Body', 'SweptSolid', [body_item])
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [body])

    def pyramid_brep_item(self, apex, base_size, height):
        half = float(base_size) / 2.0
        h = float(height)
        ax, ay, az = [float(c) for c in apex]
        p0 = self.pt3(ax, ay, az)
        p1 = self.pt3(ax - half, ay - half, az - h)
        p2 = self.pt3(ax + half, ay - half, az - h)
        p3 = self.pt3(ax + half, ay + half, az - h)
        p4 = self.pt3(ax - half, ay + half, az - h)

        def face(points):
            loop = self.model.create_entity('IfcPolyLoop', points)
            bound = self.model.create_entity('IfcFaceOuterBound', loop, True)
            return self.model.create_entity('IfcFace', [bound])

        faces = [
            face([p1, p2, p3, p4]),
            face([p0, p2, p1]),
            face([p0, p3, p2]),
            face([p0, p4, p3]),
            face([p0, p1, p4]),
        ]
        shell = self.model.create_entity('IfcClosedShell', faces)
        return self.model.create_entity('IfcFacetedBrep', shell)

    def planar_plate_brep_item(self, pts3, thickness, normal):
        top = [self.pt3(*p) for p in pts3]
        offset = [normal[0] * float(thickness), normal[1] * float(thickness), normal[2] * float(thickness)]
        bottom_pts = [[p[0] - offset[0], p[1] - offset[1], p[2] - offset[2]] for p in pts3]
        bottom = [self.pt3(*p) for p in bottom_pts]
        n = len(top)

        def face(points):
            loop = self.model.create_entity('IfcPolyLoop', points)
            bound = self.model.create_entity('IfcFaceOuterBound', loop, True)
            return self.model.create_entity('IfcFace', [bound])

        faces = [face(top), face(list(reversed(bottom)))]
        for i in range(n):
            j = (i + 1) % n
            faces.append(face([top[i], top[j], bottom[j], bottom[i]]))
        shell = self.model.create_entity('IfcClosedShell', faces)
        return self.model.create_entity('IfcFacetedBrep', shell)

    def loft_brep_item(self, section_pts_list):
        point_cache = {}
        def cp(p):
            key = (round(float(p[0]), 9), round(float(p[1]), 9), round(float(p[2]), 9))
            if key not in point_cache:
                point_cache[key] = self.pt3(*key)
            return point_cache[key]
        def face(points):
            loop = self.model.create_entity('IfcPolyLoop', [cp(p) for p in points])
            bound = self.model.create_entity('IfcFaceOuterBound', loop, True)
            return self.model.create_entity('IfcFace', [bound])
        faces = []
        first = section_pts_list[0]
        last = section_pts_list[-1]
        faces.append(face(first))
        faces.append(face(list(reversed(last))))
        for a, b in zip(section_pts_list[:-1], section_pts_list[1:]):
            n = min(len(a), len(b))
            for i in range(n):
                j = (i + 1) % n
                faces.append(face([a[i], a[j], b[j], b[i]]))
        shell = self.model.create_entity('IfcClosedShell', faces)
        return self.model.create_entity('IfcFacetedBrep', shell)

    def pyramid_body(self, base_size, height):
        brep = self.pyramid_brep_item([0.0, 0.0, 0.0], base_size, height)
        body = self.model.create_entity('IfcShapeRepresentation', self.context, 'Body', 'Brep', [brep])
        return self.model.create_entity('IfcProductDefinitionShape', None, None, [body])

    def add_pset(self, product, pset_name, props):
        prop_list = []
        for k, v in props.items():
            prop = self.model.create_entity('IfcPropertySingleValue', str(k), None, self._ifc_typed_value(v), None)
            prop_list.append(prop)
        pset = self.model.create_entity('IfcPropertySet', self._guid(), self.owner_history, str(pset_name), None, prop_list)
        self.model.create_entity('IfcRelDefinesByProperties', self._guid(), self.owner_history, None, None, [product], pset)
        return pset

    def ensure_material(self, name):
        if not name:
            return None
        key = str(name).strip()
        if not key:
            return None
        if key not in self.material_cache:
            self.material_cache[key] = self.model.create_entity('IfcMaterial', key, None, None)
        return self.material_cache[key]

    def assign_material(self, product, name):
        material = self.ensure_material(name)
        if material is None:
            return None
        return self.model.create_entity('IfcRelAssociatesMaterial', self._guid(), self.owner_history, None, None, [product], material)

    def finish(self):
        if self.contained:
            self.model.create_entity(
                'IfcRelContainedInSpatialStructure', self._guid(), self.owner_history, None, None,
                list(self.contained), self.storey
            )
        if hasattr(self.model, 'to_string'):
            return self.model.to_string()
        return str(self.model)


def combined_body_shape(w: IfcWriter, el: dict, start, end, sec: dict, beam_type: str, sec_name: str, sec_end: dict | None = None, sec_end_name: str | None = None):
    defn0 = parse_combined_section(sec or {})
    if not defn0:
        return None, None, False
    combo0 = combined_member_polygons(defn0)
    if not combo0 or len(combo0.get('polygons') or []) != 2:
        return None, None, False
    combo0 = dict(combo0)
    ang = section_orientation_angle_rad(el)
    combo0_polys, _, _, _ = translate_section_excentration_polys(combo0.get('polygons') or [], el)
    combo0['polygons'] = [rotate_poly2(poly, ang) for poly in combo0_polys]
    axis_vec = vec_sub(end, start)
    length = vec_len(axis_vec)
    if length < 1e-9:
        return w.shape_axis_curve([start, end]), None, False
    beam_dir = vec_norm(axis_vec)
    up_ref = [0.0, 0.0, 1.0]
    if abs(vec_dot(beam_dir, up_ref)) > 0.999:
        up_ref = [1.0, 0.0, 0.0]
    section_x = vec_norm(vec_cross(up_ref, beam_dir))
    if vec_len(section_x) < 1e-9:
        section_x = [1.0, 0.0, 0.0]
    placement = w.local_placement(None, start, beam_dir, section_x)
    local_axis_pts = [[0.0, 0.0, 0.0], [0.0, 0.0, length]]
    is_variable = str(beam_type).lower() == 'variablebeam' and sec_end
    body_items = []
    if is_variable:
        defn1 = parse_combined_section(sec_end or {})
        combo1 = combined_member_polygons(defn1) if defn1 else None
        if combo1 and combo1.get('code') == combo0.get('code') and len(combo1.get('polygons') or []) == len(combo0.get('polygons') or []):
            combo1 = dict(combo1)
            combo1_polys, _, _, _ = translate_section_excentration_polys(combo1.get('polygons') or [], el)
            combo1['polygons'] = [rotate_poly2(poly, ang) for poly in combo1_polys]
            for p0, p1 in zip(combo0['polygons'], combo1['polygons']):
                body_items.append(w.loft_brep_item([section_pts3_local(0.0, p0), section_pts3_local(length, p1)]))
        else:
            for p0 in combo0['polygons']:
                body_items.append(w.loft_brep_item([section_pts3_local(0.0, p0), section_pts3_local(length, p0)]))
    else:
        for p0 in combo0['polygons']:
            body_items.append(w.loft_brep_item([section_pts3_local(0.0, p0), section_pts3_local(length, p0)]))
    shape = w.shape_axis_and_body_items(local_axis_pts, body_items, body_type='Brep')
    return shape, placement, True


def section_pts3_local(station, poly2):
    z = float(station)
    return [[float(x), float(y), z] for x, y in poly2]


def linear_haunch_body_shape(w: IfcWriter, el: dict, start, end, sec: dict, beam_type: str, sec_name: str, haunch_start: dict, haunch_end: dict, sections: dict):
    axis_vec = vec_sub(end, start)
    length = vec_len(axis_vec)
    if length < 1e-9:
        return w.shape_axis_curve([start, end]), None, False
    beam_dir = vec_norm(axis_vec)
    up_ref = [0.0, 0.0, 1.0]
    if abs(vec_dot(beam_dir, up_ref)) > 0.999:
        up_ref = [1.0, 0.0, 0.0]
    section_x = vec_norm(vec_cross(up_ref, beam_dir))
    if vec_len(section_x) < 1e-9:
        section_x = [1.0, 0.0, 0.0]
    base_dims = default_linear_dims(sec, beam_type)
    if str(base_dims.get('kind', '')).upper() != 'I' or not is_i_or_h_catalog_section(sec):
        return None, None, False

    hs_len = min(length, haunch_length_along_axis(haunch_start, length, beam_dir))
    he_len = min(length, haunch_length_along_axis(haunch_end, length, beam_dir))
    if hs_len + he_len > length and (hs_len + he_len) > 1e-9:
        scale = length / (hs_len + he_len)
        hs_len *= scale
        he_len *= scale

    hs_active = hs_len > 1e-6 and str((haunch_start or {}).get('haunchPosition') or '').lower() != 'no_haunch'
    he_active = he_len > 1e-6 and str((haunch_end or {}).get('haunchPosition') or '').lower() != 'no_haunch'
    if not hs_active and not he_active:
        return None, None, False

    ex_dx, ex_dy = section_excentration_translation_local(el, base_dims)
    ang = section_orientation_angle_rad(el)
    base_poly = translate_polygon2(i_section_polygon(base_dims), dx=ex_dx, dy=ex_dy)
    body_items = [w.loft_brep_item([
        section_pts3_local(0.0, rotate_poly2(base_poly, ang)),
        section_pts3_local(length, rotate_poly2(base_poly, ang))
    ])]
    base_depth = float(base_dims.get('depth', 0.30))

    if hs_active:
        hs_ref = resolve_haunch_section_dims(sec, haunch_start, sections, beam_type)
        hs_dims = apply_haunch_height(base_dims, hs_ref, haunch_start)
        hs_poly = i_section_polygon(hs_dims)
        for dy in haunch_profile_offsets(base_depth, hs_dims.get('depth', base_depth), haunch_start.get('haunchPosition')):
            outer_poly = translate_polygon2(offset_polygon2(hs_poly, dy), dx=ex_dx, dy=ex_dy)
            inner_poly = translate_polygon2(clamp_contact_polygon(offset_polygon2(hs_poly, dy), base_depth, haunch_start.get('haunchPosition'), dy), dx=ex_dx, dy=ex_dy)
            outer_poly = rotate_poly2(outer_poly, ang)
            inner_poly = rotate_poly2(inner_poly, ang)
            body_items.append(w.loft_brep_item([
                section_pts3_local(0.0, outer_poly),
                section_pts3_local(hs_len, inner_poly),
            ]))

    if he_active:
        he_ref = resolve_haunch_section_dims(sec, haunch_end, sections, beam_type)
        he_dims = apply_haunch_height(base_dims, he_ref, haunch_end)
        he_poly = i_section_polygon(he_dims)
        z0 = max(0.0, length - he_len)
        for dy in haunch_profile_offsets(base_depth, he_dims.get('depth', base_depth), haunch_end.get('haunchPosition')):
            outer_poly = translate_polygon2(offset_polygon2(he_poly, dy), dx=ex_dx, dy=ex_dy)
            inner_poly = translate_polygon2(clamp_contact_polygon(offset_polygon2(he_poly, dy), base_depth, haunch_end.get('haunchPosition'), dy), dx=ex_dx, dy=ex_dy)
            outer_poly = rotate_poly2(outer_poly, ang)
            inner_poly = rotate_poly2(inner_poly, ang)
            body_items.append(w.loft_brep_item([
                section_pts3_local(z0, inner_poly),
                section_pts3_local(length, outer_poly),
            ]))

    placement = w.local_placement(None, start, beam_dir, section_x)
    local_axis_pts = [[0.0, 0.0, 0.0], [0.0, 0.0, length]]
    shape = w.shape_axis_and_body_items(local_axis_pts, body_items, body_type='Brep')
    return shape, placement, True


def linear_body_shape(w: IfcWriter, el: dict, start, end, sec: dict, beam_type: str, sec_name: str, sec_end: dict | None = None, sec_end_name: str | None = None):
    combo_shape, combo_placement, combo_ok = combined_body_shape(w, el, start, end, sec, beam_type, sec_name, sec_end, sec_end_name)
    if combo_ok:
        return combo_shape, combo_placement
    axis_vec = vec_sub(end, start)
    length = vec_len(axis_vec)
    if length < 1e-9:
        return w.shape_axis_curve([start, end]), None
    beam_dir = vec_norm(axis_vec)
    up_ref = [0.0, 0.0, 1.0]
    if abs(vec_dot(beam_dir, up_ref)) > 0.999:
        up_ref = [1.0, 0.0, 0.0]
    section_x = vec_norm(vec_cross(up_ref, beam_dir))
    if vec_len(section_x) < 1e-9:
        section_x = [1.0, 0.0, 0.0]
    placement = w.local_placement(None, start, beam_dir, section_x)
    dims = default_linear_dims(sec, beam_type)
    profile = w.profile_from_dims(sec_name or 'Profile', dims)
    ex_dy, ex_dz = oriented_section_translation_local(el, dims)
    ang = section_orientation_angle_rad(el)
    solid_refdir = [math.cos(ang), math.sin(ang), 0.0]
    solid_pos = w.axis2placement3d([f3(ex_dy), f3(ex_dz), 0], [0, 0, 1], solid_refdir)
    is_variable = str(beam_type).lower() == 'variablebeam' and sec_end
    if is_variable:
        end_dims = default_linear_dims(sec_end, beam_type)
        end_profile = w.profile_from_dims(sec_end_name or 'ProfileEnd', end_dims)
        body = w.extruded_profile_solid_tapered(profile, end_profile, solid_pos, length, axis_dir=(0, 0, 1))
    else:
        body = w.extruded_profile_solid(profile, solid_pos, length, axis_dir=(0, 0, 1))
    local_axis_pts = [[0.0, 0.0, 0.0], [0.0, 0.0, length]]
    shape = w.shape_axis_and_body(local_axis_pts, body)
    return shape, placement

def add_linear_product(w: IfcWriter, el, materials, sections):
    start = point3(el["geomPtStart"])
    end = point3(el["geomPtEnd"])
    sec = sections.get(eid_value(el.get("section"))) or {}
    sec_end = sections.get(eid_value(el.get("sectionEnd"))) or {}
    mat = materials.get(eid_value(el.get("material"))) or {}
    if mat.get("name"):
        sec = dict(sec)
        sec.setdefault("materialName", mat.get("name"))
        if sec_end:
            sec_end = dict(sec_end)
            sec_end.setdefault("materialName", mat.get("name"))
    sec_name = sec.get("name")
    sec_end_name = sec_end.get("name")
    beam_type = el.get("generalBeamType") or ""
    haunch_start = el.get("haunchStart") or {}
    haunch_end = el.get("haunchEnd") or {}
    has_local_haunch = str(beam_type).lower() != 'variablebeam' and is_i_or_h_catalog_section(sec) and (
        str(haunch_start.get('haunchPosition') or '').lower() != 'no_haunch' or
        str(haunch_end.get('haunchPosition') or '').lower() != 'no_haunch'
    )
    haunch_exported = False
    if has_local_haunch:
        shape, placement, haunch_exported = linear_haunch_body_shape(w, el, start, end, sec, beam_type, sec_name, haunch_start, haunch_end, sections)
    else:
        shape, placement = None, None
    if shape is None:
        shape, placement = linear_body_shape(w, el, start, end, sec, beam_type, sec_name, sec_end, sec_end_name)
    role = str(beam_type).lower()
    entity = "IFCBEAM"
    if any(x in role for x in ["column", "bar", "strut"]):
        entity = "IFCCOLUMN"
    elif any(x in role for x in ["tie", "cable"]):
        entity = "IFCMEMBER"
    name = f"Linear_{el.get('userID', 'NA')}"
    product = w.add(
        entity,
        w.s(guid22()),
        w.owner_history,
        w.s(name),
        w.s(el.get("type")),
        "$",
        placement,
        shape,
        "$",
        ".NOTDEFINED.",
    )
    w.contained.append(product)
    w.assign_material(product, mat.get("name"))
    debug_option = section_excentration_option_normalized(el)
    debug_dims = default_linear_dims(sec, beam_type)
    debug_dy, debug_dz = section_excentration_translation_local(el, debug_dims)
    if parse_combined_section(sec):
        combo_def = combined_member_polygons(parse_combined_section(sec)) or {}
        debug_polys = combo_def.get('polygons') or []
        debug_dy, debug_dz = section_excentration_translation_from_bounds(el, polygon_set_bounds(debug_polys))
    w.add_pset(product, "Pset_AD_Metadata", {
        "AD_Type": el.get("type"),
        "AD_UserID": el.get("userID"),
        "AD_GeneralBeamType": beam_type,
        "AD_LinearElementType": el.get("linearElementType"),
        "AD_Material": mat.get("name"),
        "AD_Section": sec_name,
        "AD_SectionType": sec.get("type"),
        "AD_SectionEnd": sec_end_name,
        "AD_SectionEndType": sec_end.get("type"),
        "AD_HasSectionEnd": bool(sec_end),
        "AD_IsTaperedExport": str(beam_type).lower() == 'variablebeam' and bool(sec_end),
        "AD_HaunchStartPosition": haunch_start.get("haunchPosition"),
        "AD_HaunchEndPosition": haunch_end.get("haunchPosition"),
        "AD_HaunchExported": haunch_exported,
        "AD_HaunchStartDisplaySectionType": ('identical' if str(haunch_start.get('haunchSectionType') or '').lower() in ('precedent', 'suivant') else haunch_start.get('haunchSectionType')),
        "AD_HaunchEndDisplaySectionType": ('identical' if str(haunch_end.get('haunchSectionType') or '').lower() in ('precedent', 'suivant') else haunch_end.get('haunchSectionType')),
        "AD_RelaxationExported": False,
        "AD_CombinedSection": bool(parse_combined_section(sec)),
        "AD_CombinedSectionCode": (parse_combined_section(sec) or {}).get("code"),
        "AD_SectionExcentrationOption": debug_option,
        "AD_SectionOffsetYZ": f"{f3(debug_dy)},{f3(debug_dz)}",
        "AD_SectionOrientationAngleDeg": section_orientation_angle_deg(el),
    })


def add_planar_product(w: IfcWriter, el, materials):
    pts3 = [point3(p) for p in el.get("geomPtsList") or []]
    if len(pts3) < 3:
        return
    origin, u, v, n = planar_basis(pts3)
    pts2 = [to_local_2d(p, origin, u, v) for p in pts3]
    thickness = float(el.get("thicknessIn1stVertex") or 0.2)
    placement = w.local_placement(None, origin, n, u)
    solid_pos = w.axis2placement3d([0, 0, 0], [0, 0, 1], [1, 0, 0])
    shape = w.extruded_closed_body(pts2, max(thickness, 0.001), solid_pos)
    el_type = str(el.get("elementType") or "").lower()
    if "wall" in el_type:
        entity = "IFCWALL"
    else:
        entity = "IFCSLAB"
    name = f"Planar_{el.get('userID', 'NA')}"
    type_enum = ".NOTDEFINED."
    product = w.add(
        entity,
        w.s(guid22()),
        w.owner_history,
        w.s(name),
        w.s(el.get("type")),
        "$",
        placement,
        shape,
        "$",
        type_enum,
    )
    w.contained.append(product)
    mat = materials.get(eid_value(el.get("material"))) or {}
    w.assign_material(product, mat.get("name"))
    w.add_pset(product, "Pset_AD_Metadata", {
        "AD_Type": el.get("type"),
        "AD_UserID": el.get("userID"),
        "AD_PlanarType": el.get("elementType"),
        "AD_Thickness": thickness,
        "AD_Material": mat.get("name"),
        "AD_SupportingElement": el.get("supportingElement"),
    })
    openings = el.get("openings") or []
    for idx, opening in enumerate(openings, start=1):
        opt3 = [point3(p) for p in opening]
        if len(opt3) < 3:
            continue
        opt2 = [to_local_2d(p, origin, u, v) for p in opt3]
        oshape = w.extruded_closed_body(opt2, max(thickness * 1.05, 0.001), solid_pos)
        op = w.add(
            "IFCOPENINGELEMENT",
            w.s(guid22()),
            w.owner_history,
            w.s(f"Opening_{el.get('userID', 'NA')}_{idx}"),
            w.s("Advance Design opening"),
            "$",
            placement,
            oshape,
            "$",
        )
        w.add("IFCRELVOIDSELEMENT", w.s(guid22()), w.owner_history, "$", "$", product, op)
        w.add_pset(op, "Pset_AD_Metadata", {
            "AD_HostUserID": el.get("userID"),
            "AD_OpeningIndex": idx,
        })


def add_punctual_support(w: IfcWriter, el):
    p = point3(el.get("geomPt") or {})
    size = 0.20
    height = 0.20
    placement = w.local_placement(None, p, [0, 0, 1], [1, 0, 0])
    shape = w.pyramid_body(size, height)
    name = f"Support_{el.get('userID', 'NA')}"
    product = w.add(
        "IFCBUILDINGELEMENTPROXY",
        w.s(guid22()),
        w.owner_history,
        w.s(name),
        w.s(el.get("type")),
        "$",
        placement,
        shape,
        "$",
        "$",
    )
    w.contained.append(product)
    constraints = el.get("constraintsType") or "Rigid"
    restraints = el.get("restraints") or {}
    w.add_pset(product, "Pset_AD_Support", {
        "AD_Type": el.get("type"),
        "AD_ConstraintsType": constraints,
        "AD_Tx": restraints.get("tx"),
        "AD_Ty": restraints.get("ty"),
        "AD_Tz": restraints.get("tz"),
        "AD_Rx": restraints.get("rx"),
        "AD_Ry": restraints.get("ry"),
        "AD_Rz": restraints.get("rz"),
    })


def support_sample_points_linear(start, end, spacing=0.50):
    vec = vec_sub(end, start)
    length = vec_len(vec)
    if length < 1e-9:
        return [start]
    nseg = max(1, int(math.ceil(length / float(spacing))))
    pts = []
    for i in range(nseg + 1):
        t = i / nseg
        pts.append([
            start[0] + vec[0] * t,
            start[1] + vec[1] * t,
            start[2] + vec[2] * t,
        ])
    return pts


def support_pyramid_items(w: IfcWriter, points, base_size=0.20, height=0.20):
    return [w.pyramid_brep_item(p, base_size, height) for p in points]


def add_linear_support(w: IfcWriter, el):
    start = point3(el.get("geomPtStart") or {})
    end = point3(el.get("geomPtEnd") or {})
    constraints = el.get("constraintsType") or "Rigid"
    restraints = el.get("restraints") or {}
    pts = support_sample_points_linear(start, end, spacing=0.50)
    body_items = support_pyramid_items(w, pts, base_size=0.20, height=0.20)
    placement = w.local_placement(None, [0, 0, 0])
    shape = w.shape_axis_and_body_items([start, end], body_items, body_type='Brep')
    product = w.add(
        "IFCBUILDINGELEMENTPROXY",
        w.s(guid22()),
        w.owner_history,
        w.s(f"Support_{el.get('userID', 'NA')}"),
        w.s(el.get("type")),
        "$",
        placement,
        shape,
        "$",
        "$",
    )
    w.contained.append(product)
    w.add_pset(product, "Pset_AD_Support", {
        "AD_Type": el.get("type"),
        "AD_ConstraintsType": constraints,
        "AD_Tx": restraints.get("tx"),
        "AD_Ty": restraints.get("ty"),
        "AD_Tz": restraints.get("tz"),
        "AD_Rx": restraints.get("rx"),
        "AD_Ry": restraints.get("ry"),
        "AD_Rz": restraints.get("rz"),
    })


def add_planar_support(w: IfcWriter, el):
    pts3 = [point3(p) for p in el.get("geomPtsList") or []]
    if len(pts3) < 3:
        return
    constraints = el.get("constraintsType") or "Rigid"
    restraints = el.get("restraints") or {}
    origin, u, v, n = planar_basis(pts3)
    plate = w.planar_plate_brep_item(pts3, 0.05, n)
    pyramids = support_pyramid_items(w, pts3, base_size=0.20, height=0.20)
    body_items = [plate] + pyramids
    placement = w.local_placement(None, [0, 0, 0])
    shape = w.shape_body_items(body_items, body_type='Brep')
    product = w.add(
        "IFCBUILDINGELEMENTPROXY",
        w.s(guid22()),
        w.owner_history,
        w.s(f"Support_{el.get('userID', 'NA')}"),
        w.s(el.get("type")),
        "$",
        placement,
        shape,
        "$",
        "$",
    )
    w.contained.append(product)
    w.add_pset(product, "Pset_AD_Support", {
        "AD_Type": el.get("type"),
        "AD_ConstraintsType": constraints,
        "AD_Tx": restraints.get("tx"),
        "AD_Ty": restraints.get("ty"),
        "AD_Tz": restraints.get("tz"),
        "AD_Rx": restraints.get("rx"),
        "AD_Ry": restraints.get("ry"),
        "AD_Rz": restraints.get("rz"),
    })


def add_explicit_load_proxy(w: IfcWriter, el):
    t = el.get("type")
    if t == "ElementLoadPunctual":
        p = point3(el.get("geomPt") or {})
        placement = w.local_placement(None, p, [0, 0, 1], [1, 0, 0])
        solid_pos = w.axis2placement3d([0, 0, 0], [0, 0, 1], [1, 0, 0])
        pts2 = [[-0.04, -0.04], [0.04, -0.04], [0.04, 0.04], [-0.04, 0.04]]
        shape = w.extruded_closed_body(pts2, 0.12, solid_pos)
    elif t == "ElementLoadLinear":
        start = point3(el.get("geomPtStart") or {})
        end = point3(el.get("geomPtEnd") or {})
        placement = w.local_placement(None, [0, 0, 0])
        shape = w.shape_axis_curve([start, end])
    elif t == "ElementLoadPlanar":
        pts3 = [point3(p) for p in el.get("geomPtsList") or []]
        if len(pts3) < 3:
            return
        origin, u, v, n = planar_basis(pts3)
        pts2 = [to_local_2d(p, origin, u, v) for p in pts3]
        placement = w.local_placement(None, origin, n, u)
        solid_pos = w.axis2placement3d([0, 0, 0], [0, 0, 1], [1, 0, 0])
        shape = w.extruded_closed_body(pts2, 0.02, solid_pos)
    else:
        p = point3(el.get("geomPt") or {"x": 0, "y": 0, "z": 0})
        placement = w.local_placement(None, p, [0, 0, 1], [1, 0, 0])
        solid_pos = w.axis2placement3d([0, 0, 0], [0, 0, 1], [1, 0, 0])
        pts2 = [[-0.03, -0.03], [0.03, -0.03], [0.03, 0.03], [-0.03, 0.03]]
        shape = w.extruded_closed_body(pts2, 0.08, solid_pos)
    product = w.add(
        "IFCBUILDINGELEMENTPROXY",
        w.s(guid22()),
        w.owner_history,
        w.s(f"Load_{el.get('userID', 'NA')}"),
        w.s(t),
        "$",
        placement,
        shape,
        "$",
        "$",
    )
    w.contained.append(product)
    moment = el.get("moment") or {}
    w.add_pset(product, "Pset_AD_Load", {
        "AD_Type": t,
        "AD_UserID": el.get("userID"),
        "AD_LoadCase": eid_value(el.get("loadCase")),
        "AD_Fx": el.get("fx"),
        "AD_Fy": el.get("fy"),
        "AD_Fz": el.get("fz"),
        "AD_Mx": moment.get("mx"),
        "AD_My": moment.get("my"),
        "AD_Mz": moment.get("mz"),
        "AD_Dx": el.get("dx"),
        "AD_Dy": el.get("dy"),
        "AD_Dz": el.get("dz"),
        "AD_Rx": el.get("rx"),
        "AD_Ry": el.get("ry"),
        "AD_Rz": el.get("rz"),
    })


def collect_all(host: str, include_loads: bool, element_ids=None):
    allowed = None
    if element_ids is not None:
        allowed = set()
        for e in element_ids:
            try:
                allowed.add(int(e))
            except (TypeError, ValueError):
                pass
    results = defaultdict(list)
    for t in LINEAR_TYPES + PLANAR_TYPES + SUPPORT_TYPES + (LOAD_TYPES if include_loads else []):
        ids = get_ids_for_type(host, t)
        if allowed is not None:
            filtered = []
            for i in ids:
                try:
                    val = int(eid_value(i))
                except (TypeError, ValueError):
                    continue
                if val in allowed:
                    filtered.append(i)
            ids = filtered
        results[t] = get_elements(host, ids)
    return results


def export_ifc(host: str, fto: str, out_path: str, include_loads: bool):
    open_project(host, fto)
    try:
        materials = get_materials(host)
        sections = get_sections(host)
        elems = collect_all(host, include_loads)
        w = IfcWriter()
        w.setup(project_name=os.path.basename(fto))
        for el in elems["ElementLinear"]:
            add_linear_product(w, el, materials, sections)
        for el in elems["ElementPlanar"]:
            add_planar_product(w, el, materials)
        for t in SUPPORT_TYPES:
            for el in elems[t]:
                if "Punctual" in t:
                    add_punctual_support(w, el)
                elif "Linear" in t:
                    add_linear_support(w, el)
                else:
                    add_planar_support(w, el)
        if include_loads:
            for t in LOAD_TYPES:
                for el in elems[t]:
                    add_explicit_load_proxy(w, el)
        text = w.finish()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    finally:
        close_project(host)


def emit_log(logger, message: str, level: str = "info") -> None:
    if callable(logger):
        try:
            logger(message, level)
            return
        except TypeError:
            try:
                logger(message)
                return
            except Exception:
                return
        except Exception:
            return


def export_ifc_core(host: str, out_path: str, include_loads: bool = False, project_name: str | None = None, logger=None, element_ids=None) -> dict:
    emit_log(logger, f"Export IFC v{VERSION} : lecture des matériaux et sections...", "info")
    materials = get_materials(host)
    sections = get_sections(host)
    if element_ids is not None:
        emit_log(logger, f"Lecture des éléments du modèle (sélection : {len(element_ids)} élément(s))...", "info")
    else:
        emit_log(logger, "Lecture des éléments du modèle...", "info")
    elems = collect_all(host, include_loads, element_ids=element_ids)
    emit_log(logger, "Génération du contenu IFC...", "info")
    w = IfcWriter()
    w.setup(project_name=project_name or os.path.basename(out_path))
    for el in elems["ElementLinear"]:
        add_linear_product(w, el, materials, sections)
    for el in elems["ElementPlanar"]:
        add_planar_product(w, el, materials)
    for t in SUPPORT_TYPES:
        for el in elems[t]:
            if "Punctual" in t:
                add_punctual_support(w, el)
            elif "Linear" in t:
                add_linear_support(w, el)
            else:
                add_planar_support(w, el)
    if include_loads:
        for t in LOAD_TYPES:
            for el in elems[t]:
                add_explicit_load_proxy(w, el)
    text = w.finish()
    out_path = os.path.abspath(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    emit_log(logger, f"Export IFC terminé : {out_path}", "ok")
    return {
        "success": True,
        "version": VERSION,
        "host": host,
        "out_path": out_path,
        "project_name": project_name or os.path.basename(out_path),
        "include_loads": bool(include_loads),
    }


def export_ifc_from_fto(host: str, fto_path: str, out_path: str, include_loads: bool = False, logger=None, check_api_first: bool = True, close_project_on_exit: bool = True, element_ids=None) -> dict:
    host = str(host or DEFAULT_HOST).rstrip("/")
    fto_path = check_fto_path(fto_path)
    if check_api_first:
        emit_log(logger, f"Vérification de l'accessibilité de l'API ({host})...", "info")
        check_port(host)
        emit_log(logger, "API accessible.", "ok")
    emit_log(logger, f"Ouverture du projet : {fto_path}", "info")
    open_project(host, fto_path)
    try:
        return export_ifc_core(host, out_path, include_loads=include_loads, project_name=os.path.basename(fto_path), logger=logger, element_ids=element_ids)
    finally:
        if close_project_on_exit:
            close_project(host)


def export_ifc_from_open_project(host: str, out_path: str, include_loads: bool = False, project_name: str = "ViewerProject", logger=None, check_api_first: bool = True, element_ids=None) -> dict:
    host = str(host or DEFAULT_HOST).rstrip("/")
    if check_api_first:
        emit_log(logger, f"Vérification de l'accessibilité de l'API ({host})...", "info")
        check_port(host)
        emit_log(logger, "API accessible.", "ok")
    return export_ifc_core(host, out_path, include_loads=include_loads, project_name=project_name, logger=logger, element_ids=element_ids)


def get_version() -> str:
    return VERSION


__all__ = [
    "VERSION",
    "DEFAULT_HOST",
    "DEFAULT_OUT",
    "ApiUnavailableError",
    "ProjectAlreadyOpenError",
    "check_port",
    "check_fto_path",
    "open_project",
    "close_project",
    "export_ifc_core",
    "export_ifc_from_fto",
    "export_ifc_from_open_project",
    "emit_log",
    "get_version",
]
