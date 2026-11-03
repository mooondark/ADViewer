# -*- coding: utf-8 -*-
"""
section_geometry.py
Geometrie de section pure (sans ifcopenshell) : parsing des sections Advance
Design, polygones 2D de profil, orientation et excentrement.

Extrait de ad_ifc_exporter.py pour etre reutilisable par le viewer 3D.
Aucune dependance hors stdlib (re, math).
"""

import math
import re
from dataclasses import dataclass

CIRCLE_SIDES = 12  # facettes des cercles et tubes circulaires (suffisant pour le rendu)

__all__ = [
    "is_steel_material_name",
    "parse_section_dims",
    "profile_bounds_from_dims",
    "section_excentration_option_normalized",
    "section_excentration_translation_local",
    "section_excentration_translation_from_bounds",
    "oriented_section_translation_local",
    "translate_section_excentration_polys",
    "rotate_local_yz",
    "rotate_poly2",
    "rotate_polygon2",
    "mirror_polygon2_x",
    "translate_polygon2",
    "offset_polygon2",
    "polygon_bounds",
    "polygon_set_bounds",
    "section_orientation_angle_rad",
    "section_orientation_angle_deg",
    "i_section_polygon",
    "u_section_polygon",
    "angle_section_polygon",
    "t_profile_polygon",
    "t_dissym_profile_polygon",
    "l_profile_polygon",
    "u_profile_polygon",
    "zed_profile_polygon",
    "omega_profile_polygon",
    "sigma_profile_polygon",
    "default_linear_dims",
    "profile_polygon",
    "CIRCLE_SIDES",
    "ref_value",
    "is_i_or_h_catalog_section",
    "haunch_length_along_axis",
    "apply_haunch_height",
    "resolve_haunch_section_dims",
    "clamp_contact_polygon",
    "haunch_profile_offsets",
    "parse_catalog_profile_dims",
    "parse_combined_section",
    "combined_member_polygons",
]


def is_steel_material_name(name):
    txt = (name or '').upper().strip()
    return bool(re.search(r'\bS\d{3}\b', txt)) or any(tag in txt for tag in ['STEEL', 'ACIER', 'METAL'])


_NUMBER = r"(\d+(?:[.,]\d+)?)"
_L_SHAPE = re.compile(r'^L\s*' + _NUMBER + 'X' + _NUMBER + 'X' + _NUMBER + '$')
_I_FAMILY = re.compile(r"\b(IPE|IPN|HEA|HEB|HEM)\s*" + _NUMBER)
_U_FAMILY = re.compile(r"\b(UPE|UPN|UNP|UAP|U)\s*" + _NUMBER)
# (largeur / hauteur, ame min mm, ame / hauteur, aile min mm, aile / hauteur) des profils lamines
_I_RATIOS = {'IPE': (0.5, 4.4, 0.021, 6.0, 0.034), 'IPN': (0.42, 4.0, 0.02, 6.0, 0.035)}
_H_RATIOS = (0.95, 6.0, 0.018, 9.0, 0.032)   # HEA, HEB, HEM
_U_RATIOS = {'UPE': (0.55, 6.0, 0.036, 8.5, 0.047),
             'UPN': (0.45, 6.0, 0.038, 9.0, 0.052), 'UNP': (0.45, 6.0, 0.038, 9.0, 0.052),
             'UAP': (0.45, 6.0, 0.038, 9.0, 0.052)}
_STEEL_FAMILY_TAGS = ('IPE', 'IPN', 'HEA', 'HEB', 'HEM', 'RHS', 'SHS', 'CHS')
_STEEL_TYPE_TAGS = ('ANGLE', 'I_SYMETRIC', 'IASYMETRIC', 'CIRCULARTUBE', 'RECTANGULARTUBE', 'SQUARETUBE', 'SIGMA')


def _numbers(text: str) -> list:
    return [float(x.replace(',', '.')) for x in re.findall(_NUMBER, text)]


def _cm(v) -> float:
    return float(v) / 100.0


