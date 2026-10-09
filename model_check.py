

# -*- coding: utf-8 -*-
"""Controle du modele 3D : detection d'anomalies (moteur pur, sans Qt ni VTK).

Entree : `model_data` (lecture seule) et `Thresholds` (mm, deg, m2).
Sortie : liste triee d'`Anomaly`. Les coordonnees du modele sont en metres.
Chaque regle est une fonction `rule_*(ctx)` enregistree par `@_stage` ; elles
s'executent dans l'ordre de definition (doublons, chevauchements, elements
courts, connexions, colinearite, surfaces, appuis), ce qui realise les
priorites : un couple deja signale n'est pas signale par une regle moindre.
"""

import math
from collections import namedtuple
from dataclasses import dataclass, fields

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITY_RANK = {ERROR: 0, WARNING: 1, INFO: 2}

K_MISSING = "missing_connection"
K_DUPLICATE = "duplicate"
K_OVERLAP = "overlap"
K_COLLINEAR = "collinear"
K_SHORT = "short_element"
K_NULL = "null_length_element"
K_SURF_AREA = "surface_area"
K_SURF_VERTICES = "surface_vertices"
K_SURF_CROSS = "surface_self_intersection"
K_SURF_EDGE = "surface_short_edge"
K_NO_SUPPORT = "no_support"
K_SUPPORT_OVERLAP = "support_overlap"

SEVERITY_BY_KIND = {
    K_MISSING: ERROR,
    K_DUPLICATE: ERROR,
    K_OVERLAP: ERROR,
    K_NULL: ERROR,
    K_SURF_AREA: ERROR,
    K_SURF_VERTICES: ERROR,
    K_SURF_CROSS: ERROR,
    K_NO_SUPPORT: ERROR,
    K_SHORT: WARNING,
    K_SURF_EDGE: WARNING,
    K_SUPPORT_OVERLAP: WARNING,
    K_COLLINEAR: INFO,
}
KINDS = tuple(SEVERITY_BY_KIND)

ROLE_LINE = "lines"
ROLE_PLANAR = "planars"
ROLE_SUPPORT = "support_punctual"

SECTION = "model_check"
EPS = 1e-12
ANGLE_SLACK = 1e-6   # deg : bruit d'arrondi de acos pour des axes quasi identiques

BOUNDS = {
    "connection_tol_mm": (0.0, 1000.0),
    "duplicate_tol_mm": (0.0, 1000.0),
    "duplicate_angle_deg": (0.0, 90.0),
    "overlap_dist_mm": (0.0, 1000.0),
    "overlap_min_len_mm": (0.0, 100000.0),
    "overlap_angle_deg": (0.0, 90.0),
    "min_element_len_mm": (0.0, 100000.0),
    "merge_tol_mm": (0.0, 1000.0),
    "collinear_angle_deg": (0.0, 90.0),
    "min_surface_area_m2": (0.0, 1000000.0),
    "min_edge_len_mm": (0.0, 100000.0),
    "coincident_vertex_tol_mm": (0.0, 1000.0),
    "symbol_transparency_pct": (40.0, 60.0),
    "symbol_min_size_mm": (1.0, 10000.0),
}


@dataclass(frozen=True)
class Thresholds:
    connection_tol_mm: float = 5.0
    duplicate_tol_mm: float = 1.0
    duplicate_angle_deg: float = 1.0
    overlap_dist_mm: float = 5.0
    overlap_min_len_mm: float = 10.0
    overlap_angle_deg: float = 2.0
    min_element_len_mm: float = 50.0
    merge_tol_mm: float = 1.0
    collinear_angle_deg: float = 1.0
    min_surface_area_m2: float = 0.01
    min_edge_len_mm: float = 10.0
    coincident_vertex_tol_mm: float = 1.0
    check_supports: bool = True
    report_overlapping_supports: bool = True
    include_info: bool = True
    symbol_transparency_pct: float = 50.0
    symbol_min_size_mm: float = 50.0

    def clamped(self):
        values = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name in BOUNDS:
                lo, hi = BOUNDS[f.name]
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = f.default
                if not math.isfinite(v):
                    v = f.default
                v = min(hi, max(lo, v))
            else:
                v = bool(v)
            values[f.name] = v
        return Thresholds(**values)

    def to_section(self):
        """Seules les valeurs differentes du defaut sont ecrites."""
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if v != f.default:
                out[f.name] = str(v).lower() if isinstance(v, bool) else repr(float(v))
        return out

    @classmethod
    def from_section(cls, section):
        values = {}
        for f in fields(cls):
            raw = section.get(f.name) if section is not None else None
            if raw is None:
                continue
            if f.name in BOUNDS:
                try:
                    values[f.name] = float(raw)
                except ValueError:
                    continue
            else:
                values[f.name] = str(raw).strip().lower() in ("1", "true", "yes", "on")
        return cls(**values).clamped()


