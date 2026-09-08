# -*- coding: utf-8 -*-
"""
test_profile_render.py
Garde-fou du rendu des profils 3D :
- repere de section identique a l'export IFC (profils non bi-symetriques non
  inverses) ;
- orientation : depth->vertical a beta=0, permutation a beta=90 ;
- excentrement applique et tournant avec beta ;
- section variable (loft) ;
- jarrets (goussets) : debut/fin, haut/bas/haut_et_bas.

Depend de vtk + ad_model_data (PySide6). `python test_profile_render.py`.
"""

import math

from viewer_widget import VTKViewerWidget
import ad_model_data as md

_SECOBJ = {1: {"name": "IPE 300", "type": "I_SYMETRIC"}}  # width 0.15, depth 0.30


def _section(angle_rad=0.0, excentration=None):
    # sectionOrientationAngle de l'API AD est en radians
    el = {
        "generalBeamType": "Beam",
        "section": {"value": 1},
        "sectionOrientationAngle": angle_rad,
        "geomPtStart": {"x": 0, "y": 0, "z": 0},
        "geomPtEnd": {"x": 4, "y": 0, "z": 0},
    }
    if excentration is not None:
        el["sectionExcentration"] = {"option": excentration}
    return md._build_line_section_render(el, el["geomPtStart"], el["geomPtEnd"], _SECOBJ)


def _profile_pd(section, seg=((0, 0, 0), (4, 0, 0))):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._color_by_section = False
    return w._build_profiles_polydata([list(seg)], [section], element_indexes=[0])


def _bbox(section):
    return _profile_pd(section).GetBounds()  # xmin xmax ymin ymax zmin zmax


def _bbox_pd(section):
    return _profile_pd(section, seg=((0, 0, 0), (6, 0, 0)))


def test_section_frame_matches_ifc_convention():
    # beam le long de +X : u = up_ref x beam = +Y, v = beam x u = +Z (comme l'export IFC)
    u, v = VTKViewerWidget._section_frame((0, 0, 0), (1, 0, 0))
    assert u == (0.0, 1.0, 0.0), u
    assert v == (0.0, 0.0, 1.0), v