def _mm(v) -> float:
    return float(v) / 1000.0


def _clamp_thickness_m(t_m, *sizes_m):
    """Epaisseur bornee a 49 % de la plus petite dimension non nulle (0,02 m si aucune)."""
    limit = min([s for s in sizes_m if s and s > 0] or [0.02]) * 0.49
    return max(0.001, min(t_m, limit))


@dataclass(frozen=True)
class _SectionText:
    """Champs texte d'une section Advance Design, normalises une fois."""
    name: str
    sec_type: str
    family: str
    raw: str
    material: str
    nums: tuple

    @classmethod
    def of(cls, sec: dict):
        name = (sec.get("name") or "").upper().strip()
        family = (sec.get("familyCode") or "").upper().strip()
        catalog = (sec.get("catalogName") or "").upper().strip()
        raw = " ".join([name, family, catalog]).strip()
        return cls(
            name=name,
            sec_type=re.sub(r"[^A-Z0-9]", "", (sec.get("type") or "").upper()),
            family=family,
            raw=raw,
            material=(sec.get("materialName") or sec.get("material") or "").upper().strip(),
            nums=tuple(_numbers(raw)),
        )

    def pick(self, i, default):
        """i-eme nombre du texte, ou default s'il n'y en a pas autant."""
        return self.nums[i] if len(self.nums) > i else default

    def is_steel(self) -> bool:
        return (is_steel_material_name(self.material)
                or any(tag in self.raw for tag in _STEEL_FAMILY_TAGS)
                or any(tag in self.sec_type for tag in _STEEL_TYPE_TAGS))


def _rolled_dims(h_mm, ratios):
    b_k, tw_min, tw_k, tf_min, tf_k = ratios
    return h_mm * b_k, max(tw_min, tw_k * h_mm), max(tf_min, tf_k * h_mm)


def _parse_sigma(s: _SectionText):
    h, b, hi, he, d, r, t, ri = (s.pick(i, dflt) for i, dflt in enumerate((32.0, 8.0, 8.0, 4.5, 1.6, 4.0, 0.3, 0.2)))
    clamp_sizes = (h, b, hi, he, r) if len(s.nums) >= 8 else (h, b)
    return {
        'kind': 'SIGMA',
        'width': _cm(b),
        'depth': _cm(h),
        'inner_web_height': _cm(hi),
        'outer_web_height': _cm(he),
        'web_offset': _cm(d),
        'return_lip': _cm(r),
        'thickness': _clamp_thickness_m(_cm(t), *(_cm(v) for v in clamp_sizes)),
        'inner_radius': _cm(ri),
        'overall_width': _cm(b),
        'overall_depth': _cm(h),
    }


def _parse_omega(s: _SectionText):
    h, b = s.pick(0, 14.0), s.pick(1, 6.0)
    top_b, t, r = s.pick(2, b), s.pick(3, 0.2), s.pick(4, 0.2)
    return {
        'kind': 'OMEGA',
        'width': _cm(b),
        'depth': _cm(h),
        'top_flange_width': _cm(top_b),
        'thickness': _clamp_thickness_m(_cm(t), _cm(h), _cm(b), _cm(top_b)),
        'fillet_radius': _cm(r),
        'overall_width': 2.0 * _cm(b) + _cm(top_b),
        'overall_depth': _cm(h),
    }


