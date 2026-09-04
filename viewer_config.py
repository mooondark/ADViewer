# -*- coding: utf-8 -*-
"""
viewer_config.py
Constantes, couleurs de thème, i18n, exceptions et helpers utilitaires
pour le Viewer 3D Advance Design.

Ce module ne dépend d'aucun autre module du projet.
Il peut être importé par tous les autres modules.

⚠️  Piège des globales mutables : les couleurs (BG, ACCENT, etc.) sont
    réassignées par _set_fallback_colors() via `global`.
    - Ne JAMAIS faire `from viewer_config import BG` car la valeur serait figée.
    - Utiliser `import viewer_config as cfg` puis `cfg.BG`, OU
    - Faire `from viewer_config import *` puis appeler le wrapper
      set_active_theme() défini ci-dessous qui re-synchronise les globales
      dans le module appelant.
"""

import os
import sys
import ctypes
from PySide6.QtGui import QIcon


# ======================================================================
#  Constantes applicatives
# ======================================================================

APP_VERSION = "1.89.3"
DEFAULT_HOST = "http://localhost:52000"
DEFAULT_API_SERVER_EXE = r"C:\Program Files\Graitec\Advance Design\2027\Bin\AD.API.Srv.exe"
CONFIG_FILE = "config.ini"

# qt-material theme mapping
QT_MATERIAL_THEMES = {
    "dark": "dark_blue.xml",
    "light": "light_blue.xml",
}

DEFAULT_THEME = "light"
DEFAULT_VIEW_PROJECTION = "perspective"


# ======================================================================
#  Helpers de chemins et d'application
# ======================================================================