@dataclass(frozen=True)
class Anomaly:
    kind: str
    severity: str
    items: tuple       # ((role, index), ...)
    eids: tuple        # identifiants (peuvent contenir None), alignes sur items
    point: tuple       # (x, y, z) en metres
    measured: object = None
    threshold: object = None
    unit: str = ""     # "mm", "deg" ou "m2"
    shape: object = None   # donnees de symbole (cf. model_check_view)


class DetectionCancelled(Exception):
    pass


Seg = namedtuple("Seg", "index eid a b length u")


# ---- geometrie -----------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _dist(a, b):
    return _norm(_sub(a, b))


def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _unit(v):
    n = _norm(v)
    return None if n < 1e-12 else (v[0] / n, v[1] / n, v[2] / n)


def _nk(p):
    """Cle de noeud : coordonnees strictement identiques (arrondi 1e-9 m)."""
    return (round(p[0], 9), round(p[1], 9), round(p[2], 9))


def _angle_deg(u, v):
    """Angle non oriente entre deux axes, dans [0, 90]."""
    return math.degrees(math.acos(min(1.0, abs(_dot(u, v)))))


def _perp_axes(u):
    ref = (0.0, 0.0, 1.0) if abs(u[2]) < 0.9 else (1.0, 0.0, 0.0)
    v = _unit(_cross(u, ref))
    return v, _cross(u, v)


def _enclosing_box(u, pts):
    """Prisme oriente selon l'axe u englobant les points."""
    v, w = _perp_axes(u)
    origin = pts[0]
    center = origin
    half = []
    for axis in (u, v, w):
        ts = [_dot(_sub(p, origin), axis) for p in pts]
        lo, hi = min(ts), max(ts)
        center = _add(center, _mul(axis, (lo + hi) / 2.0))
        half.append((hi - lo) / 2.0)
    return {"type": "prism", "center": center, "u": u, "v": v, "w": w, "half": tuple(half)}


# ---- contexte d'execution ---------------------------------------------------

class _Ctl:
    def __init__(self, progress, cancelled):
        self.progress = progress
        self.cancelled = cancelled
        self.n = 0

    def check(self):
        if self.cancelled is not None and self.cancelled():
            raise DetectionCancelled()

    def tick(self):
        self.n += 1
        if self.n % 2048 == 0:
            self.check()

    def stage(self, done, total):
        self.check()
        if self.progress is not None:
            self.progress(done, total)


def _build_segs(model):
    lines = model.get("lines") or []
    eids = model.get("line_eids") or []
    segs = []
    for i, ln in enumerate(lines):
        a = tuple(float(c) for c in ln[0])
        b = tuple(float(c) for c in ln[1])
        length = _dist(a, b)
        u = _unit(_sub(b, a)) if length > EPS else None
        segs.append(Seg(i, eids[i] if i < len(eids) else None, a, b, length, u))
    return segs