def _parse_zed(s: _SectionText):
    # "Z<h>X<b haut>X<b bas>X<ri>[X<retours>[X<angles>]] <epaisseur>" : 8, 6 ou 4 nombres
    parts = s.name.split()
    main = _numbers(parts[0]) if parts else []
    suffix = _numbers(parts[1]) if len(parts) > 1 else []
    t = suffix[0] if suffix else 0.2
    values = main if len(main) in (4, 6, 8) else [20.0, 6.0, 6.0, 0.2]
    h, b_top, b_bot, ri = values[:4]
    r_top, r_bot = values[4:6] or (0.0, 0.0)
    ang_bot, ang_top = values[6:8] or (90.0, 90.0)
    return {
        'kind': {8: 'ZED_SLOPED', 6: 'ZED'}.get(len(values), 'Z'),
        'depth': _cm(h),
        'top_flange_width': _cm(b_top),
        'bottom_flange_width': _cm(b_bot),
        'thickness': _clamp_thickness_m(_cm(t), _cm(h), _cm(b_top), _cm(b_bot)),
        'inner_radius': _cm(ri),
        'top_return': _cm(r_top),
        'bottom_return': _cm(r_bot),
        'bottom_return_angle_deg': float(ang_bot),
        'top_return_angle_deg': float(ang_top),
        'overall_width': _cm(b_top) + _cm(b_bot),
        'overall_depth': _cm(h),
    }


def _parse_rolled_i(s: _SectionText):
    m = _I_FAMILY.search(s.name)
    h_mm = float(m.group(2).replace(',', '.'))
    b_mm, tw_mm, tf_mm = _rolled_dims(h_mm, _I_RATIOS.get(m.group(1), _H_RATIOS))
    return {
        'kind': 'I',
        'width': _mm(b_mm),
        'depth': _mm(h_mm),
        'web': _mm(tw_mm),
        'flange': _mm(tf_mm),
        'overall_width': _mm(b_mm),
        'overall_depth': _mm(h_mm),
        'web_thickness': _mm(tw_mm),
        'flange_thickness': _mm(tf_mm),
    }


def _is_mm_rect_family(s: _SectionText) -> bool:
    return (any(tag in s.raw for tag in (' RCT', 'RHSC', 'RHSH', 'SHSC', 'SHSH'))
            or s.name.startswith(('RCT', 'RHS', 'SHS'))
            or s.family.startswith(('RCT', 'RHSC', 'RHSH', 'SHSC', 'SHSH')))


def _parse_mm_rect(s: _SectionText):
    n0 = s.pick(0, 40.0)
    n1 = s.pick(1, n0)
    depth, width = _mm(n0), _mm(n1)
    if 'RCT' in s.raw:
        return {'kind': 'RECT', 'width': width, 'depth': depth}
    thickness = _clamp_thickness_m(_mm(s.pick(2, min(n0, n1) * 0.10)), width, depth)
    return {'kind': 'RECTTUBE', 'width': width, 'depth': depth, 'thickness': thickness}


def _is_mm_circ_family(s: _SectionText) -> bool:
    return (any(tag in s.raw for tag in ('CHSC', 'CHSH'))
            or s.name.startswith('CHS') or s.family.startswith(('CHSC', 'CHSH')))


def _parse_mm_circ(s: _SectionText):
    n0 = s.pick(0, 40.0)
    diameter = _mm(n0)
    thickness = _clamp_thickness_m(_mm(s.pick(1, max(2.0, n0 * 0.10))), diameter)
    return {'kind': 'CIRCLETUBE', 'radius': diameter / 2.0, 'thickness': thickness}


def _parse_l_shape(s: _SectionText):
    a_mm, b_mm, t_mm = (float(g.replace(',', '.')) for g in _L_SHAPE.match(s.name).groups())
    return {'kind': 'ANGLE', 'width': _mm(a_mm), 'depth': _mm(b_mm),
            'thickness': _clamp_thickness_m(_mm(t_mm), _mm(a_mm), _mm(b_mm))}


def _parse_steel_angle(s: _SectionText):
    n0 = s.pick(0, 60.0)
    n1 = s.pick(1, n0)
    n2 = s.pick(2, max(4.0, min(n0, n1) * 0.10))
    return {'kind': 'ANGLE', 'width': _mm(n0), 'depth': _mm(n1),
            'thickness': _clamp_thickness_m(_mm(n2), _mm(n0), _mm(n1))}


def _parse_rect_tube(s: _SectionText):
    a = s.pick(0, 20.0)
    b = s.pick(1, a)
    width, depth = _cm(a), _cm(b)
    thickness = _clamp_thickness_m(_cm(s.pick(2, min(a, b) * 0.10)), width, depth)
    return {'kind': 'RECTTUBE', 'width': width, 'depth': depth, 'thickness': thickness}