def resource_path(relative_path):
    """Fonctionne en dev et compilé avec PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def load_app_icon(*candidates):
    for candidate in candidates:
        if not candidate:
            continue
        path = resource_path(candidate)
        if os.path.isfile(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def set_windows_app_user_model_id(app_id: str = "graitec.viewer.desktop"):
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def normalize_windows_path(path: str) -> str:
    if not path:
        return path
    path = path.strip().strip('"').strip("'")
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = os.path.normpath(path)
    path = path.replace("/", "\\")
    return path


# ======================================================================
#  Couleurs de thème (mutables — voir avertissement en tête de fichier)
# ======================================================================

# Fallback colors for VTK and custom widgets (used when qt-material is not yet applied)
BG = "#EEF2F7"
PANEL = "#FFFFFF"
BORDER = "#C9D4E3"
ACCENT = "#2F6FDB"
ACCENT2 = "#2F9E66"
WARN = "#C98A12"
ERROR_COL = "#D94A4A"
FG = "#1F2937"
FG_DIM = "#5B6B82"
INPUT_BG = "#F8FAFD"
INPUT_FG = "#1F2937"
BTN_BG = "#2F6FDB"
VTK_BG = (0.96, 0.97, 0.99)

# Dark fallback
_DARK_BG = "#1C2333"
_DARK_PANEL = "#252E42"
_DARK_BORDER = "#2E3A55"
_DARK_ACCENT = "#4A7FE0"
_DARK_ACCENT2 = "#2CB67D"
_DARK_WARN = "#E8A840"
_DARK_ERROR = "#E05555"
_DARK_FG = "#E8EBF0"
_DARK_FG_DIM = "#8899BB"
_DARK_INPUT_BG = "#1A2236"
_DARK_INPUT_FG = "#D4E1FF"
_DARK_BTN_BG = "#3B4B6D"
_DARK_VTK_BG = (0.369, 0.404, 0.443)

# Light fallback
_LIGHT_BG = "#EEF2F7"
_LIGHT_PANEL = "#FFFFFF"
_LIGHT_BORDER = "#C9D4E3"
_LIGHT_ACCENT = "#2F6FDB"
_LIGHT_ACCENT2 = "#2F9E66"
_LIGHT_WARN = "#C98A12"
_LIGHT_ERROR = "#D94A4A"
_LIGHT_FG = "#1F2937"
_LIGHT_FG_DIM = "#5B6B82"
_LIGHT_INPUT_BG = "#F8FAFD"
_LIGHT_INPUT_FG = "#1F2937"
_LIGHT_BTN_BG = "#2F6FDB"
_LIGHT_VTK_BG = (0.9608, 0.9608, 0.9608)  # #f5f5f5


def _set_fallback_colors(theme_name: str):
    global BG, PANEL, BORDER, ACCENT, ACCENT2, WARN, ERROR_COL, FG, FG_DIM, INPUT_BG, INPUT_FG, BTN_BG, VTK_BG
    if theme_name == "dark":
        BG = _DARK_BG
        PANEL = _DARK_PANEL
        BORDER = _DARK_BORDER
        ACCENT = _DARK_ACCENT
        ACCENT2 = _DARK_ACCENT2
        WARN = _DARK_WARN
        ERROR_COL = _DARK_ERROR
        FG = _DARK_FG
        FG_DIM = _DARK_FG_DIM
        INPUT_BG = _DARK_INPUT_BG
        INPUT_FG = _DARK_INPUT_FG
        BTN_BG = _DARK_BTN_BG
        VTK_BG = _DARK_VTK_BG
    else:
        BG = _LIGHT_BG
        PANEL = _LIGHT_PANEL
        BORDER = _LIGHT_BORDER
        ACCENT = _LIGHT_ACCENT
        ACCENT2 = _LIGHT_ACCENT2
        WARN = _LIGHT_WARN
        ERROR_COL = _LIGHT_ERROR
        FG = _LIGHT_FG
        FG_DIM = _LIGHT_FG_DIM
        INPUT_BG = _LIGHT_INPUT_BG
        INPUT_FG = _LIGHT_INPUT_FG
        BTN_BG = _LIGHT_BTN_BG
        VTK_BG = _LIGHT_VTK_BG


def set_active_theme(theme_name: str):
    _set_fallback_colors(theme_name)
    return {"name": theme_name}


# ======================================================================
#  Constantes d'affichage
# ======================================================================

LEFT_PANEL_INITIAL_WIDTH = 245

LINEAR_LINE_WIDTH = 2.0
PLANAR_LINE_WIDTH = 2.0
OPENING_LINE_WIDTH = 2.5
LOAD_AREA_LINE_WIDTH = 1.8

SUPPORT_PUNCTUAL_SIZE = 0.35
SUPPORT_PUNCTUAL_LINE_WIDTH = 2.0
SUPPORT_LINEAR_LINE_WIDTH = 2.5
SUPPORT_PLANAR_LINE_WIDTH = 2.5

INITIAL_TRANSPARENCY_PERCENT = 30

MESH_LINE_WIDTH = 1.0
MESH_COLOR = (0.0, 1.0, 0.0)  # #00ff00

# Charges ponctuelles
PUNCTUAL_LOAD_COLOR = (1.0, 0.45, 0.0)   # orange vif
PUNCTUAL_LOAD_SCALE = 1.0                 # facteur d'échelle par défaut (m par kN_max)

# Charges linéaires
LINEAR_LOAD_COLOR = (1.0, 0.765, 0.059)  # #ffc30f
LINEAR_LOAD_SCALE = 1.0                  # facteur d'échelle par défaut (m par kN_max)
LINEAR_LOAD_ARROW_WIDTH = 0.02           # rayon de tige en mètres (défaut)

# Charges surfaciques
PLANAR_LOAD_COLOR = (1.0, 0.561, 0.059)  # #ff8f0f
PLANAR_LOAD_SCALE = 1.0                  # facteur d'échelle par défaut (m par kN_max)
PLANAR_LOAD_ARROW_WIDTH = 0.02           # rayon de tige en mètres (défaut)


# ======================================================================
#  Listes de types d'éléments
# ======================================================================

PUNCTUAL_SUPPORT_TYPES = [
    "ElementRigidPunctualSupport",
    "ElementElasticPunctualSupport",
    "ElementTCPunctualSupport",
    "ElementAdvancedPunctualSupport",
]

LINEAR_SUPPORT_TYPES = [
    "ElementRigidLinearSupport",
    "ElementElasticLinearSupport",
    "ElementTCLinearSupport",
    "ElementAdvancedLinearSupport",
]

PLANAR_SUPPORT_TYPES = [
    "ElementRigidPlanarSupport",
    "ElementElasticPlanarSupport",
    "ElementTCPlanarSupport",
    "ElementAdvancedPlanarSupport",
]


# ======================================================================
#  Dictionnaires de libellés de types
# ======================================================================

PLANAR_ELEMENT_TYPE_LABELS = {
    "membrane": "Membrane",
    "plate": "Plaque",
    "shell": "Coque",
    "deformation_plane": "Déformation plane",
    "steeldeck": "Bac acier",
    "layeredshell": "Coque multicouche",
}

LINEAR_BEAM_TYPE_LABELS = {
    "bar": "Barre",
    "beamWStandardBending": "Poutre",
    "sbeam": "Poutre courte",
    "variablebeam": "Poutre variable",
    "tie": "Tirant",
    "strut": "Buton",
    "cable": "Câble",
    "rigid": "Rigide",
    "CompositeBeamSimpleBeam": "Poutre mixte",
    "CompositeBeamSbeam": "Poutre courte mixte",
}


# ======================================================================
#  Internationalisation (i18n)
# ======================================================================

MSG_UI = {
    "project": "Projet",
    "project_file": "Fichier .fto",
    "api_url": "URL API",
    "browse": "Parcourir...",
    "start_api": "Démarrer API",
    "stop_api": "Arrêter API",

    "actions": "Actions",
    "load_model": "Charger le modèle",
    "loading": "Chargement...",
    "fit_view": "Zoom étendu",
    "iso_view": "Vue isométrique",
    "transparency": "Transparence",
    "transparency_value": "{value} %",

    "display": "Affichage",
    "display_mode": "Mode de visualisation",
    "display_wireframe": "Filaire",
    "display_hidden_faces": "Faces cachées",
    "display_wire_hidden": "Filaire + Faces cachées",
    "display_full": "Rendu plein",

    "show_lines": "Afficher filaires",
    "show_planars": "Afficher surfaciques",
    "show_load_areas": "Afficher parois",
    "show_support_punctual": "Afficher appuis ponctuels",
    "show_support_linear": "Afficher appuis linéaires",
    "show_support_planar": "Afficher appuis surfaciques",
    "show_marker": "Afficher repère",
    "show_mesh": "Afficher le maillage",
    "show_punctual_loads": "Afficher charges ponctuelles",
    "color_by_section": "Couleur par section",

    "view3d": "Vue 3D",
    "journal": "Journal",
    "properties": "Propriétés",
    "select_element": "Sélectionnez un élément.",
    "multi_select_properties_unavailable": "Sélection multiple - impossible d'afficher les propriétés.",
    "multi_select_results_heterogeneous": "Sélection hétérogène - résultats non disponibles.",
    "multi_select_results_linear_hint": "Sélection multiple de filaires - choisissez un type de résultat et cliquez sur Appliquer.",
    "multi_select_count": "{count} éléments sélectionnés",
    "multi_select_add_hint": "Ctrl+clic pour ajouter/retirer de la sélection",
    "takeoff": "Métré",
    "results": "Résultats",
    "clear": "Effacer",
    "tooltip_clear_log": "Effacer le journal",
    "takeoff_empty": "Chargez un modèle pour afficher le métré.",
    "analysis_results_empty": "Sélectionnez un appui ponctuel, linéaire ou surfacique pour afficher ses résultats.",
    "analysis_results_help": "Choisissez un type de résultat, une valeur, puis cliquez sur Appliquer pour afficher le diagramme dans la vue 3D.",
    "analysis_results_apply": "Appliquer",
    "analysis_results_scale": "Échelle du diagramme",
    "analysis_results_status_available": "Résultats disponibles",
    "analysis_results_status_unavailable": "Aucun résultat disponible",
    "analysis_results_case_placeholder": "Aucun cas / combinaison",
    "analysis_results_type_placeholder": "Type de résultat",
    "analysis_results_value_placeholder": "Valeur",
    "analysis_results_none_for_selection": "Aucun résultat disponible pour cette sélection.",
    "takeoff_linear_section": "Métré filaire par section",
    "takeoff_linear_material": "Métré filaire par matériau",
    "takeoff_planar_thickness": "Métré surfacique par épaisseur",
    "takeoff_planar_material": "Métré surfacique par matériau",
    "takeoff_load_area": "Métré paroi",
    "takeoff_empty_linear": "Aucune poutre.",
    "takeoff_empty_planar": "Aucun élément surfacique.",
    "takeoff_empty_load_area": "Aucune paroi.",
    "takeoff_total_area": "Aire totale",
    "prop_material": "Matériau",
    "prop_section": "Section",
    "prop_orientation": "Orientation",
    "prop_relaxation_elastic": "Relaxations élastiques",
    "prop_relaxation_elastic_present": "Des relaxations élastiques sont présentes",
    "prop_blocking": "Blocage",
    "prop_stiffness": "Raideur",
    "prop_operation": "Fonctionnement",
    "prop_relaxation_end_1": "Relaxation Extrémité 1",
    "prop_relaxation_end_2": "Relaxation Extrémité 2",
    "prop_no_linear": "Aucune propriété disponible pour cet élément filaire.",
    "prop_no_planar": "Aucune propriété disponible pour cet élément surfacique.",
    "prop_no_load_area": "Aucune propriété disponible pour cette paroi.",
    "prop_load_area": "Paroi",
    "prop_load_area_type": "Type",
    "prop_load_area_transfer_method": "Méthode de transfert",
    "prop_load_area_span_direction": "Sens de portée",
    "prop_load_area_rigid_diafragm": "Membrane rigide",
    "prop_load_area_self_weight": "Poids propre",
    "prop_load_area_snow": "Neige",
    "prop_load_area_wind": "Vent",
    "prop_load_area_climatic_building": "Bâtiment",
    "prop_load_area_climatic_protruding_roof": "Avancée de toiture",
    "prop_load_area_climatic_parapet": "Acrotère",
    "prop_load_area_climatic_isolated_1_sloped": "Toiture isolée 1 versant",
    "prop_load_area_climatic_isolated_2_sloped": "Toiture isolée 2 versants",
    "prop_load_area_climatic_panel": "Panneau de signalisation",
    "prop_load_area_climatic_scaffolding": "Structure en treillis ou échafaudage",
    "prop_load_area_climatic_shed_vertical": "Toiture verticale (sheds)",
    "prop_load_area_climatic_awning": "Auvent",
    "prop_load_area_climatic_vaulted": "Toitures en voûtes",
    "prop_load_area_climatic_inclined_wall": "Paroi inclinée 45°–75°",
    "prop_load_area_climatic_free_standing_wall": "Mur isolé",
    "prop_load_area_transfer_failure_lines": "Lignes de rupture",
    "prop_load_area_transfer_fem": "Méthode MEF",
    "prop_load_area_transfer_auto": "Auto",
    "prop_load_area_span_x": "x",
    "prop_load_area_span_y": "y",
    "prop_load_area_span_xy": "xy",
    "prop_linear_element": "Élément filaire",
    "prop_planar_element": "Élément surfacique",
    "prop_punctual_support": "Appui ponctuel",
    "prop_material_na": "Matériau",
    "prop_section_na": "Section",
    "prop_thickness": "Épaisseur",
    "prop_slope_x": "Pente X",
    "prop_slope_y": "Pente Y",
    "prop_vertices": "Nb de sommets",
    "prop_eccentricity": "Excentricité",
    "prop_eccentricity_fem": "Ex. prise en compte (calcul)",
    "prop_mesh_section": "Maillage",
    "prop_mesh_automatic": "Automatique",
    "prop_mesh_type": "Type",
    "prop_mesh_density": "Densité",
    "prop_mesh_type_complete": "Complet",
    "prop_mesh_type_triangulation": "Triangulation",
    "prop_mesh_type_none": "Aucun (nœuds aux sommets)",
    "prop_mesh_density_global": "Global",
    "prop_mesh_density_simplified": "Simplifié",
    "prop_mesh_density_detailed": "Détaillé",
    "prop_mesh_density_element_size": "Taille d'élément fixe",
    "prop_not_supported": "Non pris en charge",
    "prop_support_punctual_unsupported": "Appui ponctuel non pris en charge",
    "prop_support_punctual_advanced": "Appui ponctuel avancé",
    "prop_support_punctual_rigid": "Appui ponctuel rigide",
    "prop_support_punctual_elastic": "Appui ponctuel élastique",
    "prop_support_punctual_stop": "Butée ponctuelle",
    "prop_support_linear_unsupported": "Appui linéaire non pris en charge",
    "prop_support_linear_advanced": "Appui linéaire avancé",
    "prop_support_linear_rigid": "Appui linéaire rigide",
    "prop_support_linear_elastic": "Appui linéaire élastique",
    "prop_support_linear_stop": "Butée linéaire",
    "prop_support_planar_unsupported": "Appui surfacique non pris en charge",
    "prop_support_planar_advanced": "Appui surfacique avancé",
    "prop_support_planar_rigid": "Appui surfacique rigide",
    "prop_support_planar_elastic": "Appui surfacique élastique",
    "prop_support_planar_stop": "Butée surfacique",
    "prop_torsor_top": "Torseur en tête de voile",
    "prop_torsor_left": "Torseur à gauche",
    "prop_torsor_right": "Torseur à droite",
    "prop_torsor_bottom": "Torseur en bas de voile",
    "prop_wall_height": "Hauteur du voile",
    "prop_wall_width": "Largeur du voile",
    "prop_cg_coordinates": "Coordonnées du centre de gravité",
    "analysis_result_displacements": "Déplacements",
    "analysis_result_forces": "Efforts",
    "analysis_result_stresses": "Contraintes",
    "analysis_results_apply_support_help": "Choisissez un cas ou une combinaison puis cliquez sur Appliquer.",
    "analysis_results_linear_diagram_shown": "Diagramme affiché dans la vue 3D : {title} ({points} points, amplitude absolue max = {max_abs}{suffix}).",
    "analysis_results_diagram_fill_colored": "Remplissage coloré (style Advance Design)",
    "analysis_results_diagram_envelope_label": "Enveloppe du diagramme",
    "analysis_results_diagram_baseline_label": "Axe de l'élément",
    "analysis_results_diagram_stems_label": "Tiges colorées par valeur",
    "analysis_results_diagram_label_unit_cm": "cm",
    "analysis_results_diagram_label_unit_kn": "kN",
    "analysis_results_diagram_label_unit_knm": "kN.m",
    "analysis_results_diagram_label_unit_mpa": "MPa",
    "analysis_results_select_supported_element_and_case": "Sélectionnez un élément compatible ainsi qu'un cas ou une combinaison.",
    "analysis_results_invalid_type": "Choisissez un type de résultat valide.",
    "analysis_results_invalid_linear_value": "Choisissez une valeur valide pour l'élément filaire.",
    "analysis_results_loading": "Chargement des résultats en cours...",
    "analysis_results_select_element": "Sélectionnez un élément filaire, un appui ou un élément surfacique pour afficher ses résultats.",
    "analysis_results_export": "Exporter",
    "analysis_results_export_confirm_title": "Confirmation d'écrasement",
    "analysis_results_export_confirm_overwrite": "Le fichier Excel pour cet élément existe déjà, voulez-vous l'écraser ?",
    "analysis_results_export_success": "Résultats exportés : {path}",
    "analysis_results_export_workbook_success": "Résultats exportés dans le classeur Excel : {path}",
    "analysis_results_export_sheet_displacements": "Déplacements",
    "analysis_results_export_sheet_forces": "Efforts",
    "analysis_results_export_sheet_stresses": "Contraintes",
    "analysis_results_export_not_available": "Export impossible pour la sélection courante.",
    "analysis_results_export_no_data": "Aucune donnée de résultat à exporter pour cet élément.",
    "loads_panel_title": "Charges",
    "loads_general_title": "Général",
    "loads_punctual_title": "Charges ponctuelles",
    "loads_punctual_scale": "Echelle (m/kN_max)",
    "loads_load_case_filter": "Cas de charge",
    "loads_load_case_all": "Tous",
    "loads_punctual_count": "{count} charge(s) ponctuelle(s)",
    "loads_punctual_empty": "Aucune charge ponctuelle dans le modèle.",
    "loads_punctual_no_case": "Aucun cas de charge disponible.",
    "loads_punctual_fx": "Fx",
    "loads_punctual_fy": "Fy",
    "loads_punctual_fz": "Fz",
    "loads_linear_title": "Charges linéaires",
    "loads_linear_scale": "Echelle (m/kN_max)",
    "loads_linear_count": "{count} charge(s) linéaire(s)",
    "loads_linear_empty": "Aucune charge linéaire dans le modèle.",

    "loads_planar_title": "Charges surfaciques",
    "loads_planar_scale": "Echelle (m/kN_max)",
    "loads_planar_count": "{count} charge(s) surfacique(s)",
    "loads_planar_empty": "Aucune charge surfacique dans le modèle.",

    "prop_punctual_load": "Charge ponctuelle",
    "prop_punctual_load_fx": "Fx",
    "prop_punctual_load_fy": "Fy",
    "prop_punctual_load_fz": "Fz",
    "prop_punctual_load_f":  "F résultante",
    "prop_punctual_load_mx": "Mx",
    "prop_punctual_load_my": "My",
    "prop_punctual_load_mz": "Mz",
    "prop_punctual_load_case": "Cas de charge",
    "prop_punctual_load_unit_kn":  "kN",
    "prop_punctual_load_unit_knm": "kN·m",
    "prop_no_punctual_load": "Aucune propriété disponible pour cette charge.",

    "prop_linear_load": "Charge linéaire",
    "prop_linear_load_fx": "Fx",
    "prop_linear_load_fy": "Fy",
    "prop_linear_load_fz": "Fz",
    "prop_linear_load_f":  "F résultante",
    "prop_linear_load_mx": "Mx",
    "prop_linear_load_my": "My",
    "prop_linear_load_mz": "Mz",
    "prop_linear_load_coeff1": "Coefficient 1",
    "prop_linear_load_coeff2": "Coefficient 2",
    "prop_linear_load_unit_knm": "kN/m",
    "prop_linear_load_unit_knm2": "kN.m/m",
    "prop_no_linear_load": "Aucune propriété disponible pour cette charge linéaire.",

    "prop_planar_load": "Charge surfacique",
    "prop_planar_load_fx": "Fx",
    "prop_planar_load_fy": "Fy",
    "prop_planar_load_fz": "Fz",
    "prop_planar_load_coeff1": "Coefficient 1",
    "prop_planar_load_coeff2": "Coefficient 2",
    "prop_planar_load_coeff3": "Coefficient 3",
    "prop_planar_load_unit_knm2": "kN/m2",
    "prop_no_planar_load": "Aucune propriété disponible pour cette charge surfacique.",
    "show_linear_loads": "Afficher charges linéaires",
    "show_planar_loads": "Afficher charges surfaciques",

    "filter_select_all": "Sélectionner tout",
    "filter_select_none": "Désélectionner tout",
    "filter_by_section": "Par section",
    "filter_by_thickness": "Par épaisseur",
    "filter_by_materials": "Par matériaux",
    "tooltip_view_front_back": "Vue de face/derrière (Alt+&)",
    "tooltip_view_left_right": "Vue de gauche/droite (Alt+é)",
    'tooltip_view_top_bottom': 'Vue de dessus/dessous (Alt+")',
    "tooltip_view_iso": "Vue isométrique (Alt+')",
    "tooltip_filter": "Filtre",
    "tooltip_clear_filter": "Annuler le filtre",
    "tooltip_isolate": "Isoler la sélection",
    "tooltip_isolation_active": "Isolation active",
    "progress_open_project": "Ouverture du projet...",
    "progress_read_ids": "Lecture des identifiants...",
    "progress_read_objects": "Lecture des objets filaires et surfaciques...",
    "progress_resolve_refs": "Résolution des matériaux et sections des filaires...",
    "progress_read_cases": "Lecture des cas et combinaisons...",
    "progress_check_results": "Vérification des résultats de calcul...",
    "progress_convert_geometry": "Conversion des géométries...",
    "progress_read_punctual_loads": "Lecture des charges ponctuelles...",
    "progress_read_linear_loads": "Lecture des charges linéaires...",
    "progress_read_planar_loads": "Lecture des charges surfaciques...",
    "progress_build_punctual_loads": "Construction charges ponctuelles...",
    "progress_build_linear_loads": "Construction charges linéaires...",
    "progress_build_planar_loads": "Construction charges surfaciques...",
    "progress_apply_loads": "Application des charges...",
    "progress_prepare_results": "Préparation des résultats...",
    "progress_close_project": "Fermeture du projet...",

    "settings": "Paramètres",
    "settings_title": "Paramètres",
    "menu_view3d": "Vue 3D",
    "view_projection_perspective": "Perspective",
    "view_projection_orthogonal": "Orthogonale",
    "settings_label_linear": "Filaire",
    "settings_label_planar": "Surfacique",
    "settings_label_opening": "Ouverture",
    "settings_label_load_area": "Paroi",
    "settings_label_support_punctual": "Appui ponctuel",
    "settings_label_support_linear": "Appui linéaire",
    "settings_label_support_planar": "Appui surfacique",
    "settings_label_mesh": "Maillage FEM",
    "settings_label_punctual_load_arrows": "Charges ponctuelles",
    "settings_label_linear_load_arrows": "Charges linéaires",
    "settings_label_planar_load_arrows": "Charges surfaciques",
    "settings_label_thickness": "Épaisseur",
    "settings_label_size": "Taille",
    "settings_linear": "Épaisseur filaires",
    "settings_planar": "Épaisseur surfaciques",
    "settings_opening": "Épaisseur ouvertures",
    "settings_load_area": "Épaisseur parois",
    "settings_support_punctual_size": "Taille appuis ponctuels",
    "settings_support_punctual_width": "Épaisseur appuis ponctuels",
    "settings_support_linear": "Épaisseur appuis linéaires",
    "settings_support_planar": "Épaisseur appuis surfaciques",
    "settings_color_linear": "Couleur filaires",
    "settings_color_planar": "Couleur surfaciques",
    "settings_color_opening": "Couleur ouvertures",
    "settings_color_load_area": "Couleur parois",
    "settings_color_support_punctual": "Couleur appuis ponctuels",
    "settings_color_support_linear": "Couleur appuis linéaires",
    "settings_color_support_planar": "Couleur appuis surfaciques",
    "settings_selection": "Sélection",
    "choose_color": "Choisir...",

    "menu_file": "Fichier",
    "menu_open": "Ouvrir",
    "menu_export_ifc": "Export IFC",
    "menu_about": "À propos",
    "menu_fit": "Recentrer",
    "menu_iso": "Vue isométrique",
    "menu_quit": "Quitter",
    "menu_settings": "Paramètres",
    "menu_styles": "Styles et épaisseurs...",
    "menu_configuration": "Configuration",
    "menu_api_server": "Exécutable serveur API...",
    "menu_api_url": "URL API...",
    "menu_theme": "Thème",
    "api_server_exe": "Exécutable serveur API",
    "theme": "Thème",
    "theme_dark": "Sombre",
    "theme_light": "Clair",
    "browse_exe_title": "Choisir l'exécutable serveur API",
    "browse_exe_filter": "Exécutable (*.exe);;Tous les fichiers (*)",
    "api_url_dialog_title": "URL API",
    "api_url_dialog_label": "URL du serveur API",
    "api_url_dialog_placeholder": "http://localhost:52000",
    "api_url_saved": "URL API enregistrée : {url}",

    "browse_title": "Choisir un projet Advance Design",
    "browse_filter": "Advance Design (*.fto);;Tous les fichiers (*)",
    "export_ifc_title": "Exporter en IFC",
    "export_ifc_filter": "IFC (*.ifc);;Tous les fichiers (*)",
    "export_ifc_no_project": "Aucun projet disponible pour l'export IFC.",
    "export_ifc_module_missing": "Le module externe ad_ifc_exporter.py est introuvable.",
    "export_ifc_success": "Export IFC terminé : {path}",
    "export_ifc_running": "Export IFC en cours...",
    "export_ifc_failed": "Échec de l'export IFC : {details}",

    "help_controls": "Contrôles 🛈",
    "help_controls_tooltip": (
        "Molette = zoom, clic gauche = orbite contrainte Z, "
        "clic droit = cycle de sélection, clic milieu = panoramique, "
        "F ou double-clic milieu = zoom étendu, Ctrl+I = vue isométrique."
    ),

    # Libellés génériques d'éléments et de propriétés
    "app_title": "Advance Design Model Viewer",
    "label_element_linear": "Élément filaire",
    "label_element_planar": "Élément surfacique",
    "label_element_generic": "Élément",
    "label_no_release": "Aucune",
    "label_tc_traction": "Traction",
    "label_tc_compression": "Compression",
    "label_section_stiffness": "Raideur",
    "label_section_blocking": "Blocage",
    "color_by_section_on": "Couleur par section activée",
    "color_by_section_off": "Couleur par section désactivée",
}

MSG_LOG = {
    "ready": "Prêt. Sélectionnez un fichier .fto puis chargez le modèle.",
    "selected_file": "Fichier sélectionné : {path}",
    "api_connection": "Connexion API : {host}",
    "api_url_loaded": "URL API chargée : {url}",

    "checking_api": "Vérification de l'API...",
    "api_ok": "API accessible.",
    "normalized_path": "Chemin : {path}",
    "opening_project_reading": "Ouverture du projet et lecture des éléments...",
    "project_closed_after_read": "Projet fermé.",
    "project_kept_open_for_results": "Projet conservé ouvert pour les résultats.",
    "project_closed_before_new_load": "Projet précédent fermé avant nouveau chargement.",
    "project_closed_on_exit": "Projet fermé à la fermeture du viewer.",
    "project_session_mismatch": "Le projet ouvert ne correspond pas au fichier courant.",

    "ids_linear": "Filaires trouvés : {count}",
    "ids_planar": "Surfaciques trouvés : {count}",
    "ids_load_area": "Parois trouvées : {count}",
    "ids_support_punctual": "Appuis ponctuels trouvés : {count}",
    "ids_punctual_loads": "Charges ponctuelles trouvées : {count}",
    "ids_linear_loads": "Charges linéaires trouvées : {count}",
    "ids_planar_loads": "Charges surfaciques trouvées : {count}",
    "show_punctual_loads_on": "Affichage charges ponctuelles : activé",
    "show_punctual_loads_off": "Affichage charges ponctuelles : désactivé",
    "show_linear_loads_on": "Affichage charges linéaires : activé",
    "show_linear_loads_off": "Affichage charges linéaires : désactivé",
    "show_planar_loads_on": "Affichage charges surfaciques : activé",
    "show_planar_loads_off": "Affichage charges surfaciques : désactivé",
    "ids_support_linear": "Appuis filaires trouvés : {count}",
    "ids_support_planar": "Appuis surfaciques trouvés : {count}",
    "resolved_materials": "Matériaux résolus : {resolved}/{total}.",
    "resolved_linear_sections": "Sections filaires résolues : {resolved}/{total}.",

    "loaded_geometry": (
        "Géométrie chargée : {linear} filaires, {planar} surfaciques, "
        "{load_areas} parois, {openings} ouvertures."
    ),
    "loaded_supports": (
        "Appuis chargés : {punctual} ponctuels, {linear} filaires, {planar} surfaciques."
    ),
    "results_available": "Résultats disponibles",
    "results_unavailable": "Aucun résultat disponible",

    "project_opened": "Projet ouvert : {path}",
    "render_updated": "Rendu mis à jour.",
    "api_server_starting": "Démarrage du serveur API : {path} /console",
    "api_server_started": "Serveur API lancé.",
    "api_server_stopped": "Serveur API arrêté.",
    "api_session_full_reset_before_model_change": "Réinitialisation complète de la session API avant changement de modèle...",
    "api_server_restarting": "Redémarrage de l'API Advance Design...",
    "api_server_restarted": "API Advance Design redémarrée.",
    "ifc_export_started": "Démarrage de l'export IFC : {path}",
    "ifc_export_success": "Export IFC terminé : {path}",
    "ifc_export_failed": "Échec de l'export IFC : {details}",
    "ifc_export_module_version": "Module export IFC : {version}",
    "results_export_write_error": "Impossible d'écrire le fichier Excel : {path}",
    "results_export_no_data": "Aucune donnée de résultat à exporter pour l'élément {eid}.",
    "api_server_stopped_on_exit": "Serveur API arrêté à la fermeture du viewer.",
    "display_counts": (
        "Affichage : {linear} filaires, {planar} surfaciques, "
        "{load_areas} parois, {openings} ouvertures."
    ),
    "support_counts": (
        "Appuis : {punctual} ponctuels, {linear} linéaires, {planar} surfaciques."
    ),

    "show_lines_on": "Affichage filaires : activé",
    "show_lines_off": "Affichage filaires : désactivé",
    "show_planars_on": "Affichage surfaciques : activé",
    "show_planars_off": "Affichage surfaciques : désactivé",
    "show_load_areas_on": "Affichage parois : activé",
    "show_load_areas_off": "Affichage parois : désactivé",
    "show_support_punctual_on": "Affichage appuis ponctuels : activé",
    "show_support_punctual_off": "Affichage appuis ponctuels : désactivé",
    "show_support_linear_on": "Affichage appuis linéaires : activé",
    "show_support_linear_off": "Affichage appuis linéaires : désactivé",
    "show_support_planar_on": "Affichage appuis surfaciques : activé",
    "show_support_planar_off": "Affichage appuis surfaciques : désactivé",
    "show_marker_on": "Affichage repère : activé",
    "show_marker_off": "Affichage repère : désactivé",
    "show_mesh_on": "Affichage maillage FEM : activé",
    "show_mesh_off": "Affichage maillage FEM : désactivé",

    "mode_wireframe": "Mode de visualisation : filaire",
    "mode_hidden_faces": "Mode de visualisation : faces cachées",
    "mode_wire_hidden": "Mode de visualisation : filaire + faces cachées",
    "mode_full": "Mode de visualisation : rendu plein",

    "settings_applied": (
        "Paramètres appliqués : "
        "filaires={linear:.1f}, surfaciques={planar:.1f}, ouvertures={openings:.1f}, "
        "parois={load_areas:.1f}, taille appuis ponctuels={support_size:.2f}, "
        "appuis ponctuels={support_punctual:.1f}, appuis linéaires={support_linear:.1f}, "
        "appuis surfaciques={support_planar:.1f}"
    ),
    "progress_read_fem_mesh": "Lecture du maillage FEM...",
    "progress_finalizing": "Finalisation...",
    "progress_load_done": "Chargement terminé.",
}

MSG_ERR = {
    "no_file_selected": "Aucun fichier .fto sélectionné.",
    "file_not_found": "Fichier introuvable : {path}",
    "path_not_file": "Le chemin ne désigne pas un fichier : {path}",

    "invalid_api_url": "URL API invalide : {host}",
    "api_unreachable": (
        "API non joignable sur {hostname}:{port}. "
        "Vérifiez qu'Advance Design et l'API sont démarrés."
    ),
    "api_contact_failed": "Impossible de contacter l'API Advance Design ({host}).",

    "http_error": "{label} HTTP {status}: {body}",
    "api_failure": "{label} échec API : {details}",
    "project_already_open": (
        "Le fichier est déjà ouvert dans Advance Design ou verrouillé par un autre processus. {details}"
    ),

    "api_no_response": "L'API Advance Design ne répond pas.",
    "api_check_advice": "Vérifiez que l'API est lancée.",
    "file_already_open_short": "Le fichier est déjà ouvert dans Advance Design.",
    "load_error": "Erreur lors du chargement du modèle :",
    "api_server_exe_not_found": "Exécutable serveur API introuvable : {path}",
    "api_server_start_failed": "Impossible de démarrer l'API : {details}",
    "api_engine_not_initialized": "Erreur d'initialisation : Quittez le viewer et lancez Advance Design pour initialiser le moteur API.",
    "error_session_invalid": "Session projet invalide pour la lecture des résultats.",
}


def tr_ui(key: str, **kwargs) -> str:
    text = MSG_UI.get(key, key)
    return text.format(**kwargs) if kwargs else text


def tr_log(key: str, **kwargs) -> str:
    text = MSG_LOG.get(key, key)
    return text.format(**kwargs) if kwargs else text


def tr_err(key: str, **kwargs) -> str:
    text = MSG_ERR.get(key, key)
    return text.format(**kwargs) if kwargs else text


# ======================================================================
#  Exceptions personnalisées
# ======================================================================

class ApiUnavailableError(RuntimeError):
    pass


class ProjectAlreadyOpenError(RuntimeError):
    pass
