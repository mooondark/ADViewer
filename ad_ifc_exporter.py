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

DEFAULT_HOST = "http://localhost:52000"
DEFAULT_OUT = "export_advance_design_ifc_v3.ifc"
VERSION = "4.6.17"

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

    def t_profile_polygon(self, dims):
        b = float(dims.get('width', 0.20))
        h = float(dims.get('depth', 0.30))
        tw = min(float(dims.get('web', max(b * 0.2, 0.01))), b * 0.95)
        tf = min(float(dims.get('flange', max(h * 0.15, 0.01))), h * 0.45)
        return [
            [-b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0 - tf],
            [ tw / 2.0, h / 2.0 - tf],
            [ tw / 2.0, -h / 2.0],
            [-tw / 2.0, -h / 2.0],
            [-tw / 2.0, h / 2.0 - tf],
            [-b / 2.0,  h / 2.0 - tf],
        ]
    def t_dissym_profile_polygon(self, dims):
        h = float(dims.get('depth', 0.30))
        web = float(dims.get('web', 0.10))
        left_w = float(dims.get('left_width', 0.05))
        left_t = float(dims.get('left_thickness', 0.05))
        left_off = float(dims.get('left_offset', 0.15))
        right_w = float(dims.get('right_width', 0.05))
        right_t = float(dims.get('right_thickness', 0.05))
        right_off = float(dims.get('right_offset', 0.15))

        y_top = h / 2.0
        y_bot = -h / 2.0
        x_left = -web / 2.0
        x_right = web / 2.0

        left_c = y_top - left_off
        right_c = y_top - right_off
        left_top = left_c + left_t / 2.0
        left_bot = left_c - left_t / 2.0
        right_top = right_c + right_t / 2.0
        right_bot = right_c - right_t / 2.0

        pts = [
            [x_left, y_top],
            [x_right, y_top],
            [x_right, right_top],
            [x_right + right_w, right_top],
            [x_right + right_w, right_bot],
            [x_right, right_bot],
            [x_right, y_bot],
            [x_left, y_bot],
            [x_left, left_bot],
            [x_left - left_w, left_bot],
            [x_left - left_w, left_top],
            [x_left, left_top],
        ]
        return pts

    def l_profile_polygon(self, dims):
        b = float(dims.get('width', 0.10))
        h = float(dims.get('depth', b))
        t = min(float(dims.get('thickness', max(min(b, h) * 0.15, 0.008))), min(b, h) * 0.8)
        return [
            [-b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0 - t],
            [-b / 2.0 + t, h / 2.0 - t],
            [-b / 2.0 + t, -h / 2.0],
            [-b / 2.0, -h / 2.0],
        ]

    def u_profile_polygon(self, dims):
        b = float(dims.get('width', 0.20))
        h = float(dims.get('depth', 0.30))
        tw = min(float(dims.get('web', max(b * 0.15, 0.01))), b * 0.8)
        tf = min(float(dims.get('flange', max(h * 0.15, 0.01))), h * 0.45)
        x0 = -b / 2.0
        x1 = x0 + tw
        y0 = -h / 2.0
        y1 = h / 2.0
        return [
            [x0, y1],
            [ b / 2.0, y1],
            [ b / 2.0, y1 - tf],
            [x1, y1 - tf],
            [x1, y0 + tf],
            [ b / 2.0, y0 + tf],
            [ b / 2.0, y0],
            [x0, y0],
        ]

    def zed_profile_polygon(self, dims):
        h = float(dims.get('depth', 0.20))
        b_top = float(dims.get('top_flange_width', 0.06))
        b_bot = float(dims.get('bottom_flange_width', 0.06))
        t = min(float(dims.get('thickness', 0.002)), max(0.001, min(h, max(b_top, b_bot)) * 0.49))
        rt = max(0.0, float(dims.get('top_return', 0.0)))
        rb = max(0.0, float(dims.get('bottom_return', 0.0)))
        ang_top = float(dims.get('top_return_angle_deg', 90.0))
        ang_bot = float(dims.get('bottom_return_angle_deg', 90.0))

        y_top = h / 2.0 - t / 2.0
        y_bot = -h / 2.0 + t / 2.0
        x_web = 0.0
        x_top = b_top
        x_bot = -b_bot

        centerline = []
        if rt > 1e-9:
            a = math.radians(ang_top)
            centerline.append([x_top + rt * math.cos(a), y_top - rt * math.sin(a)])
        centerline += [
            [x_top, y_top],
            [x_web, y_top],
            [x_web, y_bot],
            [x_bot, y_bot],
        ]
        if rb > 1e-9:
            a = math.radians(ang_bot)
            centerline.append([x_bot - rb * math.cos(a), y_bot + rb * math.sin(a)])

        def seg_normal(p0, p1, side):
            dx = float(p1[0]) - float(p0[0])
            dy = float(p1[1]) - float(p0[1])
            ln = max((dx * dx + dy * dy) ** 0.5, 1e-12)
            return [side * (-dy / ln), side * (dx / ln)]

        def line_intersection(a0, a1, b0, b1):
            x1, y1 = a0
            x2, y2 = a1
            x3, y3 = b0
            x4, y4 = b1
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                return [(a1[0] + b0[0]) / 2.0, (a1[1] + b0[1]) / 2.0]
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
            return [px, py]

        def offset_open_polyline(poly, dist, side):
            n = len(poly)
            out = []
            for i in range(n):
                p = [float(poly[i][0]), float(poly[i][1])]
                if i == 0:
                    n0 = seg_normal(poly[0], poly[1], side)
                    out.append([p[0] + dist * n0[0], p[1] + dist * n0[1]])
                    continue
                if i == n - 1:
                    n1 = seg_normal(poly[-2], poly[-1], side)
                    out.append([p[0] + dist * n1[0], p[1] + dist * n1[1]])
                    continue
                n_prev = seg_normal(poly[i - 1], poly[i], side)
                n_next = seg_normal(poly[i], poly[i + 1], side)
                a0 = [float(poly[i - 1][0]) + dist * n_prev[0], float(poly[i - 1][1]) + dist * n_prev[1]]
                a1 = [float(poly[i][0]) + dist * n_prev[0], float(poly[i][1]) + dist * n_prev[1]]
                b0 = [float(poly[i][0]) + dist * n_next[0], float(poly[i][1]) + dist * n_next[1]]
                b1 = [float(poly[i + 1][0]) + dist * n_next[0], float(poly[i + 1][1]) + dist * n_next[1]]
                out.append(line_intersection(a0, a1, b0, b1))
            return out

        left = offset_open_polyline(centerline, t / 2.0, 1.0)
        right = offset_open_polyline(centerline, t / 2.0, -1.0)
        poly = left + list(reversed(right))

        cleaned = []
        for p in poly:
            if not cleaned or abs(p[0] - cleaned[-1][0]) > 1e-9 or abs(p[1] - cleaned[-1][1]) > 1e-9:
                cleaned.append([float(p[0]), float(p[1])])
        if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) < 1e-9 and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-9:
            cleaned.pop()
        return cleaned

    def omega_profile_polygon(self, dims):
        h = float(dims.get('depth', 0.14))
        b = float(dims.get('width', 0.06))
        top_b = float(dims.get('top_flange_width', b))
        t = min(float(dims.get('thickness', 0.002)), max(0.001, min(h, max(b, top_b)) * 0.49))

        y_top = h / 2.0 - t / 2.0
        y_bot = -h / 2.0 + t / 2.0
        x0 = -(top_b / 2.0 + b)
        x1 = -top_b / 2.0
        x2 = top_b / 2.0
        x3 = top_b / 2.0 + b

        centerline = [
            [x0, y_bot],
            [x1, y_bot],
            [x1, y_top],
            [x2, y_top],
            [x2, y_bot],
            [x3, y_bot],
        ]

        def seg_normal(p0, p1, side):
            dx = float(p1[0]) - float(p0[0])
            dy = float(p1[1]) - float(p0[1])
            ln = max((dx * dx + dy * dy) ** 0.5, 1e-12)
            return [side * (-dy / ln), side * (dx / ln)]

        def line_intersection(a0, a1, b0, b1):
            x1, y1 = a0
            x2, y2 = a1
            x3, y3 = b0
            x4, y4 = b1
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                return [(a1[0] + b0[0]) / 2.0, (a1[1] + b0[1]) / 2.0]
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
            return [px, py]

        def offset_open_polyline(poly, dist, side):
            n = len(poly)
            out = []
            for i in range(n):
                p = [float(poly[i][0]), float(poly[i][1])]
                if i == 0:
                    n0 = seg_normal(poly[0], poly[1], side)
                    out.append([p[0] + dist * n0[0], p[1] + dist * n0[1]])
                    continue
                if i == n - 1:
                    n1 = seg_normal(poly[-2], poly[-1], side)
                    out.append([p[0] + dist * n1[0], p[1] + dist * n1[1]])
                    continue
                n_prev = seg_normal(poly[i - 1], poly[i], side)
                n_next = seg_normal(poly[i], poly[i + 1], side)
                a0 = [float(poly[i - 1][0]) + dist * n_prev[0], float(poly[i - 1][1]) + dist * n_prev[1]]
                a1 = [float(poly[i][0]) + dist * n_prev[0], float(poly[i][1]) + dist * n_prev[1]]
                b0 = [float(poly[i][0]) + dist * n_next[0], float(poly[i][1]) + dist * n_next[1]]
                b1 = [float(poly[i + 1][0]) + dist * n_next[0], float(poly[i + 1][1]) + dist * n_next[1]]
                out.append(line_intersection(a0, a1, b0, b1))
            return out

        left = offset_open_polyline(centerline, t / 2.0, 1.0)
        right = offset_open_polyline(centerline, t / 2.0, -1.0)
        poly = left + list(reversed(right))

        cleaned = []
        for p in poly:
            if not cleaned or abs(p[0] - cleaned[-1][0]) > 1e-9 or abs(p[1] - cleaned[-1][1]) > 1e-9:
                cleaned.append([float(p[0]), float(p[1])])
        if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) < 1e-9 and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-9:
            cleaned.pop()
        return cleaned

    def sigma_profile_polygon(self, dims):
        h = float(dims.get('depth', 0.32))
        b = float(dims.get('width', 0.08))
        hi = max(0.0, float(dims.get('inner_web_height', 0.08)))
        he = max(0.0, float(dims.get('outer_web_height', 0.045)))
        off = float(dims.get('web_offset', 0.016))
        lip = max(0.0, float(dims.get('return_lip', 0.04)))
        t = min(float(dims.get('thickness', 0.003)), max(0.001, min(h, b) * 0.49))

        web_remaining = max(0.0, h - 2.0 * he - hi)
        diag_h = web_remaining / 2.0
        x0 = 0.0
        x1 = off
        y_top = h / 2.0
        y_bot = -h / 2.0
        y1 = y_top - he
        y2 = y1 - diag_h
        y3 = y2 - hi
        y4 = y_bot + he

        centerline = [
            [b, y_top - lip],
            [b, y_top],
            [x0, y_top],
            [x0, y1],
            [x1, y2],
            [x1, y3],
            [x0, y4],
            [x0, y_bot],
            [b, y_bot],
            [b, y_bot + lip],
        ]

        def seg_normal(p0, p1, side):
            dx = float(p1[0]) - float(p0[0])
            dy = float(p1[1]) - float(p0[1])
            ln = max((dx * dx + dy * dy) ** 0.5, 1e-12)
            return [side * (-dy / ln), side * (dx / ln)]

        def line_intersection(a0, a1, b0, b1):
            x1, y1 = a0
            x2, y2 = a1
            x3, y3 = b0
            x4, y4 = b1
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                return [(a1[0] + b0[0]) / 2.0, (a1[1] + b0[1]) / 2.0]
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
            return [px, py]

        def offset_open_polyline(poly, dist, side):
            n = len(poly)
            out = []
            for i in range(n):
                p = [float(poly[i][0]), float(poly[i][1])]
                if i == 0:
                    n0 = seg_normal(poly[0], poly[1], side)
                    out.append([p[0] + dist * n0[0], p[1] + dist * n0[1]])
                    continue
                if i == n - 1:
                    n1 = seg_normal(poly[-2], poly[-1], side)
                    out.append([p[0] + dist * n1[0], p[1] + dist * n1[1]])
                    continue
                n_prev = seg_normal(poly[i - 1], poly[i], side)
                n_next = seg_normal(poly[i], poly[i + 1], side)
                a0 = [float(poly[i - 1][0]) + dist * n_prev[0], float(poly[i - 1][1]) + dist * n_prev[1]]
                a1 = [float(poly[i][0]) + dist * n_prev[0], float(poly[i][1]) + dist * n_prev[1]]
                b0 = [float(poly[i][0]) + dist * n_next[0], float(poly[i][1]) + dist * n_next[1]]
                b1 = [float(poly[i + 1][0]) + dist * n_next[0], float(poly[i + 1][1]) + dist * n_next[1]]
                out.append(line_intersection(a0, a1, b0, b1))
            return out

        left = offset_open_polyline(centerline, t / 2.0, 1.0)
        right = offset_open_polyline(centerline, t / 2.0, -1.0)
        poly = left + list(reversed(right))

        cleaned = []
        for p in poly:
            if not cleaned or abs(p[0] - cleaned[-1][0]) > 1e-9 or abs(p[1] - cleaned[-1][1]) > 1e-9:
                cleaned.append([float(p[0]), float(p[1])])
        if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) < 1e-9 and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-9:
            cleaned.pop()
        return cleaned

    def angle_profile_polygon(self, dims):
        b = float(dims.get('width', 0.10))
        h = float(dims.get('depth', b))
        t = min(float(dims.get('thickness', max(min(b, h) * 0.15, 0.008))), min(b, h) * 0.8)
        return [
            [-b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0],
            [ b / 2.0,  h / 2.0 - t],
            [-b / 2.0 + t, h / 2.0 - t],
            [-b / 2.0 + t, -h / 2.0],
            [-b / 2.0, -h / 2.0],
        ]

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
            return self.arbitrary_profile_def(name or 'TProfile', self.t_profile_polygon(dims))
        if kind == 'TDISSYMETRIC':
            return self.arbitrary_profile_def(name or 'TDissymProfile', self.t_dissym_profile_polygon(dims))
        if kind == 'U':
            return self.arbitrary_profile_def(name or 'UProfile', self.u_profile_polygon(dims))
        if kind in {'Z', 'ZED', 'ZED_SLOPED'}:
            return self.arbitrary_profile_def(name or 'ZedProfile', self.zed_profile_polygon(dims))
        if kind == 'OMEGA':
            return self.arbitrary_profile_def(name or 'OmegaProfile', self.omega_profile_polygon(dims))
        if kind == 'SIGMA':
            return self.arbitrary_profile_def(name or 'SigmaProfile', self.sigma_profile_polygon(dims))
        if kind == 'ANGLE':
            return self.arbitrary_profile_def(name or 'AngleProfile', self.l_profile_polygon(dims))
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