def _parse_circ_tube(s: _SectionText):
    a = s.pick(0, 20.0)
    diameter = _cm(a)
    thickness = _clamp_thickness_m(_cm(s.pick(1, a * 0.10)), diameter)
    return {'kind': 'CIRCLETUBE', 'radius': diameter / 2.0, 'thickness': thickness}


def _is_mm_round(s: _SectionText) -> bool:
    return 'ROND' in s.raw or 'Ø' in s.raw or ('DIAM' in s.raw and 'TUBE' not in s.raw)


def _is_circle(s: _SectionText) -> bool:
    return (('CIRCULAR' in s.sec_type and 'TUBE' not in s.sec_type)
            or ('CIRC' in s.name and 'TUBE' not in s.name) or _is_mm_round(s))


def _parse_circle(s: _SectionText):
    to_m = _mm if _is_mm_round(s) else _cm
    return {'kind': 'CIRCLE', 'radius': to_m(s.pick(0, 20.0)) / 2.0}


def _parse_t_dissym(s: _SectionText):
    web = _cm(s.pick(0, 20.0))
    height = _cm(s.pick(1, 60.0))
    left_width = _cm(s.pick(2, 10.0))
    right_width = _cm(s.pick(5, 10.0))
    return {
        'kind': 'TDISSYMETRIC',
        'width': web + left_width + right_width,
        'depth': height,
        'web': web,
        'left_width': left_width,
        'left_thickness': _clamp_thickness_m(_cm(s.pick(3, 10.0)), height),
        'left_offset': _cm(s.pick(4, 20.0)),
        'right_width': right_width,
        'right_thickness': _clamp_thickness_m(_cm(s.pick(6, 10.0)), height),
        'right_offset': _cm(s.pick(7, 20.0)),
    }


def _parse_t(s: _SectionText):
    height = _cm(s.pick(0, 30.0))
    width = _cm(s.pick(2, s.pick(0, 30.0) * 0.6))
    return {'kind': 'T', 'width': width, 'depth': height,
            'web': _clamp_thickness_m(_cm(s.pick(1, 10.0)), height),
            'flange': _clamp_thickness_m(_cm(s.pick(3, 10.0)), width, height)}


def _is_u(s: _SectionText) -> bool:
    return (s.sec_type == 'STU' or 'CHANNEL' in s.name
            or bool(_U_FAMILY.search(s.name)) or bool(re.search(r"\bU\b", s.name)))


def _parse_u(s: _SectionText):
    m = _U_FAMILY.search(s.name)
    ratios = _U_RATIOS.get(m.group(1)) if m else None
    if ratios is None:
        height = _cm(s.pick(0, 30.0))
        width = _cm(s.pick(1, s.pick(0, 30.0) * 0.4))
        return {'kind': 'U', 'width': width, 'depth': height,
                'web': _clamp_thickness_m(_cm(s.pick(2, 4.0)), width, height),
                'flange': _clamp_thickness_m(_cm(s.pick(3, 4.0)), width, height)}
    h_mm = float(m.group(2).replace(',', '.'))
    b_mm, tw_mm, tf_mm = _rolled_dims(h_mm, ratios)
    return {'kind': 'U', 'width': _mm(b_mm), 'depth': _mm(h_mm), 'web': _mm(tw_mm), 'flange': _mm(tf_mm)}


def _is_angle(s: _SectionText) -> bool:
    return ('STANGLE' in s.sec_type or 'STUNEQUALANGLE' in s.sec_type
            or 'ANGLE' in s.name or bool(re.search(r"\bL\b", s.name)))


def _parse_angle(s: _SectionText):
    a = s.pick(0, 10.0)
    height = _cm(a)
    if len(s.nums) >= 3:
        width = _cm(s.pick(1, a))
        thickness = _cm(s.pick(2, min(a, s.pick(1, a)) * 0.15))
    else:
        width = height
        thickness = _cm(s.pick(1, a * 0.15))
    return {'kind': 'ANGLE', 'width': width, 'depth': height,
            'thickness': _clamp_thickness_m(thickness, width, height)}


