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

APP_VERSION = "2.05"
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

# Échelle du rendu pour l'export PNG de la vue graphique (entier 1..3).
DEFAULT_PNG_EXPORT_SCALE = 1
PNG_EXPORT_SCALE_MIN = 1
PNG_EXPORT_SCALE_MAX = 3

# Mode d'export PNG : "multiplier" (échelle de la fenêtre courante) ou une
# résolution standard fixe en pixels.
DEFAULT_PNG_EXPORT_MODE = "multiplier"
PNG_EXPORT_RESOLUTIONS = {
    "hd": (1280, 720),
    "fhd": (1920, 1080),
    "qhd": (2560, 1440),
    "4k": (3840, 2160),
}

# Calcul éléments finis : délai maximum en secondes avant abandon (0 = illimité).
DEFAULT_CALC_EF_TIMEOUT = 7200
CALC_EF_TIMEOUT_MAX = 86400


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
INITIAL_PROFILES_TRANSPARENCY_PERCENT = 65  # slider "Transparence profilés" (mode Profilés + Faces cachées)

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

from lang import lang_fr

MSG_UI = lang_fr.MSG_UI
MSG_LOG = lang_fr.MSG_LOG
MSG_ERR = lang_fr.MSG_ERR


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