def _cell_size(segs):
    lens = sorted(s.length for s in segs if s.length > 0)
    med = lens[len(lens) // 2] if lens else 1.0
    return min(4.0, max(0.25, med))


def _candidate_pairs(segs, margin, ctl):
    """Couples (i, j), i < j, dont les boites englobantes dilatees de `margin`
    partagent au moins une cellule de la grille. Triee, donc deterministe."""
    cell = _cell_size(segs)
    grid = {}
    for s in segs:
        lo = [math.floor((min(s.a[k], s.b[k]) - margin) / cell) for k in range(3)]
        hi = [math.floor((max(s.a[k], s.b[k]) + margin) / cell) for k in range(3)]
        for cx in range(int(lo[0]), int(hi[0]) + 1):
            for cy in range(int(lo[1]), int(hi[1]) + 1):
                for cz in range(int(lo[2]), int(hi[2]) + 1):
                    grid.setdefault((cx, cy, cz), []).append(s.index)
    pairs = set()
    for members in grid.values():
        ctl.tick()
        n = len(members)
        for x in range(n):
            for y in range(x + 1, n):
                pairs.add((members[x], members[y]))
    return sorted(pairs)


class _Ctx:
    def __init__(self, model, th, ctl):
        self.model = model
        self.th = th
        self.ctl = ctl
        self.m = {f.name[:-3]: getattr(th, f.name) * 1e-3 for f in fields(th) if f.name.endswith("_mm")}
        self.out = []
        self.dup_pairs = set()
        self.overlap_pairs = set()
        self.short_set = set()
        self.segs = _build_segs(model)
        self._pairs = None

    @property
    def pairs(self):
        if self._pairs is None:
            margin = max(self.m["connection_tol"], self.m["duplicate_tol"], self.m["overlap_dist"])
            self._pairs = _candidate_pairs(self.segs, margin, self.ctl)
        return self._pairs

    def add(self, kind, items, eids, point, measured=None, threshold=None, unit="", shape=None):
        self.out.append(Anomaly(kind, SEVERITY_BY_KIND[kind], tuple(items), tuple(eids), tuple(point),
                                measured, threshold, unit, shape))


_STAGES = []


def _stage(fn):
    _STAGES.append(fn)
    return fn


def _sort_key(a):
    first = a.eids[0] if a.eids and a.eids[0] is not None else None
    return (SEVERITY_RANK[a.severity], KINDS.index(a.kind), first is None,
            first if first is not None else 0, a.items, a.point)


def detect(model_data, thresholds=None, progress=None, cancelled=None):
    """Detecte les anomalies. Ne modifie jamais `model_data`.

    `progress(fait, total)` est appele entre les regles ; `cancelled()` est
    consulte regulierement : s'il renvoie vrai, `DetectionCancelled` est levee
    et aucun resultat partiel n'est renvoye."""
    th = (thresholds or Thresholds()).clamped()
    ctl = _Ctl(progress, cancelled)
    ctx = _Ctx(model_data or {}, th, ctl)
    total = len(_STAGES)
    for n, rule in enumerate(_STAGES):
        ctl.stage(n, total)
        rule(ctx)
    ctl.stage(total, total)
    return sorted(ctx.out, key=_sort_key)


# ---- regles : doublons, chevauchements, elements courts ----------------------

@_stage
def rule_duplicates(ctx):
    tol = ctx.m["duplicate_tol"]
    for i, j in ctx.pairs:
        ctx.ctl.tick()
        s, t = ctx.segs[i], ctx.segs[j]
        if s.u is None or t.u is None:
            continue
        d_same = max(_dist(s.a, t.a), _dist(s.b, t.b))
        d_rev = max(_dist(s.a, t.b), _dist(s.b, t.a))
        d = min(d_same, d_rev)
        if d > tol + EPS:
            continue
        if _angle_deg(s.u, t.u) > ctx.th.duplicate_angle_deg + ANGLE_SLACK:
            continue
        ctx.dup_pairs.add((i, j))
        box = _enclosing_box(s.u, (s.a, s.b, t.a, t.b))
        ctx.add(K_DUPLICATE, ((ROLE_LINE, i), (ROLE_LINE, j)), (s.eid, t.eid), box["center"],
                d * 1000.0, ctx.th.duplicate_tol_mm, "mm", box)


def _dist_to_line(p, origin, u):
    return _norm(_sub(_sub(p, origin), _mul(u, _dot(_sub(p, origin), u))))


@_stage
def rule_overlaps(ctx):
    d_max = ctx.m["overlap_dist"]
    l_min = ctx.m["overlap_min_len"]
    for i, j in ctx.pairs:
        ctx.ctl.tick()
        if (i, j) in ctx.dup_pairs:
            continue
        s, t = ctx.segs[i], ctx.segs[j]
        if s.u is None or t.u is None:
            continue
        if _angle_deg(s.u, t.u) > ctx.th.overlap_angle_deg + ANGLE_SLACK:
            continue
        u = s.u
        ta = _dot(_sub(t.a, s.a), u)
        tb = _dot(_sub(t.b, s.a), u)
        if abs(tb - ta) < EPS:
            continue
        lo = max(0.0, min(ta, tb))
        hi = min(s.length, max(ta, tb))
        length = hi - lo
        if length <= EPS or length + EPS < l_min:
            continue

        def on_t(x):
            return _lerp(t.a, t.b, (x - ta) / (tb - ta))

        q_lo, q_hi = on_t(lo), on_t(hi)
        d = max(_dist_to_line(q_lo, s.a, u), _dist_to_line(q_hi, s.a, u))
        if d > d_max + EPS:
            continue
        ctx.overlap_pairs.add((i, j))
        p0 = _mid(_add(s.a, _mul(u, lo)), q_lo)
        p1 = _mid(_add(s.a, _mul(u, hi)), q_hi)
        shape = {"type": "cylinder", "p0": p0, "p1": p1, "radius": d_max, "thin": False}
        ctx.add(K_OVERLAP, ((ROLE_LINE, i), (ROLE_LINE, j)), (s.eid, t.eid), _mid(p0, p1),
                d * 1000.0, ctx.th.overlap_dist_mm, "mm", shape)


@_stage
def rule_short_elements(ctx):
    min_len = ctx.m["min_element_len"]
    merge = ctx.m["merge_tol"]
    for s in ctx.segs:
        ctx.ctl.tick()
        if s.length <= merge + EPS:
            kind, threshold = K_NULL, ctx.th.merge_tol_mm
        elif s.length < min_len - EPS:
            kind, threshold = K_SHORT, ctx.th.min_element_len_mm
        else:
            continue
        ctx.short_set.add(s.index)
        center = _mid(s.a, s.b)
        ctx.add(kind, ((ROLE_LINE, s.index),), (s.eid,), center, s.length * 1000.0, threshold, "mm",
                {"type": "sphere", "center": center, "radius": s.length})


# ---- regles : connexions manquantes, quasi-colinearite -----------------------

def _incident(segs):
    nodes = {}
    for s in segs:
        for p in (s.a, s.b):
            nodes.setdefault(_nk(p), set()).add(s.index)
    return nodes


@_stage
def rule_connections(ctx):
    tol = ctx.m["connection_tol"]
    if tol <= 0:
        return
    skip = ctx.dup_pairs | ctx.overlap_pairs
    pairs = [(i, j) for i, j in ctx.pairs if (i, j) not in skip]
    incident = _incident(ctx.segs)
    flagged_nodes = set()
    seen = set()
    sphere_r = tol

    def report(p, q, d, indexes):
        idx = sorted(indexes)
        center = _mid(p, q)
        ctx.add(K_MISSING, tuple((ROLE_LINE, k) for k in idx), tuple(ctx.segs[k].eid for k in idx), center,
                d * 1000.0, ctx.th.connection_tol_mm, "mm",
                {"type": "sphere", "center": center, "radius": sphere_r})

    # extremite - extremite : un seul defaut par couple de noeuds distincts
    for i, j in pairs:
        ctx.ctl.tick()
        s, t = ctx.segs[i], ctx.segs[j]
        for p in (s.a, s.b):
            for q in (t.a, t.b):
                kp, kq = _nk(p), _nk(q)
                if kp == kq:
                    continue
                d = _dist(p, q)
                if d > tol + EPS:
                    continue
                key = frozenset((kp, kq))
                if key in seen:
                    continue
                seen.add(key)
                flagged_nodes.update(key)
                report(p, q, d, incident[kp] | incident[kq])

    # extremite - corps (jonction en T), hors noeuds deja signales
    seen_body = set()
    for i, j in pairs:
        ctx.ctl.tick()
        s, t = ctx.segs[i], ctx.segs[j]
        for owner, other in ((s, t), (t, s)):
            if other.length <= EPS:
                continue
            ab = _sub(other.b, other.a)
            for p in (owner.a, owner.b):
                kp = _nk(p)
                if kp in flagged_nodes or kp == _nk(other.a) or kp == _nk(other.b):
                    continue
                raw = _dot(_sub(p, other.a), ab) / (other.length ** 2)
                if not (0.0 < raw < 1.0):
                    continue
                q = _lerp(other.a, other.b, raw)
                d = _dist(p, q)
                if d <= 1e-9 or d > tol + EPS:
                    continue
                key = (kp, other.index)
                if key in seen_body:
                    continue
                seen_body.add(key)
                report(p, q, d, incident[kp] | {other.index})


@_stage
def rule_collinear(ctx):
    max_dev = ctx.th.collinear_angle_deg
    at_node = {}
    node_point = {}
    for s in ctx.segs:
        if s.index in ctx.short_set or s.u is None:
            continue
        for p, out in ((s.a, s.u), (s.b, _mul(s.u, -1.0))):
            key = _nk(p)
            node_point.setdefault(key, p)
            at_node.setdefault(key, []).append((s.index, out))
    for key in sorted(at_node):
        members = at_node[key]
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                ctx.ctl.tick()
                i, vi = members[x]
                j, vj = members[y]
                a, b = min(i, j), max(i, j)
                if (a, b) in ctx.dup_pairs:
                    continue
                theta = math.degrees(math.acos(max(-1.0, min(1.0, _dot(vi, vj)))))
                deviation = 180.0 - theta
                if deviation > max_dev + ANGLE_SLACK:
                    continue
                sa, sb = ctx.segs[a], ctx.segs[b]
                node = node_point[key]
                shape = {"type": "cylinder", "p0": node, "p1": node, "radius": 0.0, "thin": True,
                         "axis": (members[x][1][0] * -1.0, members[x][1][1] * -1.0, members[x][1][2] * -1.0)}
                ctx.add(K_COLLINEAR, ((ROLE_LINE, a), (ROLE_LINE, b)), (sa.eid, sb.eid), node,
                        deviation, ctx.th.collinear_angle_deg, "deg", shape)


# ---- regles : surfaces -------------------------------------------------------

def _newell(pts):
    nx = ny = nz = 0.0
    n = len(pts)
    for k in range(n):
        x1, y1, z1 = pts[k]
        x2, y2, z2 = pts[(k + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    area = 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    centroid = (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)
    return (nx, ny, nz), area, centroid


def _plane_normal(pts, newell_normal):
    """Normale unitaire ; si Newell s'annule (contour en 8, aire nulle) on prend
    la premiere normale locale non degeneree."""
    n = _unit(newell_normal)
    if n is not None:
        return n
    for k in range(2, len(pts)):
        n = _unit(_cross(_sub(pts[1], pts[0]), _sub(pts[k], pts[0])))
        if n is not None:
            return n
    return None


def _seg_cross_2d(p, p2, q, q2):
    r = (p2[0] - p[0], p2[1] - p[1])
    s = (q2[0] - q[0], q2[1] - q[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-18:
        return None
    qp = (q[0] - p[0], q[1] - p[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return (p[0] + t * r[0], p[1] + t * r[1])
    return None


def _first_self_intersection(pts, normal, centroid):
    nrm = _plane_normal(pts, normal)
    if nrm is None:
        return None
    ref = (0.0, 0.0, 1.0) if abs(nrm[2]) < 0.9 else (1.0, 0.0, 0.0)
    ex = _unit(_cross(nrm, ref))
    ey = _cross(nrm, ex)
    p2 = [(_dot(_sub(p, centroid), ex), _dot(_sub(p, centroid), ey)) for p in pts]
    n = len(p2)
    for i in range(n):
        a1, a2 = p2[i], p2[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            x = _seg_cross_2d(a1, a2, p2[j], p2[(j + 1) % n])
            if x is not None:
                return _add(centroid, _add(_mul(ex, x[0]), _mul(ey, x[1])))
    return None


@_stage
def rule_surfaces(ctx):
    planars = ctx.model.get("planars") or []
    eids = ctx.model.get("planar_eids") or []
    vtol = ctx.m["coincident_vertex_tol"]
    min_edge = ctx.m["min_edge_len"]
    min_area = ctx.th.min_surface_area_m2
    for index, geom in enumerate(planars):
        ctx.ctl.tick()
        pts = [tuple(float(c) for c in p) for p in ((geom or {}).get("outer") or [])]
        if len(pts) >= 2 and _dist(pts[0], pts[-1]) <= 1e-9:
            pts = pts[:-1]
        n = len(pts)
        if n < 3:
            continue
        item = ((ROLE_PLANAR, index),)
        eid = (eids[index] if index < len(eids) else None,)
        normal, area, centroid = _newell(pts)
        outline = tuple(pts)

        def shape(center, radius):
            return {"type": "surface", "outline": outline, "center": center, "radius": radius}

        if area < min_area - 1e-15:
            ctx.add(K_SURF_AREA, item, eid, centroid, area, min_area, "m2", shape(centroid, math.sqrt(area)))

        pair = None
        for i in range(n):
            for j in range(i + 1, n):
                if _dist(pts[i], pts[j]) <= vtol + EPS:
                    pair = (i, j)
                    break
            if pair:
                break
        if pair:
            i, j = pair
            center = _mid(pts[i], pts[j])
            ctx.add(K_SURF_VERTICES, item, eid, center, _dist(pts[i], pts[j]) * 1000.0,
                    ctx.th.coincident_vertex_tol_mm, "mm", shape(center, vtol))

        cross = _first_self_intersection(pts, normal, centroid)
        if cross is not None:
            ctx.add(K_SURF_CROSS, item, eid, cross, None, None, "", shape(cross, ctx.m["symbol_min_size"]))

        for k in range(n):
            a, b = pts[k], pts[(k + 1) % n]
            length = _dist(a, b)
            if length <= vtol + EPS:
                continue
            if length < min_edge - EPS:
                center = _mid(a, b)
                ctx.add(K_SURF_EDGE, item, eid, center, length * 1000.0, ctx.th.min_edge_len_mm, "mm",
                        shape(center, length))


# ---- regles : appuis ---------------------------------------------------------

_RESTRAINT_KEYS = ("TX", "TY", "TZ", "RX", "RY", "RZ")
_STIFFNESS_KEYS = ("KTX", "KTY", "KTZ", "KRX", "KRY", "KRZ")


def _support_signature(props):
    """Signature comparable d'un appui ponctuel ; None = non comparable."""
    props = props or {}
    kind = props.get("kind")
    if kind == "rigid":
        r = props.get("restraints") or {}
        return ("rigid",) + tuple(bool(r.get(k)) for k in _RESTRAINT_KEYS)
    if kind in ("elastic", "tc"):
        st = props.get("stiffness") or {}
        return (kind, props.get("tc_behavior")) + tuple(st.get(k) for k in _STIFFNESS_KEYS)
    return None


def _cluster_points(points, indexes, tol):
    """Groupes (>= 2) d'indices dont les points sont a moins de `tol`
    (fermeture transitive), via une grille de cote `tol`."""
    cell = max(tol, 1e-9)
    parent = {i: i for i in indexes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    grid = {}
    for i in indexes:
        p = points[i]
        cx, cy, cz = (int(math.floor(c / cell)) for c in p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        if _dist(p, points[j]) <= tol + EPS:
                            parent[find(i)] = find(j)
        grid.setdefault((cx, cy, cz), []).append(i)
    groups = {}
    for i in indexes:
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def _model_bounds(model, segs):
    pts = []
    for s in segs:
        pts.extend((s.a, s.b))
    for geom in model.get("planars") or []:
        pts.extend(tuple(float(c) for c in p) for p in ((geom or {}).get("outer") or []))
    if not pts:
        return None
    return (min(p[0] for p in pts), max(p[0] for p in pts),
            min(p[1] for p in pts), max(p[1] for p in pts),
            min(p[2] for p in pts), max(p[2] for p in pts))


@_stage
def rule_supports(ctx):
    th = ctx.th
    if not th.check_supports:
        return
    model = ctx.model
    punctual = [tuple(float(c) for c in p) for p in (model.get("punctual_supports") or [])]
    total = len(punctual) + len(model.get("linear_supports") or []) + len(model.get("planar_supports") or [])
    if total == 0:
        b = _model_bounds(model, ctx.segs)
        if b is not None:
            center = ((b[0] + b[1]) / 2.0, (b[2] + b[3]) / 2.0, (b[4] + b[5]) / 2.0)
            ctx.add(K_NO_SUPPORT, (), (), center, None, None, "", {"type": "frame", "bounds": b})
    if not th.report_overlapping_supports or len(punctual) < 2:
        return
    props = model.get("punctual_support_properties") or []
    eids = model.get("punctual_support_eids") or []
    groups = {}
    for i in range(len(punctual)):
        sig = _support_signature(props[i] if i < len(props) else None)
        if sig is not None:
            groups.setdefault(sig, []).append(i)
    tol = ctx.m["duplicate_tol"]
    clusters = []
    for idx in groups.values():
        ctx.ctl.tick()
        clusters.extend(_cluster_points(punctual, idx, tol))
    for cl in sorted(clusters, key=lambda c: c[0]):
        widest = max(_dist(punctual[a], punctual[b]) for a in cl for b in cl)
        ctx.add(K_SUPPORT_OVERLAP, tuple((ROLE_SUPPORT, i) for i in cl),
                tuple(eids[i] if i < len(eids) else None for i in cl), punctual[cl[0]],
                widest * 1000.0, th.duplicate_tol_mm, "mm", {"type": "cube", "center": punctual[cl[0]]})