def is_steel_material_name(name):
    txt = (name or '').upper().strip()
    return bool(re.search(r'\bS\d{3}\b', txt)) or any(tag in txt for tag in ['STEEL', 'ACIER', 'METAL'])


def parse_section_dims(sec: dict):
    name = (sec.get("name") or "").upper().strip()
    sec_type = re.sub(r"[^A-Z0-9]", "", (sec.get("type") or "").upper())
    family = (sec.get("familyCode") or "").upper().strip()
    catalog = (sec.get("catalogName") or "").upper().strip()
    material_name = (sec.get("materialName") or sec.get("material") or "").upper().strip()
    raw = " ".join([name, family, catalog]).strip()
    nums_cm = [float(x.replace(',', '.')) for x in re.findall(r"(\d+(?:[.,]\d+)?)", raw)]

    def pick_cm(i, default_cm):
        return nums_cm[i] if len(nums_cm) > i else default_cm

    def cm(v):
        return float(v) / 100.0

    def mm(v):
        return float(v) / 1000.0

    def clamp_thickness_m(t_m, *sizes_m):
        limit = min([s for s in sizes_m if s and s > 0] or [0.02]) * 0.49
        return max(0.001, min(t_m, limit))

    steel_by_name = is_steel_material_name(material_name)
    steel_by_family = any(tag in raw for tag in ['IPE', 'IPN', 'HEA', 'HEB', 'HEM', 'RHS', 'SHS', 'CHS'])
    steel_by_type = any(tag in sec_type for tag in ['ANGLE', 'I_SYMETRIC', 'IASYMETRIC', 'CIRCULARTUBE', 'RECTANGULARTUBE', 'SQUARETUBE', 'SIGMA'])
    steel_by_shape = bool(re.match(r'^L\s*\d+(?:[.,]\d+)?X\d+(?:[.,]\d+)?X\d+(?:[.,]\d+)?$', name))
    is_mm_metal = steel_by_name or steel_by_family or steel_by_type or steel_by_shape


    if name.startswith('V') or 'SIGMA' in sec_type or family.startswith('V'):
        if len(nums_cm) >= 8:
            h_cm, b_cm, hi_cm, he_cm, d_cm, r_cm, t_cm, ri_cm = nums_cm[:8]
            return {
                'kind': 'SIGMA',
                'width': cm(b_cm),
                'depth': cm(h_cm),
                'inner_web_height': cm(hi_cm),
                'outer_web_height': cm(he_cm),
                'web_offset': cm(d_cm),
                'return_lip': cm(r_cm),
                'thickness': clamp_thickness_m(cm(t_cm), cm(h_cm), cm(b_cm), cm(hi_cm), cm(he_cm), cm(r_cm)),
                'inner_radius': cm(ri_cm),
                'overall_width': cm(b_cm),
                'overall_depth': cm(h_cm),
            }
        return {
            'kind': 'SIGMA',
            'width': cm(pick_cm(1, 8.0)),
            'depth': cm(pick_cm(0, 32.0)),
            'inner_web_height': cm(pick_cm(2, 8.0)),
            'outer_web_height': cm(pick_cm(3, 4.5)),
            'web_offset': cm(pick_cm(4, 1.6)),
            'return_lip': cm(pick_cm(5, 4.0)),
            'thickness': clamp_thickness_m(cm(pick_cm(6, 0.3)), cm(pick_cm(0, 32.0)), cm(pick_cm(1, 8.0))),
            'inner_radius': cm(pick_cm(7, 0.2)),
            'overall_width': cm(pick_cm(1, 8.0)),
            'overall_depth': cm(pick_cm(0, 32.0)),
        }

    if name.startswith('W') or 'OMEGA' in sec_type or family.startswith('W'):
        if len(nums_cm) >= 5:
            h_cm, b_cm, top_b_cm, t_cm, r_cm = nums_cm[:5]
            return {
                'kind': 'OMEGA',
                'width': cm(b_cm),
                'depth': cm(h_cm),
                'top_flange_width': cm(top_b_cm),
                'thickness': clamp_thickness_m(cm(t_cm), cm(h_cm), cm(b_cm), cm(top_b_cm)),
                'fillet_radius': cm(r_cm),
                'overall_width': 2.0 * cm(b_cm) + cm(top_b_cm),
                'overall_depth': cm(h_cm),
            }
        return {
            'kind': 'OMEGA',
            'width': cm(pick_cm(1, 6.0)),
            'depth': cm(pick_cm(0, 14.0)),
            'top_flange_width': cm(pick_cm(2, pick_cm(1, 6.0))),
            'thickness': clamp_thickness_m(cm(pick_cm(3, 0.2)), cm(pick_cm(0, 14.0)), cm(pick_cm(1, 6.0)), cm(pick_cm(2, pick_cm(1, 6.0)))),
            'fillet_radius': cm(pick_cm(4, 0.2)),
            'overall_width': 2.0 * cm(pick_cm(1, 6.0)) + cm(pick_cm(2, pick_cm(1, 6.0))),
            'overall_depth': cm(pick_cm(0, 14.0)),
        }

    if name.startswith('Z') or 'ZED' in sec_type or family.startswith('Z'):
        z_raw = (sec.get("name") or "").upper().strip()
        z_parts = z_raw.split()
        z_geom = z_parts[0] if z_parts else ''
        z_suffix = z_parts[1] if len(z_parts) > 1 else ''
        z_main_nums = [float(x.replace(',', '.')) for x in re.findall(r"(\d+(?:[.,]\d+)?)", z_geom)]
        z_suffix_nums = [float(x.replace(',', '.')) for x in re.findall(r"(\d+(?:[.,]\d+)?)", z_suffix)]
        t_cm = z_suffix_nums[0] if z_suffix_nums else 0.2

        if len(z_main_nums) == 8:
            h_cm, btop_cm, bbot_cm, ri_cm, rtop_cm, rbot_cm, ang_bot_deg, ang_top_deg = z_main_nums
            return {
                'kind': 'ZED_SLOPED',
                'depth': cm(h_cm),
                'top_flange_width': cm(btop_cm),
                'bottom_flange_width': cm(bbot_cm),
                'thickness': clamp_thickness_m(cm(t_cm), cm(h_cm), cm(btop_cm), cm(bbot_cm)),
                'inner_radius': cm(ri_cm),
                'top_return': cm(rtop_cm),
                'bottom_return': cm(rbot_cm),
                'bottom_return_angle_deg': float(ang_bot_deg),
                'top_return_angle_deg': float(ang_top_deg),
                'overall_width': cm(btop_cm) + cm(bbot_cm),
                'overall_depth': cm(h_cm),
            }
        if len(z_main_nums) == 6:
            h_cm, btop_cm, bbot_cm, ri_cm, rtop_cm, rbot_cm = z_main_nums
            return {
                'kind': 'ZED',
                'depth': cm(h_cm),
                'top_flange_width': cm(btop_cm),
                'bottom_flange_width': cm(bbot_cm),
                'thickness': clamp_thickness_m(cm(t_cm), cm(h_cm), cm(btop_cm), cm(bbot_cm)),
                'inner_radius': cm(ri_cm),
                'top_return': cm(rtop_cm),
                'bottom_return': cm(rbot_cm),
                'bottom_return_angle_deg': 90.0,
                'top_return_angle_deg': 90.0,
                'overall_width': cm(btop_cm) + cm(bbot_cm),
                'overall_depth': cm(h_cm),
            }
        if len(z_main_nums) == 4:
            h_cm, btop_cm, bbot_cm, ri_cm = z_main_nums
            return {
                'kind': 'Z',
                'depth': cm(h_cm),
                'top_flange_width': cm(btop_cm),
                'bottom_flange_width': cm(bbot_cm),
                'thickness': clamp_thickness_m(cm(t_cm), cm(h_cm), cm(btop_cm), cm(bbot_cm)),
                'inner_radius': cm(ri_cm),
                'top_return': 0.0,
                'bottom_return': 0.0,
                'bottom_return_angle_deg': 90.0,
                'top_return_angle_deg': 90.0,
                'overall_width': cm(btop_cm) + cm(bbot_cm),
                'overall_depth': cm(h_cm),
            }
        return {
            'kind': 'Z',
            'depth': cm(20.0),
            'top_flange_width': cm(6.0),
            'bottom_flange_width': cm(6.0),
            'thickness': clamp_thickness_m(cm(t_cm), cm(20.0), cm(6.0), cm(6.0)),
            'inner_radius': cm(0.2),
            'top_return': 0.0,
            'bottom_return': 0.0,
            'bottom_return_angle_deg': 90.0,
            'top_return_angle_deg': 90.0,
            'overall_width': cm(12.0),
            'overall_depth': cm(20.0),
        }

    m = re.search(r"\b(IPE|IPN|HEA|HEB|HEM)\s*(\d+(?:[.,]\d+)?)", name)
    if m:
        family_i = m.group(1)
        h_mm = float(m.group(2).replace(',', '.'))
        if family_i == 'IPE':
            b_mm = 0.5 * h_mm
            tw_mm = max(4.4, 0.021 * h_mm)
            tf_mm = max(6.0, 0.034 * h_mm)
        elif family_i == 'IPN':
            b_mm = 0.42 * h_mm
            tw_mm = max(4.0, 0.02 * h_mm)
            tf_mm = max(6.0, 0.035 * h_mm)
        else:
            b_mm = 0.95 * h_mm
            tw_mm = max(6.0, 0.018 * h_mm)
            tf_mm = max(9.0, 0.032 * h_mm)
        return {
            'kind': 'I',
            'width': b_mm / 1000.0,
            'depth': h_mm / 1000.0,
            'web': tw_mm / 1000.0,
            'flange': tf_mm / 1000.0,
            'overall_width': b_mm / 1000.0,
            'overall_depth': h_mm / 1000.0,
            'web_thickness': tw_mm / 1000.0,
            'flange_thickness': tf_mm / 1000.0,
        }

    mm_family_rect = any(tag in raw for tag in [' RCT', 'RHSC', 'RHSH', 'SHSC', 'SHSH']) or name.startswith(('RCT', 'RHS', 'SHS')) or family.startswith(('RCT', 'RHSC', 'RHSH', 'SHSC', 'SHSH'))
    mm_family_circ = any(tag in raw for tag in ['CHSC', 'CHSH']) or name.startswith('CHS') or family.startswith(('CHSC', 'CHSH'))

    if mm_family_rect:
        n0 = nums_cm[0] if len(nums_cm) > 0 else 40.0
        n1 = nums_cm[1] if len(nums_cm) > 1 else n0
        n2 = nums_cm[2] if len(nums_cm) > 2 else None
        depth = mm(n0)
        width = mm(n1)
        if 'RCT' in raw or name.startswith('RCT') or family.startswith('RCT'):
            return {'kind': 'RECT', 'width': width, 'depth': depth}
        thickness = clamp_thickness_m(mm(n2 if n2 is not None else min(n0, n1) * 0.10), width, depth)
        return {'kind': 'RECTTUBE', 'width': width, 'depth': depth, 'thickness': thickness}

    if mm_family_circ:
        n0 = nums_cm[0] if len(nums_cm) > 0 else 40.0
        n1 = nums_cm[1] if len(nums_cm) > 1 else max(2.0, n0 * 0.10)
        diameter = mm(n0)
        thickness = clamp_thickness_m(mm(n1), diameter)
        return {'kind': 'CIRCLETUBE', 'radius': diameter / 2.0, 'thickness': thickness}

    m = re.match(r'^L\s*(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)$', name)
    if m:
        a_mm = float(m.group(1).replace(',', '.'))
        b_mm = float(m.group(2).replace(',', '.'))
        t_mm = float(m.group(3).replace(',', '.'))
        return {'kind': 'ANGLE', 'width': mm(a_mm), 'depth': mm(b_mm), 'thickness': clamp_thickness_m(mm(t_mm), mm(a_mm), mm(b_mm))}

    if is_mm_metal and ('STANGLE' in sec_type or 'ANGLE' in sec_type):
        n0 = nums_cm[0] if len(nums_cm) > 0 else 60.0
        n1 = nums_cm[1] if len(nums_cm) > 1 else n0
        n2 = nums_cm[2] if len(nums_cm) > 2 else max(4.0, min(n0, n1) * 0.10)
        return {'kind': 'ANGLE', 'width': mm(n0), 'depth': mm(n1), 'thickness': clamp_thickness_m(mm(n2), mm(n0), mm(n1))}

    if 'STRECTANGULARTUBE' in sec_type or 'STSQUARETUBE' in sec_type or ('TUBE' in name and 'RECT' in name):
        width = cm(pick_cm(0, 20.0))
        depth = cm(pick_cm(1, pick_cm(0, 20.0)))
        thickness = clamp_thickness_m(cm(pick_cm(2, min(pick_cm(0, 20.0), pick_cm(1, pick_cm(0, 20.0))) * 0.10)), width, depth)
        return {'kind': 'RECTTUBE', 'width': width, 'depth': depth, 'thickness': thickness}

    if 'STCIRCULARTUBE' in sec_type or ('TUBE' in name and 'CIRC' in name):
        diameter = cm(pick_cm(0, 20.0))
        thickness = clamp_thickness_m(cm(pick_cm(1, pick_cm(0, 20.0) * 0.10)), diameter)
        return {'kind': 'CIRCLETUBE', 'radius': diameter / 2.0, 'thickness': thickness}

    mm_round = ('ROND' in raw) or ('Ø' in raw) or ('DIAM' in raw and 'TUBE' not in raw)
    if sec_type == 'STCIRCULAR' or ('CIRCULAR' in sec_type and 'TUBE' not in sec_type) or ('CIRC' in name and 'TUBE' not in name) or mm_round:
        diameter = mm(pick_cm(0, 20.0)) if mm_round else cm(pick_cm(0, 20.0))
        return {'kind': 'CIRCLE', 'radius': diameter / 2.0}

    if 'TDISSYMETRIC' in sec_type:
        web = cm(pick_cm(0, 20.0))
        height = cm(pick_cm(1, 60.0))
        left_width = cm(pick_cm(2, 10.0))
        left_thickness = clamp_thickness_m(cm(pick_cm(3, 10.0)), height)
        left_offset = cm(pick_cm(4, 20.0))
        right_width = cm(pick_cm(5, 10.0))
        right_thickness = clamp_thickness_m(cm(pick_cm(6, 10.0)), height)
        right_offset = cm(pick_cm(7, 20.0))
        return {
            'kind': 'TDISSYMETRIC',
            'width': web + left_width + right_width,
            'depth': height,
            'web': web,
            'left_width': left_width,
            'left_thickness': left_thickness,
            'left_offset': left_offset,
            'right_width': right_width,
            'right_thickness': right_thickness,
            'right_offset': right_offset,
        }

    if sec_type == 'STT' or re.search(r"\bT\b", name):
        height = cm(pick_cm(0, 30.0))
        web = clamp_thickness_m(cm(pick_cm(1, 10.0)), height)
        width = cm(pick_cm(2, pick_cm(0, 30.0) * 0.6))
        flange = clamp_thickness_m(cm(pick_cm(3, 10.0)), width, height)
        return {'kind': 'T', 'width': width, 'depth': height, 'web': web, 'flange': flange}

    m = re.search(r"\b(UPE|UPN|UNP|UAP|U)\s*(\d+(?:[.,]\d+)?)", name)
    if sec_type == 'STU' or ('CHANNEL' in name) or m or re.search(r"\bU\b", name):
        family_u = m.group(1) if m else ''
        h_mm = float(m.group(2).replace(',', '.')) if m else pick_cm(0, 30.0) * 10.0
        if family_u == 'UPE':
            b_mm = 0.55 * h_mm
            tw_mm = max(6.0, 0.036 * h_mm)
            tf_mm = max(8.5, 0.047 * h_mm)
        elif family_u in ('UPN', 'UNP', 'UAP'):
            b_mm = 0.45 * h_mm
            tw_mm = max(6.0, 0.038 * h_mm)
            tf_mm = max(9.0, 0.052 * h_mm)
        else:
            height = cm(pick_cm(0, 30.0))
            width = cm(pick_cm(1, pick_cm(0, 30.0) * 0.4))
            web = clamp_thickness_m(cm(pick_cm(2, 4.0)), width, height)
            flange = clamp_thickness_m(cm(pick_cm(3, 4.0)), width, height)
            return {'kind': 'U', 'width': width, 'depth': height, 'web': web, 'flange': flange}
        return {
            'kind': 'U',
            'width': b_mm / 1000.0,
            'depth': h_mm / 1000.0,
            'web': tw_mm / 1000.0,
            'flange': tf_mm / 1000.0,
        }

    if 'STANGLE' in sec_type or 'STUNEQUALANGLE' in sec_type or 'ANGLE' in name or re.search(r"\bL\b", name):
        height = cm(pick_cm(0, 10.0))
        if len(nums_cm) >= 3:
            width = cm(pick_cm(1, pick_cm(0, 10.0)))
            thickness = clamp_thickness_m(cm(pick_cm(2, min(pick_cm(0, 10.0), pick_cm(1, pick_cm(0, 10.0))) * 0.15)), width, height)
        else:
            width = height
            thickness = clamp_thickness_m(cm(pick_cm(1, pick_cm(0, 10.0) * 0.15)), width, height)
        return {'kind': 'ANGLE', 'width': width, 'depth': height, 'thickness': thickness}

    if 'STRECTANGULAR' in sec_type or 'STSQUARE' in sec_type or 'RECT' in name or 'SQUARE' in name:
        width = cm(pick_cm(0, 20.0))
        depth = cm(pick_cm(1, pick_cm(0, 20.0)))
        return {'kind': 'RECT', 'width': width, 'depth': depth}

    return None