def _parse_rect(s: _SectionText):
    a = s.pick(0, 20.0)
    return {'kind': 'RECT', 'width': _cm(a), 'depth': _cm(s.pick(1, a))}


# Regles essayees dans l'ordre : la premiere qui s'applique decide du profil
_SECTION_RULES = (
    (lambda s: s.name.startswith('V') or 'SIGMA' in s.sec_type or s.family.startswith('V'), _parse_sigma),
    (lambda s: s.name.startswith('W') or 'OMEGA' in s.sec_type or s.family.startswith('W'), _parse_omega),
    (lambda s: s.name.startswith('Z') or 'ZED' in s.sec_type or s.family.startswith('Z'), _parse_zed),
    (lambda s: bool(_I_FAMILY.search(s.name)), _parse_rolled_i),
    (_is_mm_rect_family, _parse_mm_rect),
    (_is_mm_circ_family, _parse_mm_circ),
    (lambda s: bool(_L_SHAPE.match(s.name)), _parse_l_shape),
    (lambda s: 'ANGLE' in s.sec_type and s.is_steel(), _parse_steel_angle),
    (lambda s: ('STRECTANGULARTUBE' in s.sec_type or 'STSQUARETUBE' in s.sec_type
                or ('TUBE' in s.name and 'RECT' in s.name)), _parse_rect_tube),
    (lambda s: 'STCIRCULARTUBE' in s.sec_type or ('TUBE' in s.name and 'CIRC' in s.name), _parse_circ_tube),
    (_is_circle, _parse_circle),
    (lambda s: 'TDISSYMETRIC' in s.sec_type, _parse_t_dissym),
    (lambda s: s.sec_type == 'STT' or bool(re.search(r"\bT\b", s.name)), _parse_t),
    (_is_u, _parse_u),
    (_is_angle, _parse_angle),
    (lambda s: ('STRECTANGULAR' in s.sec_type or 'STSQUARE' in s.sec_type
                or 'RECT' in s.name or 'SQUARE' in s.name), _parse_rect),
)


def parse_section_dims(sec: dict):
    """Dimensions (m) du profil d'une section Advance Design, None si non reconnu."""
    text = _SectionText.of(sec)
    for applies, parse in _SECTION_RULES:
        if applies(text):
            return parse(text)
    return None


def _dim(dims: dict, key, default=0.0) -> float:
    return float(dims.get(key, default) or default)


def _zed_bounds(dims: dict):
    half_depth = _dim(dims, 'depth') / 2.0
    return (-_dim(dims, 'bottom_flange_width'), -half_depth, _dim(dims, 'top_flange_width'), half_depth)


def _omega_bounds(dims: dict):
    width = _dim(dims, 'width')
    half_depth = _dim(dims, 'depth') / 2.0
    top_b = _dim(dims, 'top_flange_width', width)
    half_total = _dim(dims, 'overall_width', 2.0 * width + top_b) / 2.0
    return (-half_total, -half_depth, half_total, half_depth)


def _sigma_bounds(dims: dict):
    half_depth = _dim(dims, 'depth') / 2.0
    y_max = max(_dim(dims, 'width'), _dim(dims, 'web_offset') + _dim(dims, 'thickness', 0.003))
    return (0.0, -half_depth, y_max, half_depth)