def test_zed_section_not_mirrored():
    # Z : semelle haute -> +x du polygone, semelle basse -> -x
    # non miroir (u=+Y) => correlation Y*Z du solide > 0
    el = {"generalBeamType": "Beam", "section": {"value": 1},
          "sectionOrientationAngle": 0.0,
          "geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 4, "y": 0, "z": 0}}
    sec = md._build_line_section_render(
        el, el["geomPtStart"], el["geomPtEnd"], {1: {"name": "Z200X60X60X2"}}
    )
    assert sec["dims"]["kind"] in ("Z", "ZED", "ZED_SLOPED")
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._color_by_section = False
    pd = w._build_profiles_polydata([[(0, 0, 0), (4, 0, 0)]], [sec], element_indexes=[0])
    corr = sum(pd.GetPoint(i)[1] * pd.GetPoint(i)[2] for i in range(pd.GetNumberOfPoints()))
    assert corr > 1e-4, corr


def test_angle_read_as_radians():
    # une valeur en radians (pi/2) doit produire une rotation de 90 deg, pas de 1.57 deg
    assert abs(_section(math.pi / 2)["angle_rad"] - math.pi / 2) < 1e-9


def test_orientation_beta0_and_beta90():
    b0 = _bbox(_section(0.0))
    assert abs((b0[5] - b0[4]) - 0.30) < 0.01   # depth -> vertical (Z)
    assert abs((b0[3] - b0[2]) - 0.15) < 0.01   # width -> lateral (Y)
    b90 = _bbox(_section(math.pi / 2))
    assert abs((b90[5] - b90[4]) - 0.15) < 0.01  # permutation
    assert abs((b90[3] - b90[2]) - 0.30) < 0.01


def test_eccentricity_applied_and_rotates_with_beta():
    assert _section(0.0, "center_alignment")["offset"] in ([0.0, 0.0], [-0.0, -0.0])
    off0 = _section(0.0, "droite_haut")["offset"]
    off90 = _section(math.pi / 2, "droite_haut")["offset"]
    assert abs(off0[0]) + abs(off0[1]) > 0.1
    # rotation de 90 deg : les modules des composantes permutent
    assert abs(abs(off90[0]) - abs(off0[1])) < 1e-6
    assert abs(abs(off90[1]) - abs(off0[0])) < 1e-6


_VARIABLE_SECOBJ = {1: {"name": "IPE 300", "type": "I_SYMETRIC"},
                    2: {"name": "IPE 450", "type": "I_SYMETRIC"}}


def _variable_section(general_beam_type):
    el = {
        "generalBeamType": general_beam_type,
        "section": {"value": 1}, "sectionEnd": {"value": 2},
        "sectionOrientationAngle": 0.0,
        "geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 4, "y": 0, "z": 0},
    }
    return md._build_line_section_render(el, el["geomPtStart"], el["geomPtEnd"], _VARIABLE_SECOBJ)


def test_variable_section_lofts_between_dims():
    sec = _variable_section("VariableBeam")
    assert sec["dims_end"] is not None and abs(sec["dims_end"]["depth"] - 0.45) < 1e-6
    b = _bbox(sec)
    # profondeur qui varie -> hauteur du solide entre 0.30 et 0.45
    assert 0.30 - 0.01 < (b[5] - b[4]) < 0.45 + 0.01


def test_variable_section_detected_from_prefixed_enum():
    # AD renvoie souvent un enum prefixe ("EType::VariableBeam", "ExxxVariableBeam")
    for token in ("eLinearElementFEMType::VariableBeam", "EGeneralBeamTypeVariableBeam"):
        sec = _variable_section(token)
        assert sec["dims_end"] is not None, token
        assert abs(sec["dims_end"]["depth"] - 0.45) < 1e-6, token


def test_resolve_model_references_collects_section_end_and_haunch():
    saved_s, saved_m = md.get_sections, md.get_materials
    md.get_sections = lambda host, ids: [{"name": f"S{e}"} for e in ids]
    md.get_materials = lambda host, ids: [{"name": f"M{e}"} for e in ids]
    try:
        elements = [{
            "material": {"value": 7},
            "section": {"value": 10},
            "sectionEnd": {"value": 11},
            "haunchStart": {"haunchSection": {"value": 12}},
            "haunchEnd": {"haunchSection": 13},
        }]
        refs = md._resolve_model_references("http://x", elements, [])
    finally:
        md.get_sections, md.get_materials = saved_s, saved_m
    assert {10, 11, 12, 13} <= refs["linear_section_eids"]
    assert set(refs["linear_section_obj_by_eid"]) == {10, 11, 12, 13}


_HAUNCH_SECOBJ = {1: {"name": "IPE 300", "type": "I_SYMETRIC"}}  # depth 0.30


def _haunched(hs_pos="no_haunch", he_pos="no_haunch", name="IPE 300",
              general_beam_type="Beam"):
    el = {
        "generalBeamType": general_beam_type,
        "section": {"value": 1},
        "sectionOrientationAngle": 0.0,
        "haunchStart": {"haunchPosition": hs_pos, "haunchSectionType": "identical",
                        "lengthType": "ratio", "lengthRatio": 0.3,
                        "heightType": "ratio", "heightRatio": 2.0},
        "haunchEnd": {"haunchPosition": he_pos, "haunchSectionType": "identical",
                      "lengthType": "ratio", "lengthRatio": 0.25,
                      "heightType": "ratio", "heightRatio": 2.0},
        "geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 6, "y": 0, "z": 0},
    }
    return md._build_line_section_render(
        el, el["geomPtStart"], el["geomPtEnd"], {1: {"name": name, "type": "I_SYMETRIC"}}
    )


def _zrange(pd, x_pred):
    zs = [pd.GetPoint(i)[2] for i in range(pd.GetNumberOfPoints()) if x_pred(pd.GetPoint(i)[0])]
    return (min(zs), max(zs)) if zs else (None, None)


def test_haunch_pieces_counts_and_shape():
    assert _haunched()["haunches"] == []
    assert len(_haunched("bas")["haunches"]) == 1
    assert len(_haunched("haut_et_bas")["haunches"]) == 2
    assert len(_haunched("bas", "haut")["haunches"]) == 2
    piece = _haunched("bas")["haunches"][0]
    assert piece["t_start"] == 0.0 and abs(piece["t_end"] - 0.3) < 1e-9
    ys = [p[1] for p in piece["poly_start"]]
    ye = [p[1] for p in piece["poly_end"]]
    assert min(ys) < -0.6                       # coin plongeant sous la poutre
    assert abs(max(ye) - min(ye)) < 1e-9        # cote contact ecrase a plat


def test_haunch_only_on_i_catalog_and_not_variable():
    assert _haunched("bas", name="RHS 200X100X8")["haunches"] == []
    assert _haunched("bas", general_beam_type="VariableBeam")["haunches"] == []


def test_haunch_render_adds_wedge_at_end_only():
    sec = _haunched(hs_pos="bas")
    pd = _bbox_pd(sec)
    znear = _zrange(pd, lambda x: x < 0.01)[0]      # extremite avec jarret
    zfar = _zrange(pd, lambda x: x > 2.0)[0]        # au-dela du jarret : poutre seule
    assert znear < -0.6 and zfar is not None and zfar > -0.2

    sec = _haunched(he_pos="haut")
    pd = _bbox_pd(sec)
    zend = _zrange(pd, lambda x: x > 5.99)[1]
    zmid = _zrange(pd, lambda x: x < 4.0)[1]
    assert zend > 0.6 and zmid is not None and zmid < 0.2


# --- profiles composes CS1..CS7 --------------------------------------------

def _combined(name, excentration=None, angle_rad=0.0):
    el = {"generalBeamType": "Beam", "section": {"value": 1},
          "sectionOrientationAngle": angle_rad,
          "geomPtStart": {"x": 0, "y": 0, "z": 0}, "geomPtEnd": {"x": 4, "y": 0, "z": 0}}
    if excentration is not None:
        el["sectionExcentration"] = {"option": excentration}
    return md._build_line_section_render(
        el, el["geomPtStart"], el["geomPtEnd"], {1: {"name": name, "type": "COMBINED"}}
    )


def test_combined_section_two_pieces_render():
    for name in ("CS1 IPE200 IPE200", "CS3 HEA160 HEA160",
                 "CS6 UPN200 UPN200", "CS7 L80X80X8 L80X80X8"):
        sec = _combined(name)
        assert sec["combined"] is not None and len(sec["combined"]) == 2, name
        assert sec["dims_end"] is None, name
        pd = _profile_pd(sec)
        assert pd.GetNumberOfCells() > 0, name
        arr = pd.GetCellData().GetArray("element_index")
        assert arr is not None and arr.GetNumberOfTuples() == pd.GetNumberOfCells(), name


def test_non_combined_name_has_no_combined():
    assert _combined("IPE 300")["combined"] is None


def test_combined_offset_uses_polygon_set_bbox():
    import section_geometry as sg
    # l'excentrement d'un profil compose vient de la bbox de l'ENSEMBLE des 2
    # polygones (pas d'un ``dims``). center_alignment -> -centre de la bbox.
    sec = _combined("CS3 HEA160 HEA160", "center_alignment")
    xn, yn, xx, yx = sg.polygon_set_bounds(sec["combined"])
    assert abs(sec["offset"][0] - (-(xn + xx) / 2.0)) < 1e-9
    assert abs(sec["offset"][1] - (-(yn + yx) / 2.0)) < 1e-9
    # CS3 = I empiles selon la profondeur -> bbox non centree -> offset y non nul
    assert abs(sec["offset"][1]) > 0.05


def test_combined_cs3_stacked_in_depth_direction():
    # CS3 = 2 HEA160 empiles selon la PROFONDEUR : Z-span ~ 2 x depth, Y-span ~ 1 x width.
    # Si le repere u/v etait permute, l'empilement serait lateral (Y-span double).
    b = _profile_pd(_combined("CS3 HEA160 HEA160")).GetBounds()
    y_span, z_span = b[3] - b[2], b[5] - b[4]
    assert z_span > 2 * y_span            # empile en hauteur, pas en largeur
    assert 0.28 < z_span < 0.36           # ~ 2 x 0.152 (depth HEA160 approx)


# --- selection en mode profils : recolorage par echange de scalaires -------

def _profiles_widget_with_cache(color_by_section=False):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._color_by_section = color_by_section
    w.selection_color = (1.0, 0.0, 0.0)
    w.linear_color = (0.4, 0.6, 1.0)
    w._selected_items = []
    w._section_color_map = {}
    w._model_data = {"line_properties": [{"section": f"S{i}"} for i in range(3)]}
    lines = [[(0, i, 0), (4, i, 0)] for i in range(3)]
    secs = [_section() for _ in range(3)]
    base_pd = w._build_profiles_polydata(lines, secs, element_indexes=[0, 1, 2])
    w._profiles_base_pd = base_pd
    w._profiles_base_colors = None
    sc = base_pd.GetCellData().GetArray("section_colors")
    if sc is not None:
        import vtk
        w._profiles_base_colors = vtk.vtkUnsignedCharArray()
        w._profiles_base_colors.DeepCopy(sc)
    w._profiles_actor = w._make_surface_actor(base_pd, w.linear_color, 1.0)
    return w


def test_selection_recolor_swaps_scalars_without_rebuild():
    w = _profiles_widget_with_cache()
    base_pd = w._profiles_base_pd
    n_cells = base_pd.GetNumberOfCells()

    # aucune selection : pas de scalaires actifs
    w._apply_profiles_selection_colors()
    assert base_pd.GetCellData().GetScalars() is None

    # selection de l'element 11 : meme polydata (pas de reconstruction),
    # ses cellules en rouge, les autres en linear_color
    w._selected_items = [{"role": "lines", "index": 1}]
    w._apply_profiles_selection_colors()
    assert w._profiles_base_pd is base_pd                  # aucune reconstruction
    assert base_pd.GetNumberOfCells() == n_cells
    sc = base_pd.GetCellData().GetScalars()
    ei = base_pd.GetCellData().GetArray("element_index")
    assert sc is not None and sc.GetNumberOfTuples() == n_cells
    sel = other = 0
    for i in range(n_cells):
        rgb = tuple(int(sc.GetComponent(i, k)) for k in range(3))
        if int(ei.GetTuple1(i)) == 1:
            assert rgb == (255, 0, 0)
            sel += 1
        else:
            assert rgb == (102, 153, 255)   # round(0.4*255), round(0.6*255), 255
            other += 1
    assert sel > 0 and other > 0

    # deselection : retour a l'etat sans scalaires
    w._selected_items = []
    w._apply_profiles_selection_colors()
    assert base_pd.GetCellData().GetScalars() is None


def test_selection_recolor_preserves_section_colors():
    w = _profiles_widget_with_cache(color_by_section=True)
    # base_colors capturees
    assert w._profiles_base_colors is not None
    base_pd = w._profiles_base_pd
    ei = base_pd.GetCellData().GetArray("element_index")
    w._selected_items = [{"role": "lines", "index": 1}]
    w._apply_profiles_selection_colors()
    sc = base_pd.GetCellData().GetScalars()
    for i in range(base_pd.GetNumberOfCells()):
        rgb = tuple(int(sc.GetComponent(i, k)) for k in range(3))
        if int(ei.GetTuple1(i)) == 1:
            assert rgb == (255, 0, 0)
        else:
            # couleur de section conservee (pas linear_color)
            b = w._profiles_base_colors
            assert rgb == tuple(int(b.GetComponent(i, k)) for k in range(3))


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for _fn in _tests:
        _fn()
        print("ok", _fn.__name__)
    print(f"\n{len(_tests)} tests OK")