def profile_bounds_from_dims(dims: dict):
    kind = str((dims or {}).get('kind') or '').upper()
    width = float((dims or {}).get('width', 0.0) or 0.0)
    depth = float((dims or {}).get('depth', 0.0) or 0.0)
    if kind in {'Z', 'ZED', 'ZED_SLOPED'}:
        top_b = float((dims or {}).get('top_flange_width', 0.0) or 0.0)
        bottom_b = float((dims or {}).get('bottom_flange_width', 0.0) or 0.0)
        return (-bottom_b, -depth / 2.0, top_b, depth / 2.0)
    if kind == 'OMEGA':
        top_b = float((dims or {}).get('top_flange_width', width) or width)
        total_w = float((dims or {}).get('overall_width', (2.0 * width + top_b)) or (2.0 * width + top_b))
        return (-total_w / 2.0, -depth / 2.0, total_w / 2.0, depth / 2.0)
    if kind == 'SIGMA':
        t = float((dims or {}).get('thickness', 0.003) or 0.003)
        off = float((dims or {}).get('web_offset', 0.0) or 0.0)
        return_lip = float((dims or {}).get('return_lip', 0.0) or 0.0)
        y_min = 0.0
        y_max = max(width, off + t)
        if return_lip > 0.0:
            z_min = -depth / 2.0
            z_max = depth / 2.0
        else:
            z_min = -depth / 2.0
            z_max = depth / 2.0
        return (y_min, z_min, y_max, z_max)
    if kind in {'RECT', 'RHS', 'SHS', 'I', 'T', 'ANGLE', 'PIPE', 'CHS', 'U', 'C', 'T_DISSYM'}:
        if kind in {'PIPE', 'CHS'}:
            radius = float((dims or {}).get('radius', 0.0) or 0.0)
            if radius > 0.0:
                return (-radius, -radius, radius, radius)
        if width > 0.0 and depth > 0.0:
            return (-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    return None


def section_excentration_option_normalized(el: dict):
    ex = (el or {}).get('sectionExcentration') or {}
    option = str(ex.get('option') or 'center_alignment').strip().lower()
    option = option.replace('alignement', 'alignment')
    aliases = {
        'centeralignment': 'center_alignment',
        'gauchecentre': 'gauche_centre',
        'centrehaut': 'centre_haut',
        'centrebas': 'centre_bas',
        'droitehaut': 'droite_haut',
        'droitecentre': 'droite_centre',
        'droite_milieu': 'droite_centre',
        'droitebas': 'droite_bas',
    }
    return aliases.get(option, option or 'center_alignment')


def section_excentration_translation_local(el: dict, dims: dict):
    option = section_excentration_option_normalized(el)
    if option in {'', 'autre', 'other'}:
        return (0.0, 0.0)
    bounds = profile_bounds_from_dims(dims or {})
    if not bounds:
        return (0.0, 0.0)
    y_min, z_min, y_max, z_max = bounds
    y_map = {
        'topleft': -y_min,
        'gauche_centre': -y_min,
        'gauche_bas': -y_min,
        'centre_haut': -(y_min + y_max) / 2.0,
        'center_alignment': -(y_min + y_max) / 2.0,
        'centeralignment': -(y_min + y_max) / 2.0,
        'centre_bas': -(y_min + y_max) / 2.0,
        'droite_haut': -y_max,
        'droite_centre': -y_max,
        'droite_bas': -y_max,
    }
    z_map = {
        'topleft': -z_min,
        'gauche_centre': -(z_min + z_max) / 2.0,
        'gauche_bas': -z_max,
        'centre_haut': -z_min,
        'center_alignment': -(z_min + z_max) / 2.0,
        'centeralignment': -(z_min + z_max) / 2.0,
        'centre_bas': -z_max,
        'droite_haut': -z_min,
        'droite_centre': -(z_min + z_max) / 2.0,
        'droite_bas': -z_max,
    }
    return (float(y_map.get(option, 0.0)), float(z_map.get(option, 0.0)))

def rotate_local_yz(y: float, z: float, angle_rad: float):
    a = float(angle_rad or 0.0)
    ca = math.cos(a)
    sa = math.sin(a)
    return (float(y) * ca - float(z) * sa, float(y) * sa + float(z) * ca)


def rotate_poly2(poly2, angle_rad: float):
    a = float(angle_rad or 0.0)
    if abs(a) < 1e-12:
        return [[float(x), float(y)] for x, y in poly2]
    ca = math.cos(a)
    sa = math.sin(a)
    return [[float(x) * ca - float(y) * sa, float(x) * sa + float(y) * ca] for x, y in poly2]


def section_orientation_angle_rad(el: dict):
    return float((el or {}).get('sectionOrientationAngle') or 0.0)


def section_orientation_angle_deg(el: dict):
    return math.degrees(section_orientation_angle_rad(el))


def oriented_section_translation_local(el: dict, dims: dict):
    dy, dz = section_excentration_translation_local(el, dims)
    ang = section_orientation_angle_rad(el)
    if abs(ang) < 1e-12:
        return (dy, dz)
    return rotate_local_yz(dy, dz, ang)


def default_linear_dims(sec: dict, beam_type: str):
    parsed = parse_section_dims(sec)
    if parsed:
        return parsed
    role = (beam_type or '').lower()
    if 'column' in role or 'bar' in role or 'strut' in role:
        return {'kind': 'RECT', 'width': 0.25, 'depth': 0.25}
    return {'kind': 'RECT', 'width': 0.12, 'depth': 0.30}


def is_i_or_h_catalog_section(sec: dict):
    dims = parse_section_dims(sec or {}) or {}
    if str(dims.get('kind', '')).upper() != 'I':
        return False
    name = (sec.get('name') or '').upper().strip()
    return bool(re.search(r'\b(IPE|IPN|HEA|HEB|HEM)\s*\d', name))


def resolve_haunch_section_dims(base_sec: dict, haunch: dict, sections: dict, beam_type: str):
    htype = str((haunch or {}).get('haunchSectionType') or 'identical').lower()
    if htype == 'imposee':
        sec_ref = sections.get(eid_value((haunch or {}).get('haunchSection'))) or base_sec
    else:
        sec_ref = base_sec
    dims = default_linear_dims(sec_ref, beam_type).copy()
    dims['_ad_haunch_section_type'] = htype
    dims['_ad_haunch_section_name'] = (sec_ref or {}).get('name')
    return dims


def haunch_length_along_axis(haunch: dict, element_length: float, beam_dir):
    if not haunch or str(haunch.get('haunchPosition') or '').lower() == 'no_haunch':
        return 0.0
    ltype = str(haunch.get('lengthType') or 'ratio').lower()
    if ltype == 'ratio':
        return max(0.0, float(haunch.get('lengthRatio') or 0.0) * element_length)
    if ltype == 'valeur_axe_local':
        return max(0.0, float(haunch.get('lengthValue') or 0.0))
    if ltype == 'valeur_projete':
        uz = abs(float(beam_dir[2]))
        if uz < 1e-9:
            return min(element_length, max(0.0, float(haunch.get('lengthValue') or 0.0)))
        return max(0.0, float(haunch.get('lengthValue') or 0.0) / uz)
    return max(0.0, float(haunch.get('lengthValue') or 0.0))


def apply_haunch_height(base_dims: dict, ref_dims: dict, haunch: dict):
    dims = dict(ref_dims)
    base_depth = float(base_dims.get('depth', 0.30))
    ref_depth = float(ref_dims.get('depth', base_depth))
    htype = str((haunch or {}).get('heightType') or 'ratio').lower()
    if htype == 'valeur_axe_local':
        target_depth = max(0.001, float((haunch or {}).get('heightValue') or ref_depth))
    else:
        ratio = float((haunch or {}).get('heightRatio') or 1.0)
        target_depth = max(0.001, ref_depth * ratio)
    dims['depth'] = target_depth
    dims['overall_depth'] = target_depth
    dims['_haunch_target_depth'] = target_depth
    return dims


def i_section_polygon(dims: dict):
    b = float(dims.get('width', dims.get('overall_width', 0.15)))
    h = float(dims.get('depth', dims.get('overall_depth', 0.30)))
    tw = min(float(dims.get('web', dims.get('web_thickness', 0.006))), b * 0.95)
    tf = min(float(dims.get('flange', dims.get('flange_thickness', 0.010))), h * 0.49)
    top_extra = float(dims.get('_haunch_top_extra', 0.0))
    bottom_extra = float(dims.get('_haunch_bottom_extra', 0.0))
    x0 = -b / 2.0
    x1 = -tw / 2.0
    x2 = tw / 2.0
    x3 = b / 2.0
    y0 = -h / 2.0 - bottom_extra
    y1 = y0 + tf
    y3 = h / 2.0 + top_extra
    y2 = y3 - tf
    return [
        [x0, y3], [x3, y3], [x3, y2], [x2, y2], [x2, y1], [x3, y1],
        [x3, y0], [x0, y0], [x0, y1], [x1, y1], [x1, y2], [x0, y2]
    ]



def u_section_polygon(dims: dict, open_left=True):
    b = float(dims.get('width', dims.get('overall_width', 0.075)))
    h = float(dims.get('depth', dims.get('overall_depth', 0.20)))
    tw = min(float(dims.get('web', dims.get('web_thickness', 0.007))), b * 0.95)
    tf = min(float(dims.get('flange', dims.get('flange_thickness', 0.011))), h * 0.49)
    x0 = -b / 2.0
    x1 = b / 2.0 - tw
    x2 = b / 2.0
    y0 = -h / 2.0
    y1 = y0 + tf
    y2 = h / 2.0 - tf
    y3 = h / 2.0
    poly = [[x2, y3], [x0, y3], [x0, y2], [x1, y2], [x1, y1], [x0, y1], [x0, y0], [x2, y0]]
    if not open_left:
        poly = [[-x, y] for x, y in poly]
    return poly


def angle_section_polygon(dims: dict):
    b = float(dims.get('width', dims.get('overall_width', 0.05)))
    h = float(dims.get('depth', dims.get('overall_depth', 0.05)))
    t = min(float(dims.get('thickness', 0.005)), min(b, h) * 0.49)
    return [[0.0, 0.0], [b, 0.0], [b, t], [t, t], [t, h], [0.0, h]]


def translate_polygon2(poly2, dx=0.0, dy=0.0):
    return [[float(x) + float(dx), float(y) + float(dy)] for x, y in poly2]


def rotate_polygon2(poly2, quarter_turns=0):
    q = int(quarter_turns) % 4
    poly = [[float(x), float(y)] for x, y in poly2]
    for _ in range(q):
        poly = [[-y, x] for x, y in poly]
    return poly


def mirror_polygon2_x(poly2):
    return [[-float(x), float(y)] for x, y in poly2]


def polygon_bounds(poly2):
    xs = [p[0] for p in poly2]
    ys = [p[1] for p in poly2]
    return min(xs), min(ys), max(xs), max(ys)


def parse_catalog_profile_dims(token: str):
    name = (token or '').upper().strip()
    dims = parse_section_dims({'name': name, 'materialName': 'S275'})
    if dims:
        return dims
    m = re.match(r'^(UPN|UPE|UNP)\s*(\d+(?:[.,]\d+)?)$', name)
    if m:
        h_mm = float(m.group(2).replace(',', '.'))
        b_mm = max(40.0, 0.38 * h_mm)
        tw_mm = max(5.0, 0.035 * h_mm)
        tf_mm = max(7.0, 0.055 * h_mm)
        return {
            'kind': 'U',
            'width': b_mm / 1000.0,
            'depth': h_mm / 1000.0,
            'web': tw_mm / 1000.0,
            'flange': tf_mm / 1000.0,
            'overall_width': b_mm / 1000.0,
            'overall_depth': h_mm / 1000.0,
            'web_thickness': tw_mm / 1000.0,
            'flange_thickness': tf_mm / 1000.0,
        }
    m = re.match(r'^L\s*(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)$', name)
    if m:
        a_mm = float(m.group(1).replace(',', '.'))
        b_mm = float(m.group(2).replace(',', '.'))
        t_mm = float(m.group(3).replace(',', '.'))
        return {
            'kind': 'ANGLE',
            'width': a_mm / 1000.0,
            'depth': b_mm / 1000.0,
            'thickness': t_mm / 1000.0,
            'overall_width': a_mm / 1000.0,
            'overall_depth': b_mm / 1000.0,
        }
    return None


def parse_combined_section(sec: dict):
    name = (sec.get('name') or '').upper().strip()
    sec_type = (sec.get('type') or '').upper().strip()
    if 'COMBINED' not in sec_type and not name.startswith('CS'):
        return None
    m = re.match(r'^CS\s*([1-7])\s*([A-Z0-9X.,+-]+)\s+([A-Z0-9X.,+-]+)', name)
    if not m:
        return None
    code = f"CS{m.group(1)}"
    primary = m.group(2).replace(',', '.').upper()
    secondary = m.group(3).replace(',', '.').upper()
    return {'code': code, 'primary_name': primary, 'secondary_name': secondary}


def combined_member_polygons(defn: dict):
    if not defn:
        return None
    code = defn['code']
    p_dims = parse_catalog_profile_dims(defn['primary_name'])
    s_dims = parse_catalog_profile_dims(defn['secondary_name'])
    if not p_dims or not s_dims:
        return None
    p_kind = str(p_dims.get('kind', '')).upper()
    s_kind = str(s_dims.get('kind', '')).upper()
    if code in ('CS1', 'CS2', 'CS3') and not (p_kind == 'I' and s_kind == 'I'):
        return None
    if code in ('CS4', 'CS5') and not (p_kind == 'I' and s_kind == 'U'):
        return None
    if code == 'CS6' and not (p_kind == 'U' and s_kind == 'U'):
        return None
    if code == 'CS7' and not (p_kind == 'ANGLE' and s_kind == 'ANGLE'):
        return None

    p_poly = i_section_polygon(p_dims) if p_kind == 'I' else (u_section_polygon(p_dims) if p_kind == 'U' else angle_section_polygon(p_dims))
    s_poly = i_section_polygon(s_dims) if s_kind == 'I' else (u_section_polygon(s_dims) if s_kind == 'U' else angle_section_polygon(s_dims))
    polys = []

    if code == 'CS1':
        s_poly = rotate_polygon2(s_poly, 1)
        sx0, sy0, sx1, sy1 = polygon_bounds(s_poly)
        p_tw = float(p_dims.get('web', p_dims.get('web_thickness', 0.0)))
        dx = p_tw / 2.0 - sx0
        dy = 0.0
        polys = [p_poly, translate_polygon2(s_poly, dx=dx, dy=dy)]
    elif code == 'CS2':
        dx = float(p_dims.get('width', 0.0)) / 2.0 + float(s_dims.get('width', 0.0)) / 2.0
        dy = 0.0
        polys = [p_poly, translate_polygon2(s_poly, dx=dx, dy=dy)]
    elif code == 'CS3':
        dy = float(p_dims.get('depth', 0.0)) / 2.0 + float(s_dims.get('depth', 0.0)) / 2.0
        polys = [p_poly, translate_polygon2(s_poly, dx=0.0, dy=dy)]
    elif code == 'CS4':
        s_poly = rotate_polygon2(s_poly, 3)
        sx0, sy0, sx1, sy1 = polygon_bounds(s_poly)
        dy = float(p_dims.get('depth', 0.0)) / 2.0 - sy0
        polys = [p_poly, translate_polygon2(s_poly, dx=-(sx0 + sx1) / 2.0, dy=dy)]
    elif code == 'CS5':
        s_poly = u_section_polygon(s_dims, open_left=False)
        sx0, sy0, sx1, sy1 = polygon_bounds(s_poly)
        p_tw = float(p_dims.get('web', p_dims.get('web_thickness', 0.0)))
        dx = p_tw / 2.0 - sx0
        polys = [p_poly, translate_polygon2(s_poly, dx=dx, dy=0.0)]
    elif code == 'CS6':
        left = u_section_polygon(p_dims, open_left=True)
        right = u_section_polygon(s_dims, open_left=False)
        lx0, ly0, lx1, ly1 = polygon_bounds(left)
        rx0, ry0, rx1, ry1 = polygon_bounds(right)
        lp = translate_polygon2(left, dx=-lx1, dy=0.0)
        rp = translate_polygon2(right, dx=-rx0, dy=0.0)
        polys = [lp, rp]
    elif code == 'CS7':
        t = float(p_dims.get('thickness', 0.005))
        left = translate_polygon2(mirror_polygon2_x(angle_section_polygon(p_dims)), dx=-t, dy=0.0)
        right = angle_section_polygon(s_dims)
        polys = [left, right]

    return {'code': code, 'primary_dims': p_dims, 'secondary_dims': s_dims, 'polygons': polys}


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
def offset_polygon2(poly2, dy):
    return [[float(x), float(y) + float(dy)] for x, y in poly2]


def section_pts3_local(station, poly2):
    z = float(station)
    return [[float(x), float(y), z] for x, y in poly2]


def polygon_set_bounds(polys):
    xs = []
    ys = []
    for poly in polys or []:
        for x, y in poly or []:
            xs.append(float(x))
            ys.append(float(y))
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def section_excentration_translation_from_bounds(el: dict, bounds):
    option = section_excentration_option_normalized(el)
    if option in {'', 'autre', 'other'} or not bounds:
        return (0.0, 0.0)
    x_min, y_min, x_max, y_max = bounds
    x_map = {
        'topleft': -x_min,
        'gauche_centre': -x_min,
        'gauche_bas': -x_min,
        'centre_haut': -(x_min + x_max) / 2.0,
        'center_alignment': -(x_min + x_max) / 2.0,
        'centeralignment': -(x_min + x_max) / 2.0,
        'centre_bas': -(x_min + x_max) / 2.0,
        'droite_haut': -x_max,
        'droite_centre': -x_max,
        'droite_bas': -x_max,
    }
    y_map = {
        'topleft': -y_min,
        'gauche_centre': -(y_min + y_max) / 2.0,
        'gauche_bas': -y_max,
        'centre_haut': -y_min,
        'center_alignment': -(y_min + y_max) / 2.0,
        'centeralignment': -(y_min + y_max) / 2.0,
        'centre_bas': -y_max,
        'droite_haut': -y_min,
        'droite_centre': -(y_min + y_max) / 2.0,
        'droite_bas': -y_max,
    }
    return (float(x_map.get(option, 0.0)), float(y_map.get(option, 0.0)))


def translate_section_excentration_polys(polys, el: dict):
    bounds = polygon_set_bounds(polys)
    ex_dx, ex_dy = section_excentration_translation_from_bounds(el, bounds)
    return [translate_polygon2(poly, dx=ex_dx, dy=ex_dy) for poly in (polys or [])], ex_dx, ex_dy, bounds


def clamp_contact_polygon(poly2, base_depth, pos, dy):
    pos = str(pos or 'no_haunch').lower()
    if pos == 'haut':
        return [[x, min(y, base_depth / 2.0)] for x, y in poly2]
    if pos == 'bas':
        return [[x, max(y, -base_depth / 2.0)] for x, y in poly2]
    if pos == 'haut_et_bas':
        cy = float(dy)
        return [[x, min(y, base_depth / 2.0) if y >= cy else max(y, -base_depth / 2.0)] for x, y in poly2]
    return poly2


def haunch_profile_offsets(base_depth, add_depth, pos):
    pos = str(pos or 'no_haunch').lower()
    base_depth = float(base_depth)
    add_depth = float(add_depth)
    if pos == 'haut':
        return [base_depth / 2.0 + add_depth / 2.0]
    if pos == 'bas':
        return [-(base_depth / 2.0 + add_depth / 2.0)]
    if pos == 'haut_et_bas':
        return [base_depth / 2.0 + add_depth / 2.0, -(base_depth / 2.0 + add_depth / 2.0)]
    return []


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


def collect_all(host: str, include_loads: bool):
    results = defaultdict(list)
    for t in LINEAR_TYPES + PLANAR_TYPES + SUPPORT_TYPES + (LOAD_TYPES if include_loads else []):
        ids = get_ids_for_type(host, t)
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


def export_ifc_core(host: str, out_path: str, include_loads: bool = False, project_name: str | None = None, logger=None) -> dict:
    emit_log(logger, f"Export IFC v{VERSION} : lecture des matériaux et sections...", "info")
    materials = get_materials(host)
    sections = get_sections(host)
    emit_log(logger, "Lecture des éléments du modèle...", "info")
    elems = collect_all(host, include_loads)
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


def export_ifc_from_fto(host: str, fto_path: str, out_path: str, include_loads: bool = False, logger=None, check_api_first: bool = True, close_project_on_exit: bool = True) -> dict:
    host = str(host or DEFAULT_HOST).rstrip("/")
    fto_path = check_fto_path(fto_path)
    if check_api_first:
        emit_log(logger, f"Vérification de l'accessibilité de l'API ({host})...", "info")
        check_port(host)
        emit_log(logger, "API accessible.", "ok")
    emit_log(logger, f"Ouverture du projet : {fto_path}", "info")
    open_project(host, fto_path)
    try:
        return export_ifc_core(host, out_path, include_loads=include_loads, project_name=os.path.basename(fto_path), logger=logger)
    finally:
        if close_project_on_exit:
            close_project(host)


def export_ifc_from_open_project(host: str, out_path: str, include_loads: bool = False, project_name: str = "ViewerProject", logger=None, check_api_first: bool = True) -> dict:
    host = str(host or DEFAULT_HOST).rstrip("/")
    if check_api_first:
        emit_log(logger, f"Vérification de l'accessibilité de l'API ({host})...", "info")
        check_port(host)
        emit_log(logger, "API accessible.", "ok")
    return export_ifc_core(host, out_path, include_loads=include_loads, project_name=project_name, logger=logger)


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