def _centered_bounds(dims: dict):
    width, depth = _dim(dims, 'width'), _dim(dims, 'depth')
    if width > 0.0 and depth > 0.0:
        return (-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    return None


def _round_bounds(dims: dict):
    radius = _dim(dims, 'radius')
    if radius > 0.0:
        return (-radius, -radius, radius, radius)
    return _centered_bounds(dims)


_BOUNDS_BY_KIND = {
    'Z': _zed_bounds, 'ZED': _zed_bounds, 'ZED_SLOPED': _zed_bounds,
    'OMEGA': _omega_bounds,
    'SIGMA': _sigma_bounds,
    'PIPE': _round_bounds, 'CHS': _round_bounds,
    **{kind: _centered_bounds for kind in ('RECT', 'RHS', 'SHS', 'I', 'T', 'ANGLE', 'U', 'C', 'T_DISSYM')},
}


def profile_bounds_from_dims(dims: dict):
    """(ymin, zmin, ymax, zmax) du profil dans son repere local, None si type sans regle."""
    dims = dims or {}
    bounds = _BOUNDS_BY_KIND.get(str(dims.get('kind') or '').upper())
    return bounds(dims) if bounds else None


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


def offset_polygon2(poly2, dy):
    return [[float(x), float(y) + float(dy)] for x, y in poly2]


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


def t_profile_polygon(dims):
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


def t_dissym_profile_polygon(dims):
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


def l_profile_polygon(dims):
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


def u_profile_polygon(dims):
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


def zed_profile_polygon(dims):
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


def omega_profile_polygon(dims):
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


def sigma_profile_polygon(dims):
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


def default_linear_dims(sec: dict, beam_type: str):
    parsed = parse_section_dims(sec)
    if parsed:
        return parsed
    role = (beam_type or '').lower()
    if 'column' in role or 'bar' in role or 'strut' in role:
        return {'kind': 'RECT', 'width': 0.25, 'depth': 0.25}
    return {'kind': 'RECT', 'width': 0.12, 'depth': 0.30}


def ref_value(ref):
    """Valeur d'une reference API AD : ``ref['value']`` si dict, sinon ``ref``."""
    if isinstance(ref, dict):
        return ref.get("value")
    return ref


# --- Jarrets (goussets) : uniquement sur profiles I/H de catalogue ------------

def is_i_or_h_catalog_section(sec: dict):
    dims = parse_section_dims(sec or {}) or {}
    if str(dims.get('kind', '')).upper() != 'I':
        return False
    name = (sec.get('name') or '').upper().strip()
    return bool(re.search(r'\b(IPE|IPN|HEA|HEB|HEM)\s*\d', name))


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


def resolve_haunch_section_dims(base_sec: dict, haunch: dict, sections: dict, beam_type: str):
    htype = str((haunch or {}).get('haunchSectionType') or 'identical').lower()
    if htype == 'imposee':
        sec_ref = sections.get(ref_value((haunch or {}).get('haunchSection'))) or base_sec
    else:
        sec_ref = base_sec
    dims = default_linear_dims(sec_ref, beam_type).copy()
    dims['_ad_haunch_section_type'] = htype
    dims['_ad_haunch_section_name'] = (sec_ref or {}).get('name')
    return dims


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


# --- Profiles composes CS1..CS7 ---------------------------------------------

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


def _ngon(radius, cx=0.0, cy=0.0, n=CIRCLE_SIDES):
    r = float(radius)
    return [
        [cx + r * math.cos(2.0 * math.pi * i / n), cy + r * math.sin(2.0 * math.pi * i / n)]
        for i in range(n)
    ]


def profile_polygon(dims: dict):
    """Contour(s) 2D d'une section, centres sur l'origine du repere local.

    Retourne {'outer': [[x, y], ...], 'holes': [[[x, y], ...], ...]} ou None si
    dims est vide. x = direction largeur, y = direction hauteur (comme les
    helpers *_profile_polygon et IfcRectangleProfileDef). Les boucles sont
    fermees implicitement (premier point != dernier) et enroulees dans le meme
    sens ; le consommateur inverse les trous pour la tesselation.
    """
    if not dims:
        return None
    kind = str(dims.get('kind', 'RECT')).upper()

    def _rect(w, d):
        w = float(w)
        d = float(d)
        return [[-w / 2.0, -d / 2.0], [w / 2.0, -d / 2.0], [w / 2.0, d / 2.0], [-w / 2.0, d / 2.0]]

    if kind == 'CIRCLE':
        return {'outer': _ngon(dims.get('radius', 0.10)), 'holes': []}

    if kind == 'CIRCLETUBE':
        r = float(dims.get('radius', 0.10))
        t = min(float(dims.get('thickness', r * 0.1)), r * 0.99)
        return {'outer': _ngon(r), 'holes': [_ngon(r - t)]}

    if kind == 'RECTTUBE':
        w = float(dims.get('width', 0.20))
        d = float(dims.get('depth', 0.20))
        t = min(float(dims.get('thickness', min(w, d) * 0.1)), min(w, d) / 2.0 * 0.99)
        return {'outer': _rect(w, d), 'holes': [_rect(w - 2.0 * t, d - 2.0 * t)]}

    builders = {
        'I': i_section_polygon,
        'T': t_profile_polygon,
        'TDISSYMETRIC': t_dissym_profile_polygon,
        'U': u_profile_polygon,
        'ANGLE': l_profile_polygon,
        'Z': zed_profile_polygon,
        'ZED': zed_profile_polygon,
        'ZED_SLOPED': zed_profile_polygon,
        'OMEGA': omega_profile_polygon,
        'SIGMA': sigma_profile_polygon,
    }
    fn = builders.get(kind)
    if fn is not None:
        return {'outer': [[float(x), float(y)] for x, y in fn(dims)], 'holes': []}

    return {'outer': _rect(dims.get('width', 0.20), dims.get('depth', 0.20)), 'holes': []}


if __name__ == '__main__':
    def _area(loop):
        s = 0.0
        for i in range(len(loop)):
            x1, y1 = loop[i]
            x2, y2 = loop[(i + 1) % len(loop)]
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0

    _cases = {
        'RECT': {'kind': 'RECT', 'width': 0.3, 'depth': 0.5},
        'CIRCLE': {'kind': 'CIRCLE', 'radius': 0.1},
        'CIRCLETUBE': {'kind': 'CIRCLETUBE', 'radius': 0.1, 'thickness': 0.01},
        'RECTTUBE': {'kind': 'RECTTUBE', 'width': 0.2, 'depth': 0.1, 'thickness': 0.008},
        'I': parse_section_dims({'name': 'IPE 300', 'materialName': 'S275'}),
        'U': parse_section_dims({'name': 'UPN 200', 'materialName': 'S275'}),
        'ANGLE': parse_section_dims({'name': 'L 100X100X10', 'materialName': 'S275'}),
        'T': {'kind': 'T', 'width': 0.2, 'depth': 0.3, 'web': 0.01, 'flange': 0.015},
        'Z': {'kind': 'Z', 'depth': 0.2, 'top_flange_width': 0.06, 'bottom_flange_width': 0.06, 'thickness': 0.003},
        'OMEGA': {'kind': 'OMEGA', 'depth': 0.14, 'width': 0.06, 'top_flange_width': 0.06, 'thickness': 0.003},
        'SIGMA': {'kind': 'SIGMA', 'depth': 0.32, 'width': 0.08},
        'unknown': {'kind': 'WAT', 'width': 0.1, 'depth': 0.2},
    }
    for _label, _d in _cases.items():
        _p = profile_polygon(_d)
        assert _p is not None and len(_p['outer']) >= 3, _label
        assert _area(_p['outer']) > 1e-6, _label
        for _hole in _p['holes']:
            assert 1e-6 < _area(_hole) < _area(_p['outer']), _label
    assert profile_polygon(None) is None
    assert len(profile_polygon({'kind': 'CIRCLE', 'radius': 0.1})['outer']) == CIRCLE_SIDES
    assert len(profile_polygon({'kind': 'CIRCLETUBE', 'radius': 0.1, 'thickness': 0.01})['holes'][0]) == CIRCLE_SIDES
    assert profile_polygon({'kind': 'RECTTUBE', 'width': 0.2, 'depth': 0.1, 'thickness': 0.008})['holes']
    print('section_geometry self-check OK')
