# -*- coding: utf-8 -*-
"""
viewer_widget.py
Widget VTK 3D : interactor style contraint, rendu des éléments structuraux,
sélection/picking, filtres, isolation et diagrammes de résultats.

Dépend de :
  - viewer_config (constantes, couleurs de thème)
"""

import os
import math
import time
import hashlib
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkRenderingCore import vtkBillboardTextActor3D
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QVBoxLayout

import viewer_config as _cfg
import display_units as du
import scene_light as _scene_light
import flight_navigation as _flight_nav
import minimap as _minimap
import clip_box as _clip_box
import model_check_view as _mcv
from viewer_config import (
    LINEAR_LOAD_COLOR, LINEAR_LOAD_SCALE, LINEAR_LOAD_LINE_WIDTH,
    PLANAR_LOAD_COLOR, PLANAR_LOAD_SCALE, PLANAR_LOAD_LINE_WIDTH,
    PUNCTUAL_LOAD_LINE_WIDTH, AUTO_LOAD_SCALE_RATIO,
    BG, PANEL, BORDER, ACCENT, ACCENT2, WARN, ERROR_COL,
    FG, FG_DIM, VTK_BG,
    LINEAR_LINE_WIDTH, PLANAR_LINE_WIDTH, OPENING_LINE_WIDTH, LOAD_AREA_LINE_WIDTH,
    SUPPORT_PUNCTUAL_SIZE, SUPPORT_PUNCTUAL_LINE_WIDTH,
    SUPPORT_LINEAR_LINE_WIDTH, SUPPORT_PLANAR_LINE_WIDTH,
    INITIAL_TRANSPARENCY_PERCENT,
    INITIAL_PROFILES_TRANSPARENCY_PERCENT,
    DEFAULT_VIEW_PROJECTION,
    MESH_LINE_WIDTH,
    MESH_COLOR,
    PUNCTUAL_LOAD_COLOR,
    PUNCTUAL_LOAD_SCALE,
    _DARK_VTK_BG,
)

from ad_model_data import _build_ad_local_axes, _cross_vector3, _normalize_vector3, _rotate_vector_around_axis
from section_geometry import profile_polygon, rotate_poly2, translate_polygon2
from load_lines import LoadLines, TIP_RATIO, resultant as _resultant

_PROFILE_MODES = ("profiles_hidden", "profiles_full", "profiles_wire")
_WIRE3D_COLOR = (0.25, 0.25, 0.25)
_WIRE3D_FACE_OPACITY = 0.01  # > 0 : vtkCellPicker ignore les acteurs d'opacite nulle
_ALL_DISPLAY_MODES = ("wireframe", "hidden_faces", "wire_hidden", "full") + _PROFILE_MODES


def _poly2_area(loop):
    """Aire (valeur absolue) d'un polygone 2D ferme implicitement."""
    a = 0.0
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def _seg_intersects_rect(ax, ay, bx, by, xmin, ymin, xmax, ymax):
    """Liang-Barsky : True si le segment [a,b] touche le rectangle axis-aligned
    (contact ou recouvrement, segment entierement interieur inclus)."""
    dx = bx - ax
    dy = by - ay
    p = (-dx, dx, -dy, dy)
    q = (ax - xmin, xmax - ax, ay - ymin, ymax - ay)
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0.0:
            if qi < 0.0:
                return False
        else:
            t = qi / pi
            if pi < 0.0:
                if t > u2:
                    return False
                if t > u1:
                    u1 = t
            else:
                if t < u1:
                    return False
                if t < u2:
                    u2 = t
    return u1 <= u2


def _invert_selection_items(selected_items, universe_keys):
    current = {(it["role"], int(it["index"])) for it in selected_items}
    return [{"role": role, "index": index} for (role, index) in sorted(set(universe_keys) - current)]


class ConstrainedOrbitStyle(vtk.vtkInteractorStyleUser):
    def __init__(self, parent=None):
        super().__init__()
        self._mode = None
        self._last_pos = (0, 0)
        self._azimuth_speed = 0.35
        self._elevation_speed = 0.25
        self._zoom_factor = 1.12
        self._min_elev_deg = -85.0
        self._max_elev_deg = 85.0
        self._middle_double_click_interval = 0.35
        self._middle_double_click_tolerance = 6
        self._last_middle_press_time = 0.0
        self._last_middle_press_pos = None

        self.AddObserver("LeftButtonPressEvent", self._on_left_press)
        self.AddObserver("LeftButtonReleaseEvent", self._on_left_release)
        self.AddObserver("MiddleButtonPressEvent", self._on_middle_press)
        self.AddObserver("MiddleButtonReleaseEvent", self._on_middle_release)
        self.AddObserver("MouseMoveEvent", self._on_mouse_move)
        self.AddObserver("MouseWheelForwardEvent", self._on_wheel_forward)
        self.AddObserver("MouseWheelBackwardEvent", self._on_wheel_backward)

    def _interactor(self):
        return self.GetInteractor()

    def _update_renderer_from_event(self):
        interactor = self._interactor()
        if not interactor:
            return None
        x, y = interactor.GetEventPosition()
        renderer = self.FindPokedRenderer(x, y)
        if renderer:
            self.SetCurrentRenderer(renderer)
            return renderer
        return self.GetCurrentRenderer()

    def _renderer(self):
        renderer = self.GetCurrentRenderer()
        if renderer:
            return renderer
        return self._update_renderer_from_event()

    def _display_to_world(self, renderer, x, y, z):
        renderer.SetDisplayPoint(float(x), float(y), float(z))
        renderer.DisplayToWorld()
        world = renderer.GetWorldPoint()
        if not world or abs(world[3]) < 1e-12:
            return None
        return (world[0] / world[3], world[1] / world[3], world[2] / world[3])

    def _orbit(self, dx, dy):
        renderer = self._renderer()
        if not renderer:
            return

        camera = renderer.GetActiveCamera()
        fx, fy, fz = camera.GetFocalPoint()
        px, py, pz = camera.GetPosition()

        vx = px - fx
        vy = py - fy
        vz = pz - fz

        radius = math.sqrt(vx * vx + vy * vy + vz * vz)
        if radius < 1e-9:
            radius = 1.0

        azimuth = math.atan2(vy, vx)
        horiz = math.sqrt(vx * vx + vy * vy)
        elevation = math.atan2(vz, horiz)

        azimuth += math.radians(-dx * self._azimuth_speed)
        elevation += math.radians(-dy * self._elevation_speed)

        min_e = math.radians(self._min_elev_deg)
        max_e = math.radians(self._max_elev_deg)
        elevation = max(min(elevation, max_e), min_e)

        cos_e = math.cos(elevation)
        new_x = fx + radius * cos_e * math.cos(azimuth)
        new_y = fy + radius * cos_e * math.sin(azimuth)
        new_z = fz + radius * math.sin(elevation)

        camera.SetPosition(new_x, new_y, new_z)
        camera.SetFocalPoint(fx, fy, fz)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.OrthogonalizeViewUp()

        renderer.ResetCameraClippingRange()
        self._interactor().Render()

    def _pan(self, x, y, last_x, last_y):
        renderer = self._renderer()
        if not renderer:
            return

        camera = renderer.GetActiveCamera()
        fx, fy, fz = camera.GetFocalPoint()
        px, py, pz = camera.GetPosition()

        renderer.SetWorldPoint(fx, fy, fz, 1.0)
        renderer.WorldToDisplay()
        focal_display = renderer.GetDisplayPoint()
        focal_depth = focal_display[2]

        old_world = self._display_to_world(renderer, last_x, last_y, focal_depth)
        new_world = self._display_to_world(renderer, x, y, focal_depth)
        if old_world is None or new_world is None:
            return

        motion = (
            old_world[0] - new_world[0],
            old_world[1] - new_world[1],
            old_world[2] - new_world[2],
        )

        view_up = camera.GetViewUp()
        camera.SetFocalPoint(fx + motion[0], fy + motion[1], fz + motion[2])
        camera.SetPosition(px + motion[0], py + motion[1], pz + motion[2])
        if view_up is not None and len(view_up) >= 3:
            camera.SetViewUp(float(view_up[0]), float(view_up[1]), float(view_up[2]))
        camera.OrthogonalizeViewUp()

        renderer.ResetCameraClippingRange()
        self._interactor().Render()

    def _zoom(self, factor):
        renderer = self._renderer()
        if not renderer:
            return

        camera = renderer.GetActiveCamera()
        if camera.GetParallelProjection():
            camera.Zoom(factor)
        else:
            camera.Dolly(factor)

        renderer.ResetCameraClippingRange()
        self._interactor().Render()

    def _fit_current_renderer(self):
        renderer = self._renderer()
        if not renderer:
            return

        camera = renderer.GetActiveCamera()
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.OrthogonalizeViewUp()
        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        self._interactor().Render()

    def _on_left_press(self, obj, event):
        renderer = self._update_renderer_from_event()
        if not renderer:
            return
        self._mode = "orbit"
        self._last_pos = self._interactor().GetEventPosition()

    def _on_left_release(self, obj, event):
        self._mode = None

    def _on_middle_press(self, obj, event):
        renderer = self._update_renderer_from_event()
        if not renderer:
            return

        interactor = self._interactor()
        pos = interactor.GetEventPosition()
        now = time.monotonic()

        is_double_click = False
        if self._last_middle_press_pos is not None:
            dt = now - self._last_middle_press_time
            dx = pos[0] - self._last_middle_press_pos[0]
            dy = pos[1] - self._last_middle_press_pos[1]
            if (
                dt <= self._middle_double_click_interval
                and abs(dx) <= self._middle_double_click_tolerance
                and abs(dy) <= self._middle_double_click_tolerance
            ):
                is_double_click = True

        self._last_middle_press_time = now
        self._last_middle_press_pos = pos

        if is_double_click:
            self._mode = None
            self._fit_current_renderer()
            self._last_middle_press_time = 0.0
            self._last_middle_press_pos = None
            return

        self._mode = "pan"
        self._last_pos = pos

    def _on_middle_release(self, obj, event):
        self._mode = None

    def _on_mouse_move(self, obj, event):
        if not self._mode:
            return

        interactor = self._interactor()
        x, y = interactor.GetEventPosition()
        last_x, last_y = self._last_pos
        dx = x - last_x
        dy = y - last_y

        if self._mode == "orbit":
            self._orbit(dx, dy)
        elif self._mode == "pan":
            self._pan(x, y, last_x, last_y)

        self._last_pos = (x, y)

    def _on_wheel_forward(self, obj, event):
        self._update_renderer_from_event()
        self._zoom(self._zoom_factor)

    def _on_wheel_backward(self, obj, event):
        self._update_renderer_from_event()
        self._zoom(1.0 / self._zoom_factor)


class VTKViewerWidget(QFrame):
    # Émet la liste complète des items sélectionnés : [{"role": str, "index": int}, ...]
    # Liste vide = aucune sélection.
    selectionChanged = Signal(list)
    # Emis quand le mode "selection par fenetre" est active/desactive.
    windowSelectModeChanged = Signal(bool)
    # Emis a la fin d'une selection par fenetre : liste finale [{"role","index"}, ...].
    windowSelectionDone = Signal(list)
    # Emis quand le mode "zoom fenetre" est active/desactive.
    zoomWindowModeChanged = Signal(bool)
    # Emis quand le mode "Navigation" (camera libre) est active/desactive.
    flightModeChanged = Signal(bool)
    clipBoxChanged = Signal(bool)
    contextMenuRequested = Signal()
    ELEMENT_INDEX_ARRAY = "element_index"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Construits avant tout le reste : apply_theme() (ci-dessous) declenche
        # _apply_view_overlay_theme(), qui accede deja a _flight et _minimap
        # (cf. bug corrige lors du refactor Navigation - l'ordre compte).
        self._flight = _flight_nav.FlightController(self)
        self._minimap = _minimap.MinimapController(self)
        self._clip = _clip_box.ClipBoxController(self)
        self._clip.on_box_changed = lambda box: self._minimap.set_clip_footprint(box, self._clip.box_color)
        self.apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.vtk_widget = QVTKRenderWindowInteractor(self)
        layout.addWidget(self.vtk_widget)

        self.renderer = vtk.vtkRenderer()
        self._anomaly_overlay = _mcv.AnomalyOverlay(self.renderer)
        self._active_anomaly = None
        self._anomaly_emit = False
        self.renderer.SetBackground(*_cfg.VTK_BG)

        self.render_window = self.vtk_widget.GetRenderWindow()
        self.render_window.AddRenderer(self.renderer)

        self.interactor = self.render_window.GetInteractor()
        self.interactor_style = ConstrainedOrbitStyle()
        self.interactor_style.SetDefaultRenderer(self.renderer)
        self.interactor.SetInteractorStyle(self.interactor_style)

        self._actors = []
        self._pickable_actors = {}
        self._selection_overlay_actors = []
        self._diagram_overlay_actors = []
        self._diagram_label_actors = []
        self._selected_item = None       # compatibilité (premier item ou None)
        self._selected_items = []        # liste complète : [{"role": str, "index": int}, ...]
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1
        self._model_data = {
            "lines": [],
            "planars": [],
            "load_areas": [],
            "punctual_supports": [],
            "linear_supports": [],
            "planar_supports": [],
        }

        self._lines_actor = None
        self._profiles_actor = None
        self._profiles_base_pd = None
        self._profiles_base_colors = None
        self._planar_actor = None
        self._planar_faces_actor = None
        self._planar_edges_actor = None
        self._openings_actor = None
        self._load_areas_actor = None
        self._load_areas_faces_actor = None
        self._support_punctual_actor = None
        self._support_linear_actor = None
        self._support_planar_actor = None
        self._support_planar_faces_actor = None
        self._support_planar_centroid_actor = None
        self._mesh_actor = None
        self._mesh_nodes: list = []
        self._mesh_by_eid: dict = {}

        # Charges ponctuelles
        self._punctual_load_actors: list = []   # liste d'acteurs (un groupe par charge)
        self._punctual_load_data: list = []     # liste des dicts bruts (pos, fx, fy, fz, ...)
        self._punctual_load_case_filter: int | None = None  # EID du cas filtré, ou None = tous
        self._show_punctual_loads = False
        self.punctual_load_scale = float(PUNCTUAL_LOAD_SCALE)
        self.punctual_load_color = tuple(PUNCTUAL_LOAD_COLOR)
        self.punctual_load_line_width = float(PUNCTUAL_LOAD_LINE_WIDTH)
        self.load_auto_scale = True
        self._model_extent = 0.0
        self.punctual_load_count = 0

        self._linear_load_actors: list = []
        self._linear_load_data: list = []
        self._linear_load_case_filter: int | None = None
        self._show_linear_loads = False
        self.linear_load_scale = float(LINEAR_LOAD_SCALE)
        self.linear_load_color = tuple(LINEAR_LOAD_COLOR)
        self.linear_load_line_width = float(LINEAR_LOAD_LINE_WIDTH)
        self.linear_load_count = 0

        self._planar_load_actors: list = []
        self._planar_load_data: list = []
        self._planar_load_case_filter: int | None = None
        self._show_planar_loads = False
        self.planar_load_scale = float(PLANAR_LOAD_SCALE)
        self.planar_load_color = tuple(PLANAR_LOAD_COLOR)
        self.planar_load_line_width = float(PLANAR_LOAD_LINE_WIDTH)
        self.planar_load_count = 0

        self._show_lines = True
        self._show_planars = True
        self._show_load_areas = True
        self._show_support_punctual = True
        self._show_support_linear = True
        self._show_support_planar = True
        self._show_marker = True
        self._show_mesh = False
        self._show_punctual_loads = False
        self._show_linear_loads = False
        self._show_planar_loads = False
        self._color_by_section = False
        self._profiles_wire_applied = False
        self._planar_thickness_enabled = False
        self._section_color_map = {}
        self._display_mode = "wire_hidden"

        self.lines_count = 0
        self.planars_count = 0
        self.load_areas_count = 0
        self.support_punctual_count = 0
        self.support_linear_count = 0
        self.support_planar_count = 0

        self._support_punctual_points = []
        self._support_punctual_indexes = None  # indexes modèle si isolation active, sinon None

        self.linear_line_width = LINEAR_LINE_WIDTH
        self.planar_line_width = PLANAR_LINE_WIDTH
        self.opening_line_width = OPENING_LINE_WIDTH
        self.load_area_line_width = LOAD_AREA_LINE_WIDTH

        self.support_punctual_size = SUPPORT_PUNCTUAL_SIZE
        self.support_punctual_line_width = SUPPORT_PUNCTUAL_LINE_WIDTH
        self.support_linear_line_width = SUPPORT_LINEAR_LINE_WIDTH
        self.support_planar_line_width = SUPPORT_PLANAR_LINE_WIDTH

        self.linear_color = (0.57, 0.72, 1.0)
        self.planar_color = (0.20, 0.75, 0.45)
        self.opening_color = (1.0, 0.55, 0.25)
        self.load_area_color = (0.65, 0.65, 0.72)
        self.support_punctual_color = (1.0, 0.92, 0.20)
        self.support_linear_color = (1.0, 1.0, 0.0)
        self.support_planar_color = (1.0, 0.92, 0.20)
        self.selection_color = (1.0, 0.0, 0.0)
        self.selection_line_width = 3.5
        self.mesh_color = MESH_COLOR
        self.mesh_line_width = MESH_LINE_WIDTH

        self._transparency_percent = INITIAL_TRANSPARENCY_PERCENT
        self._profiles_transparency_percent = INITIAL_PROFILES_TRANSPARENCY_PERCENT
        self.planar_faces_base_opacity = 0.35
        self.load_areas_faces_base_opacity = 0.30
        self.support_planar_faces_base_opacity = 0.35
        self._filter_section_names = None
        self._filter_thickness_names = None
        self._filter_material_names = None
        self._isolated_selection = []   # liste de {"role","index"} — vide = pas d'isolation
        self._hidden_items = set()      # {(role, index)} masques via les cases de l'arbre Systemes
        self._linear_result_scale_factor = 1.0
        self._projection_mode = DEFAULT_VIEW_PROJECTION

        self.orientation_widget = None

        # Overlay coin haut-gauche : vue courante + position 3D de la souris.
        self._has_model = False
        self._view_overlay_actor = None
        self._overlay_mouse_world_txt = "X : --   Y : --   Z : --"

        self.setFocusPolicy(Qt.StrongFocus)
        self.vtk_widget.setFocusPolicy(Qt.StrongFocus)

        self._build_scene_base()
        self.renderer.GetActiveCamera().AddObserver("ModifiedEvent", self._on_camera_orient_labels)
        self.set_projection_mode(self._projection_mode)
        self.set_isometric_view()

        for seq, additive in (("Tab", False), ("Ctrl+Tab", True)):
            sc = QShortcut(QKeySequence(seq), self.vtk_widget)
            sc.setContext(Qt.WidgetShortcut)
            sc.activated.connect(lambda a=additive: self._cycle_selection(a))
        self.interactor.AddObserver("RightButtonPressEvent", self._on_right_button_press, 1.0)
        self.interactor.AddObserver("RightButtonReleaseEvent", self._on_right_button_release, 1.0)
        self._left_press_tag = self.interactor.AddObserver("LeftButtonPressEvent", self._on_left_button_press, 1.0)
        self.interactor.AddObserver("LeftButtonReleaseEvent", self._on_left_button_release, 1.0)
        self.interactor.AddObserver("KeyPressEvent", self._on_key_press, 1.0)
        self.interactor.AddObserver("KeyReleaseEvent", self._on_key_release, 1.0)
        self.interactor.AddObserver("MouseMoveEvent", self._on_window_select_mouse_move, 0.5)
        self.interactor.AddObserver("MouseMoveEvent", self._on_flight_mouse_move, 0.5)
        self.interactor.AddObserver("MouseMoveEvent", self._on_clip_mouse_move, 0.6)
        self._clip_hover_cursor = False
        self.interactor.AddObserver("MouseMoveEvent", self._on_overlay_mouse_move, 0.0)

        # Position du dernier press gauche — pour distinguer clic de glisser
        self._left_press_pos = None
        self._left_press_ctrl = False

        # Mode "selection par fenetre" : clic point 1, deplacement, clic point 2.
        self._window_select_mode = False
        self._plain_style = None
        self._win_pt1 = None
        self._window_rect_actor = None
        self._window_rect_pd = None

        # Mode "zoom fenetre" : meme interaction que la selection par fenetre,
        # mais le 2e clic recadre la camera sur le rectangle trace.
        self._zoom_window_mode = False
        self._zoom_win_pt1 = None

        self.vtk_widget.Initialize()
        self.vtk_widget.Start()

    def apply_theme(self):
        self.setStyleSheet(f"border:1px solid {_cfg.BORDER};")
        if hasattr(self, "_diagram_label_actors"):
            is_dark_theme = tuple(_cfg.VTK_BG) == tuple(_cfg._DARK_VTK_BG)
            label_color = (1.0, 1.0, 1.0) if is_dark_theme else None
            for actor in self._diagram_label_actors:
                if actor is None:
                    continue
                try:
                    text_prop = actor.GetTextProperty()
                except Exception:
                    continue
                if text_prop is None:
                    continue
                if label_color is None:
                    base_color = getattr(actor, '_diagram_original_color', None)
                    if base_color is None:
                        continue
                    text_prop.SetColor(*base_color)
                else:
                    text_prop.SetColor(*label_color)
        self._apply_view_overlay_theme()
        if hasattr(self, "renderer") and self.renderer is not None:
            self.renderer.SetBackground(*_cfg.VTK_BG)
            if hasattr(self, "render_window") and self.render_window is not None:
                self.render_window.Render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_minimap") and self._minimap is not None:
            self._minimap.update_viewport()

    def save_screenshot(self, path: str, scale: int = 1, target_size=None):
        with self._clip.gizmos_hidden():
            self._save_screenshot_impl(path, scale=scale, target_size=target_size)

    def _save_screenshot_impl(self, path: str, scale: int = 1, target_size=None):
        """Enregistre le rendu VTK courant dans un fichier PNG.

        target_size, si fourni (largeur, hauteur), impose une taille de
        sortie exacte en pixels (rendu hors ecran), independamment de la
        taille/du ratio de la fenetre 3D visible. Sinon, `scale` agrandit
        la fenetre visible par un facteur entier (rendu en mosaique).
        """
        if self.render_window is None:
            raise RuntimeError("Fenetre de rendu VTK indisponible.")

        if target_size is not None:
            self._save_screenshot_exact_size(path, target_size)
            return

        try:
            scale = int(scale)
        except (TypeError, ValueError):
            scale = 1
        scale = max(1, scale)

        # Sauvegarde de l'etat camera : le rendu en mosaique (SetScale > 1)
        # modifie la camera et les parametres de tuile de la fenetre, et VTK
        # ne les restaure pas toujours -> vue "zoomee" tant qu'aucun rendu
        # complet n'a eu lieu.
        camera = self.renderer.GetActiveCamera() if self.renderer is not None else None
        cam_backup = None
        if camera is not None:
            cam_backup = vtk.vtkCamera()
            cam_backup.DeepCopy(camera)

        self.render_window.Render()
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(self.render_window)
        if scale > 1:
            w2i.SetScale(scale)
        # RGB (sans canal alpha) : sinon le fond est capture en transparent et
        # l'image apparait sombre/noire dans la plupart des visionneuses.
        w2i.SetInputBufferTypeToRGB()
        w2i.ReadFrontBufferOff()
        w2i.Update()

        writer = vtk.vtkPNGWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(w2i.GetOutputPort())
        try:
            writer.Write()
        finally:
            # Restauration explicite de la fenetre et de la camera.
            self.render_window.SetTileScale(1)
            self.render_window.SetTileViewport(0.0, 0.0, 1.0, 1.0)
            if camera is not None and cam_backup is not None:
                camera.DeepCopy(cam_backup)
                if self.renderer is not None:
                    self.renderer.ResetCameraClippingRange()
            self.render_window.Render()

    def _save_screenshot_exact_size(self, path: str, target_size):
        """Rend la scene dans une fenetre VTK hors ecran de taille exacte.

        Le renderer est detache temporairement de la fenetre visible et
        rattache a une fenetre offscreen `target_size`, pour ne jamais
        redimensionner la fenetre affichee a l'ecran.
        """
        width, height = int(target_size[0]), int(target_size[1])
        if self.renderer is None:
            raise RuntimeError("Renderer VTK indisponible.")

        offscreen = vtk.vtkRenderWindow()
        offscreen.SetOffScreenRendering(1)
        offscreen.SetSize(width, height)

        minimap = self._minimap
        with_minimap = minimap.visible and minimap.renderer is not None
        self.render_window.RemoveRenderer(self.renderer)
        offscreen.AddRenderer(self.renderer)
        if with_minimap:
            self.render_window.RemoveRenderer(minimap.renderer)
            offscreen.SetNumberOfLayers(minimap.LAYER + 1)
            offscreen.AddRenderer(minimap.renderer)
            minimap.set_export_viewport(width, height, height / max(1, self.height()))
        try:
            offscreen.Render()
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(offscreen)
            w2i.SetInputBufferTypeToRGB()
            w2i.ReadFrontBufferOff()
            w2i.Update()

            writer = vtk.vtkPNGWriter()
            writer.SetFileName(path)
            writer.SetInputConnection(w2i.GetOutputPort())
            writer.Write()
        finally:
            offscreen.RemoveRenderer(self.renderer)
            self.render_window.AddRenderer(self.renderer)
            if with_minimap:
                offscreen.RemoveRenderer(minimap.renderer)
                self.render_window.AddRenderer(minimap.renderer)
                minimap.update_viewport()
            self.render_window.Render()

    def _actor_key(self, actor):
        return actor.GetAddressAsString("") if actor is not None else ""

    def _style_for_role(self, role: str):
        mapping = {
            "lines": (self.linear_color, self.linear_line_width),
            "planars": (self.planar_color, self.planar_line_width),
            "load_areas": (self.load_area_color, self.load_area_line_width),
            "support_punctual": (self.support_punctual_color, self.support_punctual_line_width),
            "support_linear": (self.support_linear_color, self.support_linear_line_width),
            "support_planar": (self.support_planar_color, self.support_planar_line_width),
            "punctual_load": (self.punctual_load_color, 1.0),
            "linear_load": (self.linear_load_color, 1.0),
            "planar_load": (self.planar_load_color, 1.0),
        }
        return mapping.get(role, ((1.0, 1.0, 1.0), 1.0))

    def _line_section_name(self, source_idx: int) -> str:
        props = self._model_data.get("line_properties") or []
        if 0 <= source_idx < len(props):
            prop = props[source_idx]
            if isinstance(prop, dict):
                section_name = str(prop.get("section") or "").strip()
                if section_name:
                    return section_name
                rows = prop.get("rows") or []
                for i in range(0, max(0, len(rows) - 1), 2):
                    label = str(rows[i] or "").strip().lower()
                    if label == "section":
                        value = str(rows[i + 1] or "").strip()
                        if value:
                            return value
        return "Section inconnue"

    def _make_section_color(self, section_name: str):
        key = str(section_name or "Section inconnue").strip() or "Section inconnue"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return (
            80 + digest[0] % 156,
            80 + digest[1] % 156,
            80 + digest[2] % 156,
        )

    def _get_section_color(self, section_name: str):
        color = self._section_color_map.get(section_name)
        if color is None:
            color = self._make_section_color(section_name)
            self._section_color_map[section_name] = color
        return color

    def set_color_by_section(self, enabled: bool):
        self._color_by_section = bool(enabled)
        if self._color_by_section:
            self._section_color_map = {}
        self._rebuild_filtered_structural_actors()

    def set_planar_thickness_enabled(self, enabled: bool):
        self._planar_thickness_enabled = bool(enabled)
        self._rebuild_planar_faces_actor()
        self._apply_visibility_state()
        if self.render_window is not None:
            self.render_window.Render()


    def _base_face_color_opacity(self, role: str):
        if role == "planars":
            return self.planar_color, self.planar_faces_base_opacity * self._transparency_factor()
        if role == "load_areas":
            return self.load_area_color, self.load_areas_faces_base_opacity * self._transparency_factor()
        if role == "support_planar":
            return self.support_planar_color, self.support_planar_faces_base_opacity * self._transparency_factor()
        return self.selection_color, max(0.18, 0.30 * self._transparency_factor())

    def _register_pickable_actor(self, actor, role: str):
        if actor is None:
            return
        self._pickable_actors[self._actor_key(actor)] = {"actor": actor, "role": role}

    def _unregister_pickable_actor(self, actor):
        if actor is None:
            return
        self._pickable_actors.pop(self._actor_key(actor), None)

    def _add_actor(self, actor, role: str | None = None, pickable: bool = False):
        if actor is None:
            return None
        self.renderer.AddActor(actor)
        self._actors.append(actor)
        self._clip.apply_to_actor(actor)
        if pickable and role:
            self._register_pickable_actor(actor, role)
        return actor

    def _remove_actor(self, actor):
        if actor is None:
            return
        self._unregister_pickable_actor(actor)
        if actor in self._selection_overlay_actors:
            self._selection_overlay_actors.remove(actor)
        if actor in self._diagram_overlay_actors:
            self._diagram_overlay_actors.remove(actor)
        if actor in self._actors:
            self._actors.remove(actor)
        self.renderer.RemoveActor(actor)

    def _replace_actor(self, attr_name: str, actor, role: str | None = None, pickable: bool = False):
        old_actor = getattr(self, attr_name)
        if old_actor is not None:
            self._remove_actor(old_actor)
        setattr(self, attr_name, self._add_actor(actor, role=role, pickable=pickable))

    def _make_int_array(self):
        arr = vtk.vtkIntArray()
        arr.SetName(self.ELEMENT_INDEX_ARRAY)
        return arr

    def _make_polydata_actor(self, polydata, color, line_width=1.0, opacity=1.0):
        if polydata is None or polydata.GetNumberOfCells() == 0:
            return None
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        section_colors = polydata.GetCellData().GetArray("section_colors")
        if section_colors is not None:
            mapper.SetScalarModeToUseCellData()
            mapper.SetColorModeToDirectScalars()
            mapper.ScalarVisibilityOn()
        else:
            mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.PickableOn()
        prop = actor.GetProperty()
        prop.SetColor(*color)
        prop.SetOpacity(opacity)
        prop.SetLineWidth(line_width)
        return actor

    def _make_surface_actor(self, polydata, color, opacity):
        actor = self._make_polydata_actor(polydata, color, line_width=1.0, opacity=opacity)
        if actor is not None:
            prop = actor.GetProperty()
            prop.SetRepresentationToSurface()
            prop.EdgeVisibilityOff()
            prop.SetInterpolationToPhong()
            prop.SetAmbient(0.20)
            prop.SetDiffuse(0.85)
            prop.SetSpecular(0.08)
            prop.SetSpecularPower(18.0)
        return actor

    def _make_wire_actor(self, polydata, color, line_width):
        actor = self._make_polydata_actor(polydata, color, line_width=line_width, opacity=1.0)
        if actor is not None:
            actor.GetProperty().SetRepresentationToSurface()
        return actor

    def _normalize_vector3(self, vec):
        try:
            x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
        except Exception:
            return None
        length = math.sqrt(x * x + y * y + z * z)
        if length <= 1e-12:
            return None
        return (x / length, y / length, z / length)

    def _polygon_local_frame(self, outer):
        """Repere local (normale, u, v) d'un polygone 3D : normale via le
        premier triangle non degenere du contour, u le long du premier
        segment non degenere, v = normal x u. Fallbacks identiques si le
        contour est trop degenere pour en tirer un axe (polygone a 2 points
        distincts, etc.)."""
        normal = None
        for i in range(1, len(outer) - 1):
            ax, ay, az = outer[0]
            bx, by, bz = outer[i]
            cx, cy, cz = outer[i + 1]
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            normal = self._normalize_vector3((uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx))
            if normal is not None:
                break
        if normal is None:
            normal = (0.0, 0.0, 1.0)

        u_vec = None
        for i in range(len(outer)):
            p1 = outer[i]
            p2 = outer[(i + 1) % len(outer)]
            u_vec = self._normalize_vector3((p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]))
            if u_vec is not None:
                break
        if u_vec is None:
            fallback = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
            proj = fallback[0] * normal[0] + fallback[1] * normal[1] + fallback[2] * normal[2]
            u_vec = self._normalize_vector3((fallback[0] - proj * normal[0], fallback[1] - proj * normal[1], fallback[2] - proj * normal[2])) or (1.0, 0.0, 0.0)

        v_vec = self._normalize_vector3((
            normal[1] * u_vec[2] - normal[2] * u_vec[1],
            normal[2] * u_vec[0] - normal[0] * u_vec[2],
            normal[0] * u_vec[1] - normal[1] * u_vec[0],
        )) or (0.0, 1.0, 0.0)

        return normal, u_vec, v_vec

    def _compute_planar_support_centroid_info(self, item: dict):
        if not isinstance(item, dict):
            return None
        outer = list(item.get("outer") or [])
        openings = list(item.get("openings") or [])
        if len(outer) < 3:
            return None

        poly = self._build_surface_polydata_with_openings(outer, openings)
        area_sum = 0.0
        cx = cy = cz = 0.0

        if poly is not None and poly.GetNumberOfCells() > 0:
            for cell_id in range(poly.GetNumberOfCells()):
                cell = poly.GetCell(cell_id)
                if cell is None or cell.GetNumberOfPoints() < 3:
                    continue
                p0 = poly.GetPoint(cell.GetPointId(0))
                for i in range(1, cell.GetNumberOfPoints() - 1):
                    p1 = poly.GetPoint(cell.GetPointId(i))
                    p2 = poly.GetPoint(cell.GetPointId(i + 1))
                    ax, ay, az = p0
                    bx, by, bz = p1
                    cx2, cy2, cz2 = p2
                    ux, uy, uz = bx - ax, by - ay, bz - az
                    vx, vy, vz = cx2 - ax, cy2 - ay, cz2 - az
                    cross_x = uy * vz - uz * vy
                    cross_y = uz * vx - ux * vz
                    cross_z = ux * vy - uy * vx
                    area = 0.5 * math.sqrt(cross_x * cross_x + cross_y * cross_y + cross_z * cross_z)
                    if area <= 1e-12:
                        continue
                    tri_cx = (ax + bx + cx2) / 3.0
                    tri_cy = (ay + by + cy2) / 3.0
                    tri_cz = (az + bz + cz2) / 3.0
                    cx += tri_cx * area
                    cy += tri_cy * area
                    cz += tri_cz * area
                    area_sum += area

        if area_sum > 1e-12:
            center = (cx / area_sum, cy / area_sum, cz / area_sum)
        else:
            sx = sum(float(pt[0]) for pt in outer)
            sy = sum(float(pt[1]) for pt in outer)
            sz = sum(float(pt[2]) for pt in outer)
            count = float(len(outer))
            center = (sx / count, sy / count, sz / count)

        _normal, u_vec, v_vec = self._polygon_local_frame(outer)

        size = max(0.10, float(self.support_punctual_size))

        return {
            "point": center,
            "u": u_vec,
            "v": v_vec,
            "size": size,
            "x": float(center[0]),
            "y": float(center[1]),
            "z": float(center[2]),
        }

    def get_planar_support_centroid_info(self, index: int):
        items = self._model_data.get("planar_supports", [])
        if 0 <= int(index) < len(items):
            return self._compute_planar_support_centroid_info(items[int(index)])
        return None

    def _build_centroid_cross_polydata(self, center, u_vec, v_vec, size: float):
        try:
            cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
        except Exception:
            return None
        u_vec = self._normalize_vector3(u_vec) or (1.0, 0.0, 0.0)
        v_vec = self._normalize_vector3(v_vec) or (0.0, 1.0, 0.0)
        half = max(0.01, float(size) * 0.5)

        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()

        segments = [
            ((cx - u_vec[0] * half, cy - u_vec[1] * half, cz - u_vec[2] * half),
             (cx + u_vec[0] * half, cy + u_vec[1] * half, cz + u_vec[2] * half)),
            ((cx - v_vec[0] * half, cy - v_vec[1] * half, cz - v_vec[2] * half),
             (cx + v_vec[0] * half, cy + v_vec[1] * half, cz + v_vec[2] * half)),
        ]

        pid = 0
        for p1, p2 in segments:
            points.InsertNextPoint(*p1)
            points.InsertNextPoint(*p2)
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, pid)
            line.GetPointIds().SetId(1, pid + 1)
            cells.InsertNextCell(line)
            pid += 2

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        return poly

    def clear_planar_support_result_centroid(self, render: bool = True):
        if self._support_planar_centroid_actor is not None:
            self._remove_actor(self._support_planar_centroid_actor)
            self._support_planar_centroid_actor = None
            if render:
                self.renderer.ResetCameraClippingRange()
                self.render_window.Render()

    def show_planar_support_result_centroid(self, centroid_info):
        self.clear_planar_support_result_centroid(render=False)
        if not isinstance(centroid_info, dict):
            self.render_window.Render()
            return
        poly = self._build_centroid_cross_polydata(
            centroid_info.get("point"),
            centroid_info.get("u"),
            centroid_info.get("v"),
            float(centroid_info.get("size", 0.10) or 0.10),
        )
        actor = self._make_wire_actor(poly, self.selection_color, self.support_planar_line_width)
        if actor is not None:
            actor.PickableOff()
            self._support_planar_centroid_actor = self._add_actor(actor, role=None, pickable=False)
            self._apply_visibility_state()
        else:
            self.render_window.Render()

    def _build_lines_polydata(self, lines, element_indexes=None, include_section_colors=True):
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        pid = 0
        mapped_indexes = list(element_indexes or [])
        section_colors = vtk.vtkUnsignedCharArray()
        section_colors.SetName("section_colors")
        section_colors.SetNumberOfComponents(3)
        has_section_colors = False

        for idx, seg in enumerate(lines or []):
            if not seg or len(seg) != 2:
                continue
            p1, p2 = seg
            points.InsertNextPoint(*p1)
            points.InsertNextPoint(*p2)
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, pid)
            line.GetPointIds().SetId(1, pid + 1)
            cells.InsertNextCell(line)
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            elem_ids.InsertNextValue(int(source_idx))
            if self._color_by_section and include_section_colors:
                rgb = self._get_section_color(self._line_section_name(source_idx))
                section_colors.InsertNextTuple3(*rgb)
                has_section_colors = True
            pid += 2

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        poly.GetCellData().AddArray(elem_ids)
        if has_section_colors:
            poly.GetCellData().SetScalars(section_colors)
        return poly

    def _build_support_points_polydata(self, points_list, element_indexes=None):
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        mapped_indexes = list(element_indexes or [])

        for idx, pt in enumerate(points_list or []):
            if not isinstance(pt, (list, tuple)) or len(pt) < 3:
                continue
            pid = points.InsertNextPoint(float(pt[0]), float(pt[1]), float(pt[2]))
            vertex = vtk.vtkVertex()
            vertex.GetPointIds().SetId(0, pid)
            cells.InsertNextCell(vertex)
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            elem_ids.InsertNextValue(int(source_idx))

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetVerts(cells)
        poly.GetCellData().AddArray(elem_ids)
        return poly

    def _make_support_points_actor(self, points_list, role: str = "support_punctual", element_indexes=None):
        poly = self._build_support_points_polydata(points_list, element_indexes=element_indexes)
        if poly is None or poly.GetNumberOfPoints() == 0:
            return None
        actor = self._make_polydata_actor(poly, self.support_punctual_color, line_width=self.support_punctual_line_width, opacity=1.0)
        if actor is not None:
            prop = actor.GetProperty()
            prop.SetRepresentationToPoints()
            prop.SetPointSize(max(1.0, float(self.support_punctual_size) * 10.0))
            prop.RenderPointsAsSpheresOn()
        return actor

    def _build_loops_wire_polydata(self, items, openings: bool = False, element_indexes=None):
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        pid = 0
        mapped_indexes = list(element_indexes or [])

        for idx, item in enumerate(items or []):
            loops = item.get("openings", []) if openings else [item.get("outer")]
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            for loop in loops:
                loop = list(loop or [])
                if len(loop) < 2:
                    continue
                ids = []
                for pt in loop:
                    points.InsertNextPoint(*pt)
                    ids.append(pid)
                    pid += 1
                for i in range(len(ids)):
                    line = vtk.vtkLine()
                    line.GetPointIds().SetId(0, ids[i])
                    line.GetPointIds().SetId(1, ids[(i + 1) % len(ids)])
                    cells.InsertNextCell(line)
                    elem_ids.InsertNextValue(int(source_idx))

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        poly.GetCellData().AddArray(elem_ids)
        return poly

    def _build_surface_polydata_with_openings(self, outer, openings=None):
        outer = list(outer or [])
        openings = list(openings or [])
        if len(outer) < 3:
            return None

        if not openings:
            # Pas de trou : pas besoin de vtkContourTriangulator (evite un
            # Update() par capuchon, x2 par element x5800 sur un gros modele ->
            # gain majeur en mode Profiles). Un contour convexe reste un polygone
            # unique ; un contour concave (I, H, L, T...) doit etre decoupe, sinon
            # l'affichage le triangule en eventail et l'extremite est deformee.
            if self._polygon_is_convex(outer):
                return self._single_polygon_polydata(outer)
            triangulated = self._triangulated_polygon_polydata(outer)
            return triangulated if triangulated is not None else self._single_polygon_polydata(outer)

        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        pid = 0
        loops = [outer]
        for hole in openings:
            if len(hole) >= 3:
                loops.append(list(reversed(hole)))

        for loop in loops:
            n = len(loop)
            if n < 3:
                continue
            ids = []
            for pt in loop:
                points.InsertNextPoint(*pt)
                ids.append(pid)
                pid += 1
            polyline = vtk.vtkPolyLine()
            polyline.GetPointIds().SetNumberOfIds(n + 1)
            for i, point_id in enumerate(ids):
                polyline.GetPointIds().SetId(i, point_id)
            polyline.GetPointIds().SetId(n, ids[0])
            lines.InsertNextCell(polyline)

        contour = vtk.vtkPolyData()
        contour.SetPoints(points)
        contour.SetLines(lines)

        triangulator = vtk.vtkContourTriangulator()
        triangulator.SetInputData(contour)
        triangulator.Update()

        out = vtk.vtkPolyData()
        out.ShallowCopy(triangulator.GetOutput())
        if out.GetNumberOfCells() > 0:
            return out

        return self._single_polygon_polydata(outer)

    @staticmethod
    def _polygon_is_convex(points, tol=1e-9):
        n = len(points)
        if n <= 3:
            return True
        nx = ny = nz = 0.0
        for i in range(n):
            x0, y0, z0 = points[i]
            x1, y1, z1 = points[(i + 1) % n]
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        nnorm = math.sqrt(nx * nx + ny * ny + nz * nz)
        if nnorm < 1e-18:
            return True
        sign = 0
        for i in range(n):
            a, b, c = points[i], points[(i + 1) % n], points[(i + 2) % n]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - b[0], c[1] - b[1], c[2] - b[2]
            d = (uy * vz - uz * vy) * nx + (uz * vx - ux * vz) * ny + (ux * vy - uy * vx) * nz
            scale = math.sqrt(ux * ux + uy * uy + uz * uz) * math.sqrt(vx * vx + vy * vy + vz * vz) * nnorm
            if abs(d) <= tol * scale:
                continue  # sommets alignes
            current = 1 if d > 0 else -1
            if sign == 0:
                sign = current
            elif current != sign:
                return False
        return True

    @staticmethod
    def _triangulated_polygon_polydata(outer):
        """Contour simple (sans trou), eventuellement concave, decoupe en
        triangles par vtkPolygon.Triangulate ; None si le decoupage echoue."""
        n = len(outer)
        polygon = vtk.vtkPolygon()
        polygon.GetPoints().SetNumberOfPoints(n)
        polygon.GetPointIds().SetNumberOfIds(n)
        points = vtk.vtkPoints()
        for i, pt in enumerate(outer):
            polygon.GetPoints().SetPoint(i, *pt)
            polygon.GetPointIds().SetId(i, i)
            points.InsertNextPoint(*pt)
        ids = vtk.vtkIdList()
        if not polygon.Triangulate(0, ids, vtk.vtkPoints()) or ids.GetNumberOfIds() < 3:
            return None
        cells = vtk.vtkCellArray()
        for k in range(0, ids.GetNumberOfIds() - 2, 3):
            cells.InsertNextCell(3)
            for j in range(3):
                cells.InsertCellPoint(ids.GetId(k + j))
        out = vtk.vtkPolyData()
        out.SetPoints(points)
        out.SetPolys(cells)
        return out

    @staticmethod
    def _single_polygon_polydata(outer):
        """Polydata a une seule cellule polygone (contour simple, sans trou)."""
        points = vtk.vtkPoints()
        polygon = vtk.vtkPolygon()
        polygon.GetPointIds().SetNumberOfIds(len(outer))
        for i, pt in enumerate(outer):
            points.InsertNextPoint(*pt)
            polygon.GetPointIds().SetId(i, i)

        polys = vtk.vtkCellArray()
        polys.InsertNextCell(polygon)
        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetPolys(polys)
        return poly

    def _build_faces_polydata(self, items, element_indexes=None):
        append = vtk.vtkAppendPolyData()
        appended = False
        mapped_indexes = list(element_indexes or [])

        for idx, item in enumerate(items or []):
            poly = self._build_surface_polydata_with_openings(item.get("outer"), item.get("openings", []))
            if poly is None or poly.GetNumberOfCells() == 0:
                continue
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            elem_ids = self._make_int_array()
            for _ in range(poly.GetNumberOfCells()):
                elem_ids.InsertNextValue(int(source_idx))
            poly.GetCellData().AddArray(elem_ids)
            append.AddInputData(poly)
            appended = True

        if not appended:
            return None

        append.Update()

        clean = vtk.vtkCleanPolyData()
        clean.SetInputConnection(append.GetOutputPort())
        clean.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(clean.GetOutputPort())
        normals.ComputePointNormalsOff()
        normals.ComputeCellNormalsOn()
        normals.ConsistencyOn()
        # Pas d'AutoOrientNormalsOn ici : verifie empiriquement peu fiable,
        # meme sur une simple face fermee (peut inverser un triangle au hasard).
        normals.SplittingOff()
        normals.Update()

        out = vtk.vtkPolyData()
        out.ShallowCopy(normals.GetOutput())
        return out

    def _build_planar_thickness_polydata(self, items, thicknesses=None, eccentricities=None, element_indexes=None):
        """Comme _build_faces_polydata, mais chaque panneau devient un solide
        epaissi (loft entre le plan -epaisseur/2 et +epaisseur/2 autour du
        plan de reference, decale de l'excentrement le long de la normale
        locale) au lieu d'une face plane sans epaisseur. Reutilise le loft
        deja utilise pour les solides de profils filaires (_loft_solid_polydata),
        qui gere deja les trous (openings) et les parois."""
        append = vtk.vtkAppendPolyData()
        appended = False
        mapped_indexes = list(element_indexes or [])
        thick_list = list(thicknesses or [])
        ecc_list = list(eccentricities or [])

        for idx, item in enumerate(items or []):
            outer = list((item or {}).get("outer") or [])
            if len(outer) < 3:
                continue
            openings = [list(h) for h in ((item or {}).get("openings") or []) if len(h) >= 3]
            thickness = float(thick_list[idx]) if idx < len(thick_list) else 0.0
            eccentricity = float(ecc_list[idx]) if idx < len(ecc_list) else 0.0
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx

            normal, u_vec, v_vec = self._polygon_local_frame(outer)
            origin = outer[0]

            def _project(pt, _origin=origin, _u=u_vec, _v=v_vec):
                dx, dy, dz = pt[0] - _origin[0], pt[1] - _origin[1], pt[2] - _origin[2]
                return (dx * _u[0] + dy * _u[1] + dz * _u[2],
                        dx * _v[0] + dy * _v[1] + dz * _v[2])

            loops2d = [[_project(p) for p in outer]]
            for hole in openings:
                loops2d.append([_project(p) for p in hole])

            half = thickness / 2.0

            def _mk_to3d(offset, _origin=origin, _u=u_vec, _v=v_vec, _n=normal):
                def to3d(p2):
                    w, d = p2
                    return (_origin[0] + w * _u[0] + d * _v[0] + offset * _n[0],
                            _origin[1] + w * _u[1] + d * _v[1] + offset * _n[1],
                            _origin[2] + w * _u[2] + d * _v[2] + offset * _n[2])
                return to3d

            pd = self._loft_solid_polydata(
                loops2d, _mk_to3d(eccentricity - half),
                loops2d, _mk_to3d(eccentricity + half),
                int(source_idx),
            )
            if pd is not None and pd.GetNumberOfCells() > 0:
                append.AddInputData(pd)
                appended = True

        if not appended:
            return None

        append.Update()
        out = vtk.vtkPolyData()
        out.ShallowCopy(append.GetOutput())
        return out if out.GetNumberOfCells() > 0 else None

    def _tag_cells(self, polydata, source_idx: int):
        elem_ids = self._make_int_array()
        for _ in range(polydata.GetNumberOfCells()):
            elem_ids.InsertNextValue(int(source_idx))
        polydata.GetCellData().AddArray(elem_ids)
        return polydata

    def _profile_walls_polydata(self, loops0, loops1, to3d_start, to3d_end, source_idx: int):
        points = vtk.vtkPoints()
        polys = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        pid = 0
        for k in range(min(len(loops0), len(loops1))):
            ring0 = [to3d_start(p) for p in loops0[k]]
            ring1 = [to3d_end(p) for p in loops1[k]]
            n = min(len(ring0), len(ring1))
            if n < 3:
                continue
            for i in range(n):
                j = (i + 1) % n
                for v in (ring0[i], ring0[j], ring1[j], ring1[i]):
                    points.InsertNextPoint(*v)
                quad = vtk.vtkQuad()
                for m in range(4):
                    quad.GetPointIds().SetId(m, pid + m)
                polys.InsertNextCell(quad)
                elem_ids.InsertNextValue(int(source_idx))
                pid += 4
        if polys.GetNumberOfCells() == 0:
            return None
        pd = vtk.vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(polys)
        pd.GetCellData().AddArray(elem_ids)
        return pd

    @staticmethod
    def _section_frame(start, end):
        """Repere de section (u = largeur / axe local y, v = hauteur / axe local
        z) identique a celui de l'export IFC afin de ne pas inverser les profils
        non bi-symetriques : u = normalize(up_ref x beam_dir), v = beam_dir x u.
        """
        beam = _normalize_vector3((end[0] - start[0], end[1] - start[1], end[2] - start[2])) or (1.0, 0.0, 0.0)
        up = (0.0, 0.0, 1.0)
        if abs(beam[0] * up[0] + beam[1] * up[1] + beam[2] * up[2]) > 0.999:
            up = (1.0, 0.0, 0.0)
        u = _normalize_vector3(_cross_vector3(up, beam)) or (1.0, 0.0, 0.0)
        v = _normalize_vector3(_cross_vector3(beam, u)) or (0.0, 0.0, 1.0)
        return u, v

    def _loft_solid_polydata(self, loops_a, to3d_a, loops_b, to3d_b, source_idx: int):
        """Solide ferme entre deux jeux de boucles (loops_a a une station,
        loops_b a une autre) : 2 capuchons + parois. loops[0] = contour,
        loops[1:] = trous. Un capuchon degenere (points colineaires) est ignore
        (cas du coin de jarret cote contact, ecrase a plat)."""
        append = vtk.vtkAppendPolyData()
        added = False
        for to3d, loops in ((to3d_a, loops_a), (to3d_b, loops_b)):
            if _poly2_area(loops[0]) < 1e-9:
                continue  # contour ecrase (cote contact d'un jarret) : pas de capuchon
            outer3d = [to3d(p) for p in loops[0]]
            holes3d = [[to3d(p) for p in loops[k]] for k in range(1, len(loops))]
            cap = self._build_surface_polydata_with_openings(outer3d, holes3d)
            if cap is not None and cap.GetNumberOfCells() > 0:
                append.AddInputData(self._tag_cells(cap, source_idx))
                added = True
        walls = self._profile_walls_polydata(loops_a, loops_b, to3d_a, to3d_b, source_idx)
        if walls is not None:
            append.AddInputData(walls)
            added = True
        if not added:
            return None
        append.Update()
        out = vtk.vtkPolyData()
        out.ShallowCopy(append.GetOutput())
        return out if out.GetNumberOfCells() > 0 else None

    def _build_one_profile_polydata(self, start, end, section, source_idx: int):
        """Solide filaire : profil de base (ou 2 elements d'un profil compose)
        extrude de start a end, plus les coins de jarret (section['haunches'])."""
        ang = float(section.get("angle_rad") or 0.0)  # deja en radians (API AD)
        off = section.get("offset") or [0.0, 0.0]
        ox, oy = float(off[0]), float(off[1])
        u_axis, v_axis = self._section_frame(start, end)

        def _xform(loop):
            return translate_polygon2(rotate_poly2(loop, ang), dx=ox, dy=oy)

        def _loops(contour):
            return [_xform(loop) for loop in [contour["outer"]] + list(contour.get("holes") or [])]

        # x -> u (largeur / axe local y), y -> v (hauteur / axe local z)
        def _mk_to3d(base):
            def to3d(p2):
                w, d = float(p2[0]), float(p2[1])
                return (base[0] + w * u_axis[0] + d * v_axis[0],
                        base[1] + w * u_axis[1] + d * v_axis[1],
                        base[2] + w * u_axis[2] + d * v_axis[2])
            return to3d

        def _at(t):
            return _mk_to3d((start[0] + (end[0] - start[0]) * t,
                             start[1] + (end[1] - start[1]) * t,
                             start[2] + (end[2] - start[2]) * t))

        # pieces : (loops_a, to3d_a, loops_b, to3d_b) — un solide loft par piece
        pieces = []
        combined = section.get("combined")
        if combined:
            combined_end = section.get("combined_end") or combined
            if len(combined_end) != len(combined):
                combined_end = combined
            for pa, pb in zip(combined, combined_end):
                pieces.append(([_xform(pa)], _at(0.0), [_xform(pb)], _at(1.0)))
        else:
            contour0 = profile_polygon(section.get("dims"))
            if not contour0 or len(contour0.get("outer") or []) < 3:
                return None
            dims_end = section.get("dims_end")
            contour1 = profile_polygon(dims_end) if dims_end else contour0
            if (not contour1
                    or len(contour1.get("outer") or []) != len(contour0["outer"])
                    or len(contour1.get("holes") or []) != len(contour0.get("holes") or [])):
                contour1 = contour0
            pieces.append((_loops(contour0), _at(0.0), _loops(contour1), _at(1.0)))
            for h in section.get("haunches") or []:
                pieces.append(([_xform(h["poly_start"])], _at(float(h["t_start"])),
                               [_xform(h["poly_end"])], _at(float(h["t_end"]))))

        if len(pieces) == 1:
            # Cas majoritaire (pas de profil compose, pas de jarret) : pas besoin
            # de vtkAppendPolyData pour fusionner une seule piece avec elle-meme.
            loops_a, to3d_a, loops_b, to3d_b = pieces[0]
            pd = self._loft_solid_polydata(loops_a, to3d_a, loops_b, to3d_b, source_idx)
            return pd if (pd is not None and pd.GetNumberOfCells() > 0) else None

        append = vtk.vtkAppendPolyData()
        added = False
        for loops_a, to3d_a, loops_b, to3d_b in pieces:
            pd = self._loft_solid_polydata(loops_a, to3d_a, loops_b, to3d_b, source_idx)
            if pd is not None:
                append.AddInputData(pd)
                added = True
        if not added:
            return None
        append.Update()
        out = vtk.vtkPolyData()
        out.ShallowCopy(append.GetOutput())
        return out if out.GetNumberOfCells() > 0 else None

    def _build_profiles_polydata(self, lines, line_sections, element_indexes=None, progress_cb=None):
        """progress_cb(done, total), si fourni, est appele a chaque palier de
        pourcentage franchi (utilise par BuildProfilesWorker pour la barre de
        progression lors du switch vers un mode Profiles)."""
        append = vtk.vtkAppendPolyData()
        appended = False
        mapped_indexes = list(element_indexes or [])
        sections = list(line_sections or [])
        total = len(lines or [])
        last_pct = -1
        for idx, seg in enumerate(lines or []):
            if not seg or len(seg) != 2:
                continue
            section = sections[idx] if idx < len(sections) else None
            if not isinstance(section, dict):
                continue
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            pd = self._build_one_profile_polydata(seg[0], seg[1], section, int(source_idx))
            if pd is not None and pd.GetNumberOfCells() > 0:
                if self._color_by_section:
                    rgb = self._get_section_color(self._line_section_name(int(source_idx)))
                    colors = vtk.vtkUnsignedCharArray()
                    colors.SetName("section_colors")
                    colors.SetNumberOfComponents(3)
                    for _ in range(pd.GetNumberOfCells()):
                        colors.InsertNextTuple3(*rgb)
                    pd.GetCellData().SetScalars(colors)
                append.AddInputData(pd)
                appended = True
            if progress_cb is not None and total:
                pct = (idx + 1) * 100 // total
                if pct != last_pct:
                    last_pct = pct
                    progress_cb(idx + 1, total)
        if not appended:
            return None
        append.Update()

        # Capuchons et parois sont construits comme des morceaux de polydata
        # distincts (points non partages, meme aux aretes communes) : sans
        # soudure, ConsistencyOn ne peut harmoniser le sens des normales qu'a
        # l'interieur de chaque morceau isole, jamais entre eux - d'ou des
        # faces noires/mal eclairees aleatoires. vtkCleanPolyData soude les
        # points geometriquement coincidents (tolerance exacte : ils viennent
        # de la meme formule to3d()) pour que chaque profil devienne un seul
        # solide connecte, sur lequel ConsistencyOn peut alors se propager
        # correctement.
        clean = vtk.vtkCleanPolyData()
        clean.SetInputConnection(append.GetOutputPort())
        clean.PointMergingOn()
        clean.SetTolerance(0.0)
        clean.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(clean.GetOutputPort())
        normals.ComputePointNormalsOff()
        normals.ComputeCellNormalsOn()
        normals.ConsistencyOn()
        # Pas d'AutoOrientNormalsOn : peu fiable, meme sur un solide ferme et
        # soude (verifie empiriquement - inverse parfois une face au hasard).
        # ConsistencyOn seul rend le sens uniforme sur tout le solide soude,
        # mais ce sens uniforme se trouve etre vers l'interieur (verifie
        # empiriquement) - FlipNormalsOn corrige ca globalement.
        normals.FlipNormalsOn()
        normals.SplittingOff()
        normals.Update()

        out = vtk.vtkPolyData()
        out.ShallowCopy(normals.GetOutput())
        return out

    def _build_punctual_supports_polydata(self, support_points, element_indexes=None):
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        pid = 0
        size = self.support_punctual_size
        mapped_indexes = list(element_indexes or [])

        for idx, point in enumerate(support_points or []):
            if not point or len(point) != 3:
                continue
            source_idx = mapped_indexes[idx] if idx < len(mapped_indexes) else idx
            cx, cy, cz = point
            half = size * 0.5
            base_z = cz - size
            local_pts = [
                (cx - half, cy - half, base_z),
                (cx + half, cy - half, base_z),
                (cx + half, cy + half, base_z),
                (cx - half, cy + half, base_z),
                (cx, cy, cz),
            ]
            ids = []
            for pt in local_pts:
                points.InsertNextPoint(*pt)
                ids.append(pid)
                pid += 1
            edges = [
                (0, 1), (1, 2), (2, 3), (3, 0),
                (0, 4), (1, 4), (2, 4), (3, 4),
            ]
            for a, b in edges:
                line = vtk.vtkLine()
                line.GetPointIds().SetId(0, ids[a])
                line.GetPointIds().SetId(1, ids[b])
                cells.InsertNextCell(line)
                elem_ids.InsertNextValue(int(source_idx))

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        poly.GetCellData().AddArray(elem_ids)
        return poly

    def _get_actor_polydata(self, actor):
        if actor is None or actor.GetMapper() is None:
            return None
        mapper = actor.GetMapper()
        mapper.Update()
        return mapper.GetInput()

    def _get_pick_hit(self, x: int, y: int, exclude_keys=None):
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.0035)
        picker.PickFromListOn()
        picker.InitializePickList()

        visible = False
        for key, info in self._pickable_actors.items():
            if exclude_keys and key in exclude_keys:
                continue
            actor = info["actor"]
            if actor is not None and actor.GetVisibility():
                picker.AddPickList(actor)
                visible = True
        if not visible:
            return None

        if not picker.Pick(x, y, 0, self.renderer):
            return None

        actor = picker.GetActor()
        cell_id = int(picker.GetCellId()) if hasattr(picker, "GetCellId") else -1
        if actor is None or cell_id < 0:
            return None

        actor_key = self._actor_key(actor)
        info = self._pickable_actors.get(actor_key)
        if not info:
            return None

        polydata = self._get_actor_polydata(actor)
        if polydata is None:
            return None

        arr = polydata.GetCellData().GetArray(self.ELEMENT_INDEX_ARRAY)
        if arr is None or cell_id >= arr.GetNumberOfTuples():
            return None

        element_index = int(arr.GetTuple1(cell_id))
        pos = picker.GetPickPosition()
        if not self._clip.accepts_point(pos):
            return None
        cam = self.renderer.GetActiveCamera().GetPosition() if self.renderer.GetActiveCamera() else (0.0, 0.0, 0.0)
        depth = (pos[0] - cam[0]) ** 2 + (pos[1] - cam[1]) ** 2 + (pos[2] - cam[2]) ** 2
        return {
            "role": info["role"],
            "index": element_index,
            "actor": actor,
            "cell_id": cell_id,
            "key": actor_key,
            "depth": depth,
        }

    def _get_pick_hit_stack(self, x: int, y: int, max_layers: int = 12):
        """Pick avant-vers-arrière : renvoie tous les éléments sous le pixel,
        du plus proche au plus lointain, en retirant l'acteur touché entre
        chaque passe. Permet d'atteindre un élément masqué par une face
        surfacique."""
        hits = []
        exclude = set()
        for _ in range(max_layers):
            hit = self._get_pick_hit(x, y, exclude_keys=exclude)
            if hit is None:
                break
            hits.append(hit)
            exclude.add(hit["key"])
        return hits

    def _pick_selection_candidates(self, x: int, y: int):
        offsets = [
            (0, 0),
            (2, 0), (-2, 0), (0, 2), (0, -2),
            (2, 2), (-2, 2), (2, -2), (-2, -2),
            (4, 0), (-4, 0), (0, 4), (0, -4),
            (4, 4), (-4, 4), (4, -4), (-4, -4),
            (6, 0), (-6, 0), (0, 6), (0, -6),
            (8, 0), (-8, 0), (0, 8), (0, -8),
        ]
        peel = self._display_mode in ("hidden_faces", "wire_hidden", "profiles_hidden", "profiles_wire")
        found = {}
        for dx, dy in offsets:
            if peel and dx == 0 and dy == 0:
                hits = self._get_pick_hit_stack(x, y)
            else:
                hits = [self._get_pick_hit(x + dx, y + dy)]
            for hit in hits:
                if hit is None:
                    continue
                key = (hit["role"], int(hit["index"]))
                dist2 = dx * dx + dy * dy
                current = found.get(key)
                if current is None or (dist2, hit["depth"]) < (current["distance2"], current["depth"]):
                    hit["distance2"] = dist2
                    found[key] = hit

        results = list(found.values())
        if peel:
            results.sort(key=lambda item: (item["distance2"], item["depth"], item["role"], item["index"]))
        else:
            results.sort(key=lambda item: (item["distance2"], item["role"], item["index"]))
        for index in self._anomaly_overlay.pick(x, y):
            results.append({"role": "anomaly", "index": int(index), "depth": 0.0, "distance2": 0})
        return results

    def _clear_selection_overlay(self):
        for actor in list(self._selection_overlay_actors):
            self._remove_actor(actor)
        self._selection_overlay_actors = []

    def _selected_role_visible(self, role: str, face: bool = False):
        mode = self._display_mode
        show_faces = mode in ("hidden_faces", "wire_hidden", "full") or mode in _PROFILE_MODES
        show_planar_wire = mode in ("wireframe", "wire_hidden")
        if role == "lines":
            return self._show_lines
        if role == "planars":
            return self._show_planars and (show_faces if face else show_planar_wire)
        if role == "load_areas":
            return self._show_load_areas and (show_faces if face else show_planar_wire)
        if role == "support_punctual":
            return self._show_support_punctual
        if role == "support_linear":
            return self._show_support_linear
        if role == "support_planar":
            return self._show_support_planar and (show_faces if face else show_planar_wire)
        if role == "punctual_load":
            return self._show_punctual_loads
        if role == "linear_load":
            return self._show_linear_loads
        if role == "planar_load":
            return self._show_planar_loads
        return True

    def _make_selection_overlay_actors(self, role: str, index: int):
        overlays = []
        line_width = max(self.selection_line_width, self._style_for_role(role)[1] + 1.0)

        if role == "lines":
            # En mode profils la selection est rendue en recolorant les cellules
            # de _profiles_actor (cf. _rebuild_profiles_actor), pas par un overlay.
            if self._display_mode in _PROFILE_MODES:
                return overlays
            lines = self._model_data.get("lines", [])
            if 0 <= index < len(lines):
                poly = self._build_lines_polydata([lines[index]], include_section_colors=False)
                actor = self._make_wire_actor(poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)

        elif role == "planars":
            items = self._model_data.get("planars", [])
            if 0 <= index < len(items):
                item = items[index]
                wire_poly = self._build_loops_wire_polydata([{"outer": item.get("outer"), "openings": item.get("openings", [])}], openings=False)
                actor = self._make_wire_actor(wire_poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)
                opening_poly = self._build_loops_wire_polydata([{"outer": [], "openings": item.get("openings", [])}], openings=True)
                opening_actor = self._make_wire_actor(opening_poly, self.selection_color, line_width)
                if opening_actor:
                    overlays.append(opening_actor)
                if self._planar_thickness_enabled and self._display_mode in _PROFILE_MODES:
                    # Le recouvrement de selection doit suivre la meme geometrie
                    # (solide epaissi) que _planar_faces_actor, sinon une face
                    # plate au plan de reference se retrouve enterree a
                    # l'interieur du solide opaque et devient invisible.
                    thicknesses = self._model_data.get("planar_thicknesses", []) or []
                    eccentricities = self._model_data.get("planar_eccentricities", []) or []
                    thickness = float(thicknesses[index]) if index < len(thicknesses) else 0.0
                    eccentricity = float(eccentricities[index]) if index < len(eccentricities) else 0.0
                    face_poly = self._build_planar_thickness_polydata([item], [thickness], [eccentricity])
                else:
                    face_poly = self._build_faces_polydata([item])
                face_actor = self._make_surface_actor(face_poly, self.selection_color, max(0.18, 0.30 * self._transparency_factor()))
                if face_actor:
                    # Le recouvrement est geometriquement coincident avec la
                    # face de base (plate, ou solide epaissi) : sans decalage,
                    # le z-fighting le fait perdre a la face de base et le
                    # recouvrement devient invisible - surtout marque quand la
                    # surface est quasi perpendiculaire a la camera (ex: une
                    # toiture vue de dessus, contrairement a un mur vu de biais).
                    face_actor.GetMapper().SetResolveCoincidentTopologyToPolygonOffset()
                    face_actor.GetMapper().SetRelativeCoincidentTopologyPolygonOffsetParameters(-4, -4)
                    overlays.append(face_actor)

        elif role == "load_areas":
            items = self._model_data.get("load_areas", [])
            if 0 <= index < len(items):
                item = items[index]
                wire_poly = self._build_loops_wire_polydata([{"outer": item.get("outer"), "openings": item.get("openings", [])}], openings=False)
                actor = self._make_wire_actor(wire_poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)
                face_poly = self._build_faces_polydata([item])
                face_actor = self._make_surface_actor(face_poly, self.selection_color, max(0.18, 0.30 * self._transparency_factor()))
                if face_actor:
                    overlays.append(face_actor)

        elif role == "support_punctual":
            points = self._model_data.get("punctual_supports", [])
            if 0 <= index < len(points):
                poly = self._build_punctual_supports_polydata([points[index]])
                actor = self._make_wire_actor(poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)

        elif role == "support_linear":
            lines = self._model_data.get("linear_supports", [])
            if 0 <= index < len(lines):
                poly = self._build_lines_polydata([lines[index]])
                actor = self._make_wire_actor(poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)

        elif role == "support_planar":
            items = self._model_data.get("planar_supports", [])
            if 0 <= index < len(items):
                item = items[index]
                wire_poly = self._build_loops_wire_polydata([{"outer": item.get("outer"), "openings": item.get("openings", [])}], openings=False)
                actor = self._make_wire_actor(wire_poly, self.selection_color, line_width)
                if actor:
                    overlays.append(actor)
                face_poly = self._build_faces_polydata([item])
                face_actor = self._make_surface_actor(face_poly, self.selection_color, max(0.18, 0.30 * self._transparency_factor()))
                if face_actor:
                    overlays.append(face_actor)

        elif role in ("punctual_load", "linear_load", "planar_load"):
            # Charge redessinee en couleur de selection, normalisee sur les charges
            # actives (meme filtre de cas) pour coincider avec la charge affichee
            kind = role[:-len("_load")]
            loads = getattr(self, f"_{kind}_load_data")
            if 0 <= index < len(loads):
                case = getattr(self, f"_{kind}_load_case_filter")
                active = [ld for ld in loads if case is None or ld.get("load_case_eid") == case]
                builder = getattr(self, f"_build_{kind}_load_actors")
                extra = {} if kind == "punctual" else {"global_data": loads}
                actor_pairs = builder(
                    [loads[index]],
                    self.effective_load_scale(kind),
                    self.selection_color,
                    line_width=max(line_width, getattr(self, f"{kind}_load_line_width") + 1.0),
                    norm_loads=active,
                    **extra,
                )
                for a, _ in actor_pairs:
                    overlays.append(a)

        return overlays

    def _refresh_selection_overlay(self):
        self._clear_selection_overlay()
        for item in self._selected_items:
            overlays = self._make_selection_overlay_actors(item["role"], item["index"])
            for actor in overlays:
                self.renderer.AddActor(actor)
                self._actors.append(actor)
                self._clip.apply_to_actor(actor)
                self._selection_overlay_actors.append(actor)
        # En mode profils : recolorer (echange de scalaires, sans reconstruction).
        if self._display_mode in _PROFILE_MODES:
            self._apply_profiles_selection_colors()
        self._apply_visibility_state()

    def _orient_diagram_label(self, actor):
        """Place le texte d'une etiquette de diagramme vers l'exterieur, cote
        ecran : un vtkBillboardTextActor3D dessine son texte au-dessus de
        l'ancre et centre, ce qui recouvre le diagramme quand l'etiquette est
        en dessous ou sur le cote."""
        outward = getattr(actor, "_diagram_outward", None)
        if outward is None or self.renderer is None:
            return

        def to_display(point):
            self.renderer.SetWorldPoint(point[0], point[1], point[2], 1.0)
            self.renderer.WorldToDisplay()
            d = self.renderer.GetDisplayPoint()
            return d[0], d[1]

        pos = actor.GetPosition()
        x0, y0 = to_display(pos)
        x1, y1 = to_display((pos[0] + outward[0], pos[1] + outward[1], pos[2] + outward[2]))
        dx, dy = x1 - x0, y1 - y0
        tangent = getattr(actor, "_diagram_tangent", None)
        if tangent is not None:
            # Au point extreme la courbe est tangente a l'axe de l'element : on
            # ne garde de la direction "exterieure" que sa part perpendiculaire a
            # cette tangente (a l'ecran), pour que le texte reste du bon cote.
            tx, ty = to_display((pos[0] + tangent[0], pos[1] + tangent[1], pos[2] + tangent[2]))
            tx, ty = tx - x0, ty - y0
            tnorm = math.hypot(tx, ty)
            if tnorm > 1e-6:
                tx, ty = tx / tnorm, ty / tnorm
                along = dx * tx + dy * ty
                px, py = dx - along * tx, dy - along * ty
                if math.hypot(px, py) > 1e-6 * max(1.0, math.hypot(dx, dy)):
                    dx, dy = px, py
        tp = actor.GetTextProperty()
        if math.hypot(dx, dy) < 1e-6:
            dx, dy = 0.0, 1.0
        # Le texte est ancre par son coin le plus proche du diagramme : la boite
        # reste entierement dans le quadrant "exterieur", meme quand la courbe
        # est oblique a l'ecran.
        if abs(dx) > 0.3 * abs(dy):
            tp.SetJustificationToLeft() if dx > 0 else tp.SetJustificationToRight()
        else:
            tp.SetJustificationToCentered()
        if abs(dy) > 0.3 * abs(dx):
            tp.SetVerticalJustificationToBottom() if dy >= 0 else tp.SetVerticalJustificationToTop()
        else:
            tp.SetVerticalJustificationToCentered()

    def _on_camera_orient_labels(self, obj, event):
        for actor in self._diagram_label_actors:
            self._orient_diagram_label(actor)

    def clear_result_diagram(self):
        for actor in list(self._diagram_overlay_actors):
            self._remove_actor(actor)
        self._diagram_overlay_actors = []
        self._diagram_label_actors = []
        if hasattr(self, "render_window") and self.render_window is not None:
            self.render_window.Render()

    @staticmethod
    def _diagram_value_to_color(value: float, min_val: float, max_val: float):
        """Mappe une valeur scalaire vers une couleur style Advance Design.

        Bleu foncé = valeur minimale du diagramme (quel que soit son signe)
        Rouge      = valeur maximale du diagramme (quel que soit son signe)

        Ainsi un diagramme entièrement positif aura quand même son min en bleu
        et son max en rouge.
        """
        # Palette : bleu foncé → bleu clair → cyan → vert → jaune → orange → rouge
        stops = [
            (0.0, (0.0,  0.0,  0.55)),
            (0.2, (0.0,  0.50, 1.0)),
            (0.4, (0.0,  0.85, 0.85)),
            (0.5, (0.30, 0.85, 0.30)),
            (0.6, (1.0,  0.85, 0.0)),
            (0.8, (1.0,  0.45, 0.0)),
            (1.0, (0.85, 0.0,  0.0)),
        ]
        span = max_val - min_val
        if span < 1e-12:
            # Toutes les valeurs identiques → couleur médiane (vert)
            return (0.30, 0.85, 0.30)
        t = max(0.0, min(1.0, (value - min_val) / span))
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                alpha = (t - t0) / (t1 - t0) if (t1 - t0) > 1e-12 else 0.0
                return (
                    c0[0] + alpha * (c1[0] - c0[0]),
                    c0[1] + alpha * (c1[1] - c0[1]),
                    c0[2] + alpha * (c1[2] - c0[2]),
                )
        return stops[-1][1]

    def _build_linear_diagram_actors(self, line_points, series, title: str = "", line_property: dict = None, unit: str = "", decimals=None):
        """Construit et ajoute au renderer les acteurs VTK d'un diagramme filaire.

        Retourne la liste des acteurs créés (overlay + labels), sans toucher aux
        listes _diagram_overlay_actors / _diagram_label_actors existantes.
        Cela permet d'appeler cette méthode de manière additive.
        """
        if not isinstance(line_points, (list, tuple)) or len(line_points) != 2:
            return []
        if not isinstance(series, list) or len(series) < 2:
            return []

        try:
            p1 = tuple(float(v) for v in line_points[0])
            p2 = tuple(float(v) for v in line_points[1])
        except Exception:
            return []

        axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        length = math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2])
        if length <= 1e-9:
            return []
        u = (axis[0] / length, axis[1] / length, axis[2] / length)

        local_axes = ((line_property or {}).get("local_axes") or {}) if isinstance(line_property, dict) else {}
        normal = _normalize_vector3(local_axes.get("z")) if isinstance(local_axes, dict) else None
        if normal is None:
            rebuilt = _build_ad_local_axes(p1, p2, (line_property or {}).get("section_orientation_angle_rad", 0.0) if isinstance(line_property, dict) else 0.0)
            normal = _normalize_vector3((rebuilt or {}).get("z")) if isinstance(rebuilt, dict) else None
        if normal is None:
            normal = _normalize_vector3(_cross_vector3(u, (0.0, 0.0, 1.0)))
        if normal is None:
            normal = _normalize_vector3(_cross_vector3(u, (0.0, 1.0, 0.0)))
        if normal is None:
            return []
        rotated_normal = _rotate_vector_around_axis(normal, u, -math.pi / 2.0)
        normal = _normalize_vector3(rotated_normal) or normal
        title_key = str(title or "").strip().lower()
        family_key, sep, component_key = title_key.partition("-")
        family_key = family_key.strip()
        component_key = component_key.strip() if sep else ""
        if family_key in ("déplacements", "deplacements") and component_key in ("dz", "d"):
            normal = (-normal[0], -normal[1], -normal[2])

        scale_height = max(0.25, 0.15 * length)
        scale_height *= max(1e-6, float(getattr(self, "_linear_result_scale_factor", 1.0)))

        all_values = [float((entry or {}).get("value", 0.0)) for entry in series]
        max_abs = max(abs(v) for v in all_values)
        min_val = min(all_values)
        max_val = max(all_values)
        amplitude_scale = (scale_height / max_abs) if max_abs > 1e-12 else 0.0

        baseline_points = []
        diagram_points = []
        stems = []
        samples = []
        for entry in series:
            abscissa = max(0.0, min(length, float((entry or {}).get("abscissa", 0.0))))
            value = float((entry or {}).get("value", 0.0))
            base = (
                p1[0] + u[0] * abscissa,
                p1[1] + u[1] * abscissa,
                p1[2] + u[2] * abscissa,
            )
            tip = (
                base[0] + normal[0] * value * amplitude_scale,
                base[1] + normal[1] * value * amplitude_scale,
                base[2] + normal[2] * value * amplitude_scale,
            )
            baseline_points.append(base)
            diagram_points.append(tip)
            stems.append((base, tip, value))
            samples.append({"value": value, "abscissa": abscissa, "tip": tip})

        def build_polyline(points_list):
            if len(points_list) < 2:
                return None
            points = vtk.vtkPoints()
            cells = vtk.vtkCellArray()
            polyline = vtk.vtkPolyLine()
            polyline.GetPointIds().SetNumberOfIds(len(points_list))
            for i, pt in enumerate(points_list):
                pid = points.InsertNextPoint(*pt)
                polyline.GetPointIds().SetId(i, pid)
            cells.InsertNextCell(polyline)
            poly = vtk.vtkPolyData()
            poly.SetPoints(points)
            poly.SetLines(cells)
            return poly

        def build_colored_stems(segments_list):
            pts = vtk.vtkPoints()
            cells = vtk.vtkCellArray()
            colors = vtk.vtkUnsignedCharArray()
            colors.SetName("Colors")
            colors.SetNumberOfComponents(3)
            for start, end, value in segments_list:
                rgb = self._diagram_value_to_color(value, min_val, max_val)
                pid0 = pts.InsertNextPoint(*start)
                pid1 = pts.InsertNextPoint(*end)
                line = vtk.vtkLine()
                line.GetPointIds().SetId(0, pid0)
                line.GetPointIds().SetId(1, pid1)
                cells.InsertNextCell(line)
                r, g, b = int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
                colors.InsertNextTuple3(r, g, b)
            poly = vtk.vtkPolyData()
            poly.SetPoints(pts)
            poly.SetLines(cells)
            poly.GetCellData().SetScalars(colors)
            return poly

        def build_filled_diagram(base_pts, tip_pts, values):
            if len(base_pts) < 2:
                return None
            n = len(base_pts)
            pts = vtk.vtkPoints()
            colors = vtk.vtkUnsignedCharArray()
            colors.SetName("Colors")
            colors.SetNumberOfComponents(3)
            for i in range(n):
                pts.InsertNextPoint(*base_pts[i])
                rgb = self._diagram_value_to_color(values[i], min_val, max_val)
                colors.InsertNextTuple3(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            for i in range(n):
                pts.InsertNextPoint(*tip_pts[i])
                rgb = self._diagram_value_to_color(values[i], min_val, max_val)
                colors.InsertNextTuple3(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            cells = vtk.vtkCellArray()
            for i in range(n - 1):
                b0, b1 = i,     i + 1
                t0, t1 = n + i, n + i + 1
                tri1 = vtk.vtkTriangle()
                tri1.GetPointIds().SetId(0, b0)
                tri1.GetPointIds().SetId(1, t0)
                tri1.GetPointIds().SetId(2, t1)
                cells.InsertNextCell(tri1)
                tri2 = vtk.vtkTriangle()
                tri2.GetPointIds().SetId(0, b0)
                tri2.GetPointIds().SetId(1, t1)
                tri2.GetPointIds().SetId(2, b1)
                cells.InsertNextCell(tri2)
            poly = vtk.vtkPolyData()
            poly.SetPoints(pts)
            poly.SetPolys(cells)
            poly.GetPointData().SetScalars(colors)
            return poly

        def make_colored_polydata_actor(polydata, line_width=1.0, opacity=1.0, use_point_colors=False):
            if polydata is None or polydata.GetNumberOfCells() == 0:
                return None
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(polydata)
            if use_point_colors:
                mapper.SetScalarModeToUsePointData()
            else:
                mapper.SetScalarModeToUseCellData()
            mapper.SetColorModeToDirectScalars()
            mapper.ScalarVisibilityOn()
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.PickableOff()
            prop = actor.GetProperty()
            prop.SetOpacity(opacity)
            prop.SetLineWidth(line_width)
            return actor

        unit_str = str(unit or "").strip()

        def _format_diagram_label_value(text_value):
            try:
                value = float(text_value)
            except Exception:
                return str(text_value)
            dec = 3 if decimals is None else int(decimals)
            if dec >= 1 and abs(value) < 10.0 ** (-dec):
                formatted = "+0" if value >= 0.0 else "-0"
            else:
                formatted = f"{value:.{dec}f}"
            return f"{formatted} {unit_str}" if unit_str else formatted

        new_label_actors = []

        def add_billboard_label(text_value, point, color, offset_factor=0.06):
            if point is None:
                return None
            try:
                actor = vtkBillboardTextActor3D()
            except Exception:
                return None
            offset = max(0.03, scale_height * offset_factor)
            try:
                sign = 1.0 if float(text_value) >= 0.0 else -1.0
            except Exception:
                sign = 1.0
            pos = (
                float(point[0]) + normal[0] * offset * sign,
                float(point[1]) + normal[1] * offset * sign,
                float(point[2]) + normal[2] * offset * sign,
            )
            actor.SetInput(_format_diagram_label_value(text_value))
            actor.SetPosition(*pos)
            text_prop = actor.GetTextProperty()
            text_prop.SetFontSize(16)
            text_prop.BoldOn()
            is_dark_theme = tuple(_cfg.VTK_BG) == tuple(_cfg._DARK_VTK_BG)
            applied_color = (1.0, 1.0, 1.0) if is_dark_theme else color
            text_prop.SetColor(*applied_color)
            actor._diagram_original_color = tuple(color)
            actor._diagram_outward = (normal[0] * sign, normal[1] * sign, normal[2] * sign)
            actor._diagram_tangent = u
            self._orient_diagram_label(actor)
            actor.PickableOff()
            self.renderer.AddActor(actor)
            self._actors.append(actor)
            self._clip.apply_to_actor(actor)
            new_label_actors.append(actor)
            return actor

        new_actors = []
        values_list = [s["value"] for s in samples]

        fill_poly = build_filled_diagram(baseline_points, diagram_points, values_list)
        fill_actor = make_colored_polydata_actor(fill_poly, opacity=0.82, use_point_colors=True)
        if fill_actor is not None:
            fill_actor.GetProperty().SetRepresentationToSurface()
            fill_actor.GetProperty().LightingOff()
            new_actors.append(self._add_actor(fill_actor, role=None, pickable=False))

        stems_poly = build_colored_stems(stems)
        stems_actor = make_colored_polydata_actor(stems_poly, line_width=1.2)
        if stems_actor is not None:
            new_actors.append(self._add_actor(stems_actor, role=None, pickable=False))

        baseline_actor = self._make_wire_actor(build_polyline(baseline_points), (0.35, 0.35, 0.35), 1.5)
        if baseline_actor is not None:
            baseline_actor.PickableOff()
            new_actors.append(self._add_actor(baseline_actor, role=None, pickable=False))

        diagram_actor = self._make_wire_actor(build_polyline(diagram_points), (0.10, 0.10, 0.10), max(1.5, self.linear_line_width))
        if diagram_actor is not None:
            diagram_actor.PickableOff()
            new_actors.append(self._add_actor(diagram_actor, role=None, pickable=False))

        if samples:
            min_sample = min(samples, key=lambda item: float(item["value"]))
            max_sample = max(samples, key=lambda item: float(item["value"]))
            if abs(float(max_sample["value"]) - float(min_sample["value"])) <= 1e-12:
                label_actor = add_billboard_label(max_sample["value"], max_sample["tip"], (0.85, 0.0, 0.0))
                if label_actor is not None:
                    new_actors.append(label_actor)
            else:
                min_color = self._diagram_value_to_color(min_sample["value"], min_val, max_val)
                max_color = self._diagram_value_to_color(max_sample["value"], min_val, max_val)
                min_actor = add_billboard_label(min_sample["value"], min_sample["tip"], min_color)
                max_actor = add_billboard_label(max_sample["value"], max_sample["tip"], max_color)
                if min_actor is not None:
                    new_actors.append(min_actor)
                if max_actor is not None:
                    new_actors.append(max_actor)

        # Enregistrer les labels dans la liste officielle (pour apply_theme, etc.)
        self._diagram_label_actors.extend(new_label_actors)

        return [a for a in new_actors if a is not None]

    def set_linear_result_diagram(self, line_points, series, title: str = "", line_property: dict = None, unit: str = "", decimals=None):
        """Remplace le diagramme courant (clear + reconstruction d'un seul élément)."""
        self.clear_result_diagram()
        actors = self._build_linear_diagram_actors(line_points, series, title, line_property, unit=unit, decimals=decimals)
        self._diagram_overlay_actors = actors
        self.render_window.Render()

    def add_linear_result_diagram(self, line_points, series, title: str = "", line_property: dict = None, unit: str = "", decimals=None):
        """Ajoute un diagramme filaire SANS effacer les diagrammes existants.

        Utilisé pour la sélection multiple de filaires : chaque filaire est
        chargé séquentiellement et superposé dans la vue.
        Les acteurs sont ajoutés directement au renderer, puis enregistrés
        dans _diagram_overlay_actors pour que clear_result_diagram() les retire.
        """
        actors = self._build_linear_diagram_actors(line_points, series, title, line_property, unit=unit, decimals=decimals)
        self._diagram_overlay_actors.extend(actors)
        self.render_window.Render()

    def clear_selection(self):
        self._selected_item = None
        self._selected_items = []
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1
        self.selectionChanged.emit([])
        self._refresh_selection_overlay()

    def set_selection_style(self, selection_color, selection_line_width: float):
        self.selection_color = tuple(float(v) for v in selection_color)
        self.selection_line_width = max(0.1, float(selection_line_width))
        self._refresh_selection_overlay()

    def _select_item(self, role: str, index: int, additive: bool = False):
        """Sélectionne un élément. Si additive=True (Ctrl), ajoute/retire de la sélection."""
        if role == "anomaly":
            return self.select_anomaly(int(index))
        new_item = {"role": role, "index": int(index)}
        key = (role, int(index))
        if additive:
            existing_keys = [(item["role"], item["index"]) for item in self._selected_items]
            if key in existing_keys:
                # Retirer l'item de la sélection
                self._selected_items = [it for it in self._selected_items if (it["role"], it["index"]) != key]
            else:
                self._selected_items.append(new_item)
        else:
            self._selected_items = [new_item]
        # _selected_item = premier item pour compatibilité
        self._selected_item = self._selected_items[0] if self._selected_items else None
        self.selectionChanged.emit(list(self._selected_items))
        self._refresh_selection_overlay()
        return True

    def _cycle_selection(self, additive: bool = False):
        """Tab : passe a l'element suivant sous le curseur (Ctrl+Tab : ajoute a la selection)."""
        if self._window_select_mode or self._zoom_window_mode:
            return
        x, y = self.interactor.GetEventPosition()
        candidates = self._pick_selection_candidates(x, y)
        if not candidates:
            return
        candidate_keys = [(c["role"], int(c["index"])) for c in candidates]
        if not additive and candidate_keys == self._selection_candidate_keys:
            self._selection_cycle_index = (self._selection_cycle_index + 1) % len(candidates)
        else:
            self._selection_candidates = candidates
            self._selection_candidate_keys = candidate_keys
            self._selection_cycle_index = 0
        selected = candidates[self._selection_cycle_index]
        self._select_item(selected["role"], selected["index"], additive=additive)

    def _on_right_button_press(self, obj, event):
        if self._flight.active:
            self._flight.on_right_button_press()
            return
        if self._window_select_mode:
            self.set_window_select_mode(False)   # clic droit = annuler
            return
        if self._zoom_window_mode:
            self.set_zoom_window_mode(False)     # clic droit = annuler
            return
        self.vtk_widget.setFocus()
        self.contextMenuRequested.emit()

    def _on_right_button_release(self, obj, event):
        if self._flight.active:
            self._flight.on_right_button_release()

    def _on_left_button_press(self, obj, event):
        if self._clip.on_left_press(*self.interactor.GetEventPosition()):
            self.vtk_widget.setFocus()
            self.interactor.GetCommand(self._left_press_tag).SetAbortFlag(1)
            return
        if self._window_select_mode:
            self.vtk_widget.setFocus()
            x, y = self.interactor.GetEventPosition()
            self._left_press_pos = None         # neutralise _on_left_button_release
            if self._win_pt1 is None:
                self._win_pt1 = (x, y)          # point 1
                return
            p1 = self._win_pt1                  # point 2 -> selection + fin du mode
            additive = bool(self.interactor.GetControlKey())
            self._window_select_from_rect(p1, (x, y), additive)
            self.set_window_select_mode(False)
            return
        if self._zoom_window_mode:
            self.vtk_widget.setFocus()
            x, y = self.interactor.GetEventPosition()
            self._left_press_pos = None
            if self._zoom_win_pt1 is None:
                self._zoom_win_pt1 = (x, y)     # point 1
                return
            self._zoom_to_rect(self._zoom_win_pt1, (x, y))   # point 2 -> zoom + fin
            self.set_zoom_window_mode(False)
            return
        self.vtk_widget.setFocus()
        x, y = self.interactor.GetEventPosition()
        ctrl = bool(self.interactor.GetControlKey())
        self._left_press_pos = (x, y)
        self._left_press_ctrl = ctrl
        candidates = self._pick_selection_candidates(x, y)
        if candidates:
            self._selection_candidates = candidates
            self._selection_candidate_keys = [(c["role"], int(c["index"])) for c in candidates]
            self._selection_cycle_index = 0
            selected = candidates[0]
            self._select_item(selected["role"], selected["index"], additive=ctrl)
            return
        # Zone vide : ne pas déselectionner ici — attendre le release
        # pour distinguer clic simple (déselectionner) de glisser (orbite).
        # En mode Navigation, interactor_style (orbite) est detache de
        # l'interactor (GetInteractor() renvoie None) : l'appeler plante VTK
        # (deref C++ d'un pointeur nul). L'orbite n'a de toute facon aucun
        # sens pendant le vol, la camera etant deja pilotee par ce mode.
        if not self._flight.active:
            self.interactor_style.OnLeftButtonDown()

    def _on_left_button_release(self, obj, event):
        if self._clip.on_left_release():
            return
        if self._window_select_mode or self._zoom_window_mode:
            return
        x, y = self.interactor.GetEventPosition()
        press_pos = self._left_press_pos
        self._left_press_pos = None
        if press_pos is None:
            return
        # Vérifier que c'est un clic stationnaire (pas un glisser)
        dx = abs(x - press_pos[0])
        dy = abs(y - press_pos[1])
        if dx <= 3 and dy <= 3 and not self._left_press_ctrl:
            # Clic dans zone vide sans Ctrl et sans mouvement → déselectionner
            candidates = self._pick_selection_candidates(x, y)
            if not candidates:
                self.clear_selection()

    def _on_clip_mouse_move(self, obj, event):
        x, y = self.interactor.GetEventPosition()
        self._clip.on_mouse_move(x, y)
        hovering = self._clip.hover_key is not None
        if hovering != self._clip_hover_cursor:
            self._clip_hover_cursor = hovering
            if hovering:
                self.vtk_widget.setCursor(Qt.PointingHandCursor)
            else:
                self.vtk_widget.unsetCursor()

    def _on_key_press(self, obj, event):
        key = self.interactor.GetKeySym() if self.interactor is not None else ""
        if self._flight.active:
            self._flight.on_key_press(key)
            return
        if key in ("Escape", "escape"):
            if self._window_select_mode:
                self.set_window_select_mode(False)
                return
            if self._zoom_window_mode:
                self.set_zoom_window_mode(False)
                return
            self.clear_selection()
            return

    def _on_key_release(self, obj, event):
        if not self._flight.active:
            return
        key = self.interactor.GetKeySym() if self.interactor is not None else ""
        self._flight.on_key_release(key)

    def _ensure_plain_style(self):
        """Cree paresseusement le style d'interaction neutre partage par les
        modes selection-fenetre / zoom-fenetre / Navigation. L'observateur
        CharEvent no-op empeche vtkInteractorStyleUser d'executer ses
        raccourcis clavier VTK par defaut (w/s changent la representation
        des acteurs, q/e emettent ExitEvent), qui corrompraient le rendu."""
        if self._plain_style is None:
            self._plain_style = vtk.vtkInteractorStyleUser()
            self._plain_style.SetDefaultRenderer(self.renderer)
            self._plain_style.AddObserver("CharEvent", lambda o, e: None)
        return self._plain_style

    def set_window_select_mode(self, active: bool):
        """Active/desactive la selection par fenetre : clic point 1, deplacement
        (rectangle pointille), clic point 2 -> selection puis fin du mode.
        gauche->droite : entites entierement comprises.
        droite->gauche : entites comprises + intersectees."""
        active = bool(active)
        if active == self._window_select_mode:
            return
        if active and self._zoom_window_mode:
            self.set_zoom_window_mode(False)
        if active and self._flight.active:
            self.set_flight_mode(False)
        self._window_select_mode = active
        self._win_pt1 = None
        if active:
            self.interactor.SetInteractorStyle(self._ensure_plain_style())
            self.vtk_widget.setCursor(Qt.CrossCursor)
        else:
            self.interactor.SetInteractorStyle(self.interactor_style)
            self.vtk_widget.unsetCursor()
            self._hide_window_rect()
        self.windowSelectModeChanged.emit(active)

    def _on_flight_mouse_move(self, obj, event):
        if not self._flight.active:
            return
        self._flight.on_mouse_move()

    def _on_window_select_mouse_move(self, obj, event):
        if self._window_select_mode:
            pt1 = self._win_pt1
        elif self._zoom_window_mode:
            pt1 = self._zoom_win_pt1
        else:
            return
        if pt1 is None:
            return
        x, y = self.interactor.GetEventPosition()
        self._update_window_rect(pt1, (x, y))

    def set_zoom_window_mode(self, active: bool):
        """Active/desactive le zoom fenetre : clic point 1, deplacement (rectangle
        pointille), clic point 2 -> recadrage camera sur le rectangle puis fin
        du mode."""
        active = bool(active)
        if active == self._zoom_window_mode:
            return
        if active and self._window_select_mode:
            self.set_window_select_mode(False)
        if active and self._flight.active:
            self.set_flight_mode(False)
        self._zoom_window_mode = active
        self._zoom_win_pt1 = None
        if active:
            self.interactor.SetInteractorStyle(self._ensure_plain_style())
            self.vtk_widget.setCursor(Qt.CrossCursor)
        else:
            self.interactor.SetInteractorStyle(self.interactor_style)
            self.vtk_widget.unsetCursor()
            self._hide_window_rect()
        self.zoomWindowModeChanged.emit(active)

    def _zoom_to_rect(self, p0, p1):
        """Recadre la camera sur le rectangle ecran (p0, p1). Portage de la
        logique caméra de vtkInteractorStyleRubberBandZoom : translation pour
        amener le centre du rectangle au centre de la vue, puis facteur de zoom."""
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        w = x1 - x0
        h = y1 - y0
        if w < 3 and h < 3:
            return
        ren = self.renderer
        cam = ren.GetActiveCamera()
        if cam is None:
            return
        size = ren.GetSize()
        if not size or size[0] <= 0 or size[1] <= 0:
            return

        fp = cam.GetFocalPoint()
        pos = cam.GetPosition()
        ren.SetWorldPoint(fp[0], fp[1], fp[2], 1.0)
        ren.WorldToDisplay()
        depth = ren.GetDisplayPoint()[2]

        def _unproject(dx, dy):
            ren.SetDisplayPoint(float(dx), float(dy), depth)
            ren.DisplayToWorld()
            wx, wy, wz, ww = ren.GetWorldPoint()
            if ww != 0.0:
                wx, wy, wz = wx / ww, wy / ww, wz / ww
            return wx, wy, wz

        wr = _unproject((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        wc = _unproject(size[0] / 2.0, size[1] / 2.0)
        tr = (wr[0] - wc[0], wr[1] - wc[1], wr[2] - wc[2])
        cam.SetFocalPoint(fp[0] + tr[0], fp[1] + tr[1], fp[2] + tr[2])
        cam.SetPosition(pos[0] + tr[0], pos[1] + tr[1], pos[2] + tr[2])

        factor = size[0] / w if w > h else size[1] / h
        if cam.GetParallelProjection():
            cam.Zoom(factor)
        else:
            cam.Dolly(factor)
        ren.ResetCameraClippingRange()
        self.render_window.Render()
        self._update_view_overlay()

    def _ensure_window_rect_actor(self):
        if self._window_rect_actor is not None:
            return
        pts = vtk.vtkPoints()
        pts.SetNumberOfPoints(4)
        lines = vtk.vtkCellArray()
        lines.InsertNextCell(5)
        for i in (0, 1, 2, 3, 0):
            lines.InsertCellPoint(i)
        pd = vtk.vtkPolyData()
        pd.SetPoints(pts)
        pd.SetLines(lines)
        coord = vtk.vtkCoordinate()
        coord.SetCoordinateSystemToDisplay()
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(pd)
        mapper.SetTransformCoordinate(coord)
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.SetPickable(False)
        actor.SetVisibility(False)
        prop = actor.GetProperty()
        is_dark = tuple(_cfg.VTK_BG) == tuple(_cfg._DARK_VTK_BG)
        prop.SetColor(*((0.95, 0.95, 0.95) if is_dark else (0.10, 0.10, 0.10)))
        prop.SetLineWidth(1.0)
        # ponytail: pointilles via vtkProperty2D ; trait plein si le backend GL
        # ignore le stipple.
        prop.SetLineStipplePattern(0xF0F0)
        prop.SetLineStippleRepeatFactor(1)
        self._window_rect_pd = pd
        self._window_rect_actor = actor
        self.renderer.AddViewProp(actor)

    def _update_window_rect(self, p1, p2):
        self._ensure_window_rect_actor()
        (x1, y1), (x2, y2) = p1, p2
        pts = self._window_rect_pd.GetPoints()
        pts.SetPoint(0, x1, y1, 0.0)
        pts.SetPoint(1, x2, y1, 0.0)
        pts.SetPoint(2, x2, y2, 0.0)
        pts.SetPoint(3, x1, y2, 0.0)
        pts.Modified()
        self._window_rect_pd.Modified()
        self._window_rect_actor.SetVisibility(True)
        self.render_window.Render()

    def _hide_window_rect(self):
        if self._window_rect_actor is not None and self._window_rect_actor.GetVisibility():
            self._window_rect_actor.SetVisibility(False)
            self.render_window.Render()

    def _window_select_from_rect(self, p0, p1, additive):
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        crossing = p1[0] < p0[0]   # trace de droite a gauche => inclut les intersectees

        # Rectangle degenere (simple clic) -> picking ponctuel classique.
        if (x1 - x0) < 3 and (y1 - y0) < 3:
            cands = self._pick_selection_candidates(int(round(p1[0])), int(round(p1[1])))
            if cands:
                c = cands[0]
                self._select_item(c["role"], c["index"], additive=additive)
            elif not additive:
                self.clear_selection()
            self.windowSelectionDone.emit(list(self._selected_items))
            return

        cam = self.renderer.GetActiveCamera()
        if cam is None:
            return
        w, h = self.renderer.GetSize()
        m = cam.GetCompositeProjectionTransformMatrix(self.renderer.GetTiledAspectRatio(), -1.0, 1.0)

        def _proj(pt):
            o = m.MultiplyPoint((pt[0], pt[1], pt[2], 1.0))
            if abs(o[3]) < 1e-9:
                return None
            return ((o[0] / o[3] * 0.5 + 0.5) * w, (o[1] / o[3] * 0.5 + 0.5) * h)

        FACE_ROLES = ("planars", "load_areas", "support_planar")
        all_in = {}   # cle -> toutes les cellules vues jusqu'ici entierement dans le rectangle
        cross = {}    # cle -> au moins une cellule touchant le rectangle

        # ponytail: boucle python O(cellules) par selection-fenetre ; OK jusqu'a
        # ~100k cellules. Passer a vtk.util.numpy_support (projection vectorisee)
        # si le rendu du modele est plus lourd.
        for info in self._pickable_actors.values():
            actor = info["actor"]
            if actor is None or not actor.GetVisibility():
                continue
            role = info["role"]
            pd = self._get_actor_polydata(actor)
            if pd is None:
                continue
            arr = pd.GetCellData().GetArray(self.ELEMENT_INDEX_ARRAY)
            pts = pd.GetPoints()
            if arr is None or pts is None:
                continue
            for cid in range(pd.GetNumberOfCells()):
                key = (role, int(arr.GetTuple1(cid)))
                cell = pd.GetCell(cid)
                npc = cell.GetNumberOfPoints()
                if npc == 0:
                    continue
                world = self._clip.visible_part([pts.GetPoint(cell.GetPointId(k)) for k in range(npc)])
                npc = len(world)
                if npc == 0:
                    continue
                scr = []
                ok = True
                for k in range(npc):
                    sp = _proj(world[k])
                    if sp is None:
                        ok = False
                        break
                    scr.append(sp)
                if not ok:
                    all_in[key] = False
                    continue
                cell_in = all(x0 <= sx <= x1 and y0 <= sy <= y1 for sx, sy in scr)
                all_in[key] = all_in.get(key, True) and cell_in
                if cross.get(key):
                    continue
                if npc == 1:
                    if cell_in:
                        cross[key] = True
                    continue
                closed = npc >= 3 and role in FACE_ROLES
                n_edges = npc if closed else npc - 1
                for e in range(n_edges):
                    ax, ay = scr[e]
                    bx, by = scr[(e + 1) % npc]
                    if _seg_intersects_rect(ax, ay, bx, by, x0, y0, x1, y1):
                        cross[key] = True
                        break

        keys = [k for k, v in all_in.items() if v or (crossing and cross.get(k))]
        new_items = [{"role": r, "index": i} for (r, i) in sorted(keys)]
        if additive:
            have = {(it["role"], it["index"]) for it in self._selected_items}
            new_items = list(self._selected_items) + [
                it for it in new_items if (it["role"], it["index"]) not in have
            ]
        self._selected_items = new_items
        self._selected_item = self._selected_items[0] if self._selected_items else None
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1
        self.selectionChanged.emit(list(self._selected_items))
        self._refresh_selection_overlay()
        self.windowSelectionDone.emit(list(self._selected_items))

    def _selectable_element_keys(self):
        """Elements selectionnables : ceux des acteurs pickables visibles, hors
        elements entierement coupes par la boite de coupe."""
        keys = set()
        clip_active = self._clip.active
        for info in self._pickable_actors.values():
            actor = info["actor"]
            if actor is None or not actor.GetVisibility():
                continue
            pd = self._get_actor_polydata(actor)
            if pd is None:
                continue
            arr = pd.GetCellData().GetArray(self.ELEMENT_INDEX_ARRAY)
            pts = pd.GetPoints()
            if arr is None or pts is None:
                continue
            role = info["role"]
            for cid in range(pd.GetNumberOfCells()):
                key = (role, int(arr.GetTuple1(cid)))
                if key in keys:
                    continue
                if clip_active:
                    cell = pd.GetCell(cid)
                    world = [pts.GetPoint(cell.GetPointId(k)) for k in range(cell.GetNumberOfPoints())]
                    if not self._clip.visible_part(world):
                        continue
                keys.add(key)
        return keys

    def invert_selection(self):
        """Inverse la selection : sans selection ne fait rien (None) ; sinon
        l'ancienne selection est retiree et tous les autres elements
        selectionnables sont selectionnes. Retourne les nouveaux items."""
        if not self._selected_items:
            return None
        items = _invert_selection_items(self._selected_items, self._selectable_element_keys())
        self.set_selected_items(items)
        return items

    def get_selected_items(self) -> list:
        """Retourne la liste des items actuellement sélectionnés : [{"role", "index"}, ...]."""
        return list(self._selected_items)

    def set_selected_items(self, items: list):
        """Remplace la sélection courante par la liste d'items fournie : [{"role", "index"}, ...]."""
        valid = []
        for item in (items or []):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            index = int(item.get("index", -1))
            if role and index >= 0:
                valid.append({"role": role, "index": index})
        self._selected_items = valid
        self._selected_item = valid[0] if valid else None
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1
        self.selectionChanged.emit(list(self._selected_items))
        self._refresh_selection_overlay()

    # Delegues vers scene_light.py (extrait pour isoler ce sous-ensemble
    # autonome) : signatures et comportement inchanges pour les appelants
    # (main_window.py, tests/test_scene_light.py).
    scene_light_default_azimuth_elevation = staticmethod(_scene_light.default_azimuth_elevation)
    _position_to_azimuth_elevation = staticmethod(_scene_light.position_to_azimuth_elevation)
    _azimuth_elevation_to_position = staticmethod(_scene_light.azimuth_elevation_to_position)

    def set_scene_light(self, intensity: float, azimuth_deg: float, elevation_deg: float):
        if self.scene_light is None:
            return
        self.scene_light.SetIntensity(float(intensity))
        self.scene_light.SetPosition(*self._azimuth_elevation_to_position(azimuth_deg, elevation_deg))
        self.render_window.Render()

    def show_scene_light_gizmo(self, position):
        self._scene_light_gizmo.show(position)

    def hide_scene_light_gizmo(self):
        self._scene_light_gizmo.hide()

    def set_flight_mode(self, active: bool):
        """Active/desactive le mode Navigation (camera libre). Meme schema que
        set_window_select_mode/set_zoom_window_mode : drapeau d'etat + bascule
        vers un style d'interaction neutre pendant le mode. Logique complete
        dans flight_navigation.FlightController."""
        active = bool(active)
        if active == self._flight.active:
            return
        if active:
            self._flight.activate()
        else:
            self._flight.deactivate()
        self.flightModeChanged.emit(active)

    def _clippable_actors(self):
        actors = list(self._actors)
        mesh = self._mesh_actor
        if mesh is not None and mesh not in actors:
            actors.append(mesh)
        return actors

    def _clip_edge_sources(self):
        sources = []
        candidates = []
        if self._show_lines:
            candidates.append(self._profiles_actor if self._display_mode in _PROFILE_MODES else self._lines_actor)
        if self._show_planars:
            candidates.append(self._planar_faces_actor)
        if self._show_support_planar:
            candidates.append(self._support_planar_faces_actor)
        for actor in candidates:
            pd = self._get_actor_polydata(actor)
            if pd is not None:
                sources.append(pd)
        return sources

    def _clip_activation_bounds(self):
        if self._selected_items and self._selection_overlay_actors:
            union = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
            for actor in self._selection_overlay_actors:
                b = actor.GetBounds()
                if b is None or b[0] > b[1]:
                    continue
                for i in range(3):
                    union[2 * i] = min(union[2 * i], b[2 * i])
                    union[2 * i + 1] = max(union[2 * i + 1], b[2 * i + 1])
            if union[0] <= union[1]:
                return union
        return self._get_visible_bounds()

    def set_clip_box_active(self, active: bool):
        active = bool(active)
        if active == self._clip.active:
            return
        if active:
            self._clip.activate(self._clip_activation_bounds())
        else:
            self._clip.deactivate()
        self.clipBoxChanged.emit(self._clip.active)

    def is_clip_box_active(self) -> bool:
        return self._clip.active

    def set_clip_box_frame_visible(self, visible: bool):
        self._clip.set_frame_visible(visible)

    def set_clip_box_style(self, box_color, edge_color, edge_width=None):
        self._clip.set_style(box_color, edge_color, edge_width)

    def get_clip_box_edge_width(self) -> float:
        return self._clip.edge_width

    def get_clip_box_style(self):
        return self._clip.box_color, self._clip.edge_color

    def set_clip_box_margin(self, pct: float):
        self._clip.margin_pct = max(0.0, float(pct))

    def get_clip_box_margin(self) -> float:
        return self._clip.margin_pct

    def set_minimap_visible(self, visible: bool):
        self._minimap.set_visible(visible)

    def set_minimap_corner(self, corner: str):
        self._minimap.set_corner(corner)

    def set_minimap_size(self, size: str):
        self._minimap.set_size(size)

    def get_display_counts(self):
        return {
            "lines": self.lines_count,
            "planars": self.planars_count,
            "load_areas": self.load_areas_count,
            "support_punctual": self.support_punctual_count,
            "support_linear": self.support_linear_count,
            "support_planar": self.support_planar_count,
            "punctual_loads": self.punctual_load_count,
            "linear_loads": self.linear_load_count,
            "planar_loads": self.planar_load_count,
        }

    # Valeurs par defaut re-exposees depuis scene_light.py (main_window.py les
    # lit via self.viewer.SCENE_LIGHT_DEFAULT_*).
    SCENE_LIGHT_DEFAULT_POSITION = _scene_light.DEFAULT_POSITION
    SCENE_LIGHT_DEFAULT_INTENSITY = _scene_light.DEFAULT_INTENSITY

    def _build_scene_base(self):
        light = vtk.vtkLight()
        light.SetLightTypeToSceneLight()
        light.SetFocalPoint(0, 0, 0)
        self.scene_light = light
        self.renderer.AddLight(light)
        self._scene_light_gizmo = _scene_light.SceneLightGizmo(self.renderer, self.render_window)
        az, el = self.scene_light_default_azimuth_elevation()
        self.set_scene_light(self.SCENE_LIGHT_DEFAULT_INTENSITY, az, el)
        self._setup_corner_axes()
        self._setup_view_overlay()
        self._flight.setup_overlay()
        self._minimap.setup()

    def _setup_view_overlay(self):
        actor = vtk.vtkTextActor()
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        actor.GetPositionCoordinate().SetValue(0.012, 0.985)
        actor.SetTextScaleModeToNone()
        actor.SetPickable(False)
        actor.SetVisibility(False)
        tp = actor.GetTextProperty()
        tp.SetFontFamilyToArial()
        tp.SetFontSize(12)
        tp.SetJustificationToLeft()
        tp.SetVerticalJustificationToTop()
        tp.SetLineSpacing(1.2)
        tp.ShadowOff()
        self._view_overlay_actor = actor
        self.renderer.AddViewProp(actor)
        self._apply_view_overlay_theme()

    def _apply_view_overlay_theme(self):
        is_dark = tuple(_cfg.VTK_BG) == tuple(_cfg._DARK_VTK_BG)
        color = (0.92, 0.94, 0.98) if is_dark else (0.12, 0.16, 0.22)
        actor = getattr(self, "_view_overlay_actor", None)
        if actor is not None:
            actor.GetTextProperty().SetColor(*color)
        self._flight.apply_overlay_theme(color)
        self._minimap.apply_theme(color)

    def _current_view_label(self) -> str:
        cam = self.renderer.GetActiveCamera() if self.renderer is not None else None
        if cam is None:
            return _cfg.tr_ui("view_label_user")
        dop = cam.GetDirectionOfProjection()
        norm = math.sqrt(dop[0] * dop[0] + dop[1] * dop[1] + dop[2] * dop[2])
        if norm < 1e-9:
            return _cfg.tr_ui("view_label_user")
        d = (dop[0] / norm, dop[1] / norm, dop[2] / norm)
        tol = 1.0e-3
        named = (
            ((0.0, 1.0, 0.0), "view_label_front"),
            ((0.0, -1.0, 0.0), "view_label_back"),
            ((1.0, 0.0, 0.0), "view_label_left"),
            ((-1.0, 0.0, 0.0), "view_label_right"),
            ((0.0, 0.0, -1.0), "view_label_top"),
            ((0.0, 0.0, 1.0), "view_label_bottom"),
        )
        for axis, key in named:
            if d[0] * axis[0] + d[1] * axis[1] + d[2] * axis[2] >= 1.0 - tol:
                return _cfg.tr_ui(key)
        iso = 1.0 / math.sqrt(3.0)
        if d[0] * (-iso) + d[1] * iso + d[2] * (-iso) >= 1.0 - tol:
            return _cfg.tr_ui("view_label_iso")
        return _cfg.tr_ui("view_label_user")

    def _update_view_overlay(self, display_x=None, display_y=None, render: bool = True):
        actor = getattr(self, "_view_overlay_actor", None)
        if actor is None:
            return

        if self._flight.active:
            actor.SetInput(_cfg.tr_ui("flight_mode_overlay"))
            if not actor.GetVisibility():
                actor.SetVisibility(True)
            if render and self.render_window is not None:
                self.render_window.Render()
            return

        if not self._has_model:
            if actor.GetVisibility():
                actor.SetVisibility(False)
                if render and self.render_window is not None:
                    self.render_window.Render()
            return

        if display_x is not None and display_y is not None and self.renderer is not None:
            picker = vtk.vtkWorldPointPicker()
            picker.Pick(float(display_x), float(display_y), 0.0, self.renderer)
            wx, wy, wz = picker.GetPickPosition()
            _n = du.decimals("length")
            _u = du.unit("length")
            self._overlay_mouse_world_txt = (
                f"X : {du.conv(wx, 'length'):.{_n}f}   "
                f"Y : {du.conv(wy, 'length'):.{_n}f}   "
                f"Z : {du.conv(wz, 'length'):.{_n}f} {_u}"
            )

        actor.SetInput(f"{self._current_view_label()}\n{self._overlay_mouse_world_txt}")
        if not actor.GetVisibility():
            actor.SetVisibility(True)
        if render and self.render_window is not None:
            self.render_window.Render()

    def _on_overlay_mouse_move(self, obj, event):
        if not self._has_model or self.interactor is None:
            return
        x, y = self.interactor.GetEventPosition()
        self._update_view_overlay(x, y)

    def _setup_corner_axes(self):
        axes = vtk.vtkAxesActor()
        axes.SetShaftTypeToLine()
        axes.SetTotalLength(1.0, 1.0, 1.0)
        axes.SetCylinderRadius(0.03)
        axes.SetConeRadius(0.10)
        axes.SetSphereRadius(0.12)
        axes.SetXAxisLabelText("X")
        axes.SetYAxisLabelText("Y")
        axes.SetZAxisLabelText("Z")
        axes.GetXAxisCaptionActor2D().SetWidth(0.10)
        axes.GetXAxisCaptionActor2D().SetHeight(0.10)
        axes.GetYAxisCaptionActor2D().SetWidth(0.10)
        axes.GetYAxisCaptionActor2D().SetHeight(0.10)
        axes.GetZAxisCaptionActor2D().SetWidth(0.10)
        axes.GetZAxisCaptionActor2D().SetHeight(0.10)

        widget = vtk.vtkOrientationMarkerWidget()
        widget.SetOrientationMarker(axes)
        widget.SetInteractor(self.interactor)
        widget.SetViewport(*self._ORIENTATION_WIDGET_VIEWPORT_BOTTOM_LEFT)
        widget.SetEnabled(1)
        widget.InteractiveOff()
        self.orientation_widget = widget

    _ORIENTATION_WIDGET_VIEWPORT_BOTTOM_LEFT = (0.02, 0.02, 0.12, 0.12)
    _ORIENTATION_WIDGET_VIEWPORT_BOTTOM_RIGHT = (0.88, 0.02, 0.98, 0.12)

    def _sync_orientation_widget_corner(self):
        """Le trieder d'axes passe dans le coin oppose quand la minicarte
        occupe son coin habituel (bas-gauche), pour eviter qu'ils se
        superposent."""
        if self.orientation_widget is None:
            return
        if self._minimap.visible and self._minimap.corner == "bottom_left":
            self.orientation_widget.SetViewport(*self._ORIENTATION_WIDGET_VIEWPORT_BOTTOM_RIGHT)
        else:
            self.orientation_widget.SetViewport(*self._ORIENTATION_WIDGET_VIEWPORT_BOTTOM_LEFT)

    def clear_scene(self):
        if self._clip.active:
            self._clip.deactivate()
            self.clipBoxChanged.emit(False)
        self._has_model = False
        self._update_view_overlay(render=False)
        self._minimap.clear_geometry()
        self.lines_count = 0
        self.planars_count = 0
        self.load_areas_count = 0
        self.support_punctual_count = 0
        self.support_linear_count = 0
        self.support_planar_count = 0

        for actor in list(self._actors):
            self.renderer.RemoveActor(actor)
        self._actors = []
        self._pickable_actors = {}
        self._selection_overlay_actors = []
        self._diagram_overlay_actors = []
        self._selected_item = None
        self._selected_items = []
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1

        self._lines_actor = None
        self._profiles_actor = None
        self._profiles_base_pd = None
        self._profiles_base_colors = None
        self._planar_actor = None
        self._planar_faces_actor = None
        self._planar_edges_actor = None
        self._openings_actor = None
        self._load_areas_actor = None
        self._load_areas_faces_actor = None
        self._support_punctual_actor = None
        self._support_linear_actor = None
        self._support_planar_actor = None
        self._support_planar_faces_actor = None
        self._support_planar_centroid_actor = None
        self._support_punctual_points = []
        self._support_punctual_indexes = None
        self._punctual_load_actors = []
        self._punctual_load_data = []
        self.punctual_load_count = 0
        self._linear_load_actors = []
        self._linear_load_data = []
        self.linear_load_count = 0
        self._planar_load_actors = []
        self._planar_load_data = []
        self.planar_load_count = 0
        self._model_data = {
            "lines": [],
            "line_properties": [],
            "planars": [],
            "planar_eids": [],
            "planar_properties": [],
            "load_areas": [],
            "punctual_supports": [],
            "linear_supports": [],
            "planar_supports": [],
        }
        self._filter_section_names = None
        self._filter_thickness_names = None
        self._filter_material_names = None
        self._isolated_selection = []
        self._hidden_items = set()
        self._anomaly_overlay.set_isolation(None)
        self._apply_visibility_state()

    def focus_bounds(self, bounds):
        """Cadre la camera sur une boite (xmin, xmax, ymin, ymax, zmin, zmax)
        sans changer sa direction de visee."""
        model = self._get_visible_bounds()
        if model is not None:
            # VTK place le plan proche a ~1 % du plan lointain (taille du modele) :
            # une boite trop petite mettrait la camera en deca et couperait la vue.
            diag = math.sqrt(sum((model[2 * i + 1] - model[2 * i]) ** 2 for i in range(3)))
            bounds = _clip_box.expand_bounds(bounds, 0.0, min_size=0.06 * diag)
        self.renderer.ResetCamera(*bounds)
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()
        self._update_view_overlay()

    def zoom_to_selection(self):
        union = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
        for actor in self._selection_overlay_actors:
            b = actor.GetBounds()
            if b is None or b[0] > b[1]:
                continue
            for i in range(3):
                union[2 * i] = min(union[2 * i], b[2 * i])
                union[2 * i + 1] = max(union[2 * i + 1], b[2 * i + 1])
        if union[0] > union[1]:
            return
        self.focus_bounds(union)

    # --- Controle modele : anomalies ---
    def set_anomalies(self, anomalies, thresholds):
        self._anomaly_overlay.set_anomalies(anomalies, thresholds)
        self._active_anomaly = None
        self.render_window.Render()

    def clear_anomalies(self):
        self._anomaly_overlay.clear()
        self._active_anomaly = None
        self.render_window.Render()

    def set_anomalies_visible(self, visible: bool):
        self._anomaly_overlay.set_visible(visible)
        self.render_window.Render()

    def anomalies_visible(self) -> bool:
        return self._anomaly_overlay.is_visible()

    def select_anomaly(self, index: int):
        """Selectionne une anomalie : ses elements entrent dans la selection
        ordinaire et son symbole est renforce."""
        anomaly = self._anomaly_overlay.anomaly(index)
        if anomaly is None:
            return False
        items = [{"role": role, "index": int(i)} for role, i in anomaly.items]
        self._active_anomaly = index
        self._anomaly_overlay.set_active(index)
        self._selected_items = items
        self._selected_item = items[0] if items else None
        self._anomaly_emit = True
        try:
            self.selectionChanged.emit(list(items))
        finally:
            self._anomaly_emit = False
        self._refresh_selection_overlay()
        return True

    def active_anomaly_index(self):
        return self._active_anomaly

    def consume_anomaly_selection(self):
        """A appeler en tete du gestionnaire selectionChanged. Renvoie l'index
        de l'anomalie si l'evenement vient de select_anomaly ; sinon oublie
        l'anomalie active (symbole remis a l'etat normal) et renvoie None."""
        if self._anomaly_emit:
            return self._active_anomaly
        if self._active_anomaly is not None:
            self._active_anomaly = None
            self._anomaly_overlay.set_active(None)
            self.render_window.Render()
        return None

    def focus_anomaly(self, index: int):
        bounds = self._anomaly_overlay.bounds(index)
        if bounds is not None:
            self.focus_bounds(bounds)

    def fit_view(self):
        cam = self.renderer.GetActiveCamera()
        direction = cam.GetDirectionOfProjection()
        view_up = cam.GetViewUp()
        try:
            dot = abs(
                float(direction[0]) * float(view_up[0])
                + float(direction[1]) * float(view_up[1])
                + float(direction[2]) * float(view_up[2])
            )
        except Exception:
            dot = 0.0
        if dot > 0.999:
            if abs(float(direction[2])) > 0.9:
                cam.SetViewUp(0.0, 1.0, 0.0)
            else:
                cam.SetViewUp(0.0, 0.0, 1.0)
        cam.OrthogonalizeViewUp()
        self._reset_camera_to_framing()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()
        self._update_view_overlay()

    def _get_visible_bounds(self):
        bounds = [0.0] * 6
        with self._anomaly_overlay.suspended():
            self.renderer.ComputeVisiblePropBounds(bounds)
        if bounds[0] > bounds[1] or bounds[2] > bounds[3] or bounds[4] > bounds[5]:
            return None
        if not all(math.isfinite(v) for v in bounds):
            return None
        return bounds

    def _framing_bounds(self):
        return list(self._clip.box) if self._clip.active else self._get_visible_bounds()

    def _reset_camera_to_framing(self):
        bounds = self._framing_bounds()
        if bounds is None:
            self.renderer.ResetCamera()
        else:
            self.renderer.ResetCamera(*bounds)

    def set_projection_mode(self, mode: str):
        normalized = str(mode or DEFAULT_VIEW_PROJECTION).strip().lower()
        if normalized not in ("perspective", "orthogonal"):
            normalized = DEFAULT_VIEW_PROJECTION
        self._projection_mode = normalized
        camera = self.renderer.GetActiveCamera() if self.renderer is not None else None
        if camera is not None:
            camera.SetParallelProjection(normalized == "orthogonal")
            self.renderer.ResetCameraClippingRange()
            if self.render_window is not None:
                self.render_window.Render()

    def get_projection_mode(self) -> str:
        return str(getattr(self, "_projection_mode", DEFAULT_VIEW_PROJECTION) or DEFAULT_VIEW_PROJECTION)

    def set_isometric_view(self):
        bounds = self._framing_bounds()
        if bounds is None:
            cx, cy, cz = 0.0, 0.0, 0.0
            radius = 10.0
        else:
            xmin, xmax, ymin, ymax, zmin, zmax = bounds
            cx = 0.5 * (xmin + xmax)
            cy = 0.5 * (ymin + ymax)
            cz = 0.5 * (zmin + zmax)
            dx = xmax - xmin
            dy = ymax - ymin
            dz = zmax - zmin
            diag = math.sqrt(dx * dx + dy * dy + dz * dz)
            radius = max(diag, 1.0)

        cam = self.renderer.GetActiveCamera()
        cam.SetFocalPoint(cx, cy, cz)
        cam.SetPosition(cx + radius, cy - radius, cz + radius)
        cam.SetViewUp(0.0, 0.0, 1.0)
        cam.OrthogonalizeViewUp()
        self._reset_camera_to_framing()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()
        self._update_view_overlay()

    def _set_axis_view(self, direction, up=(0.0, 0.0, 1.0)):
        bounds = self._framing_bounds()
        if bounds is None:
            cx, cy, cz = 0.0, 0.0, 0.0
            radius = 10.0
        else:
            xmin, xmax, ymin, ymax, zmin, zmax = bounds
            cx = 0.5 * (xmin + xmax)
            cy = 0.5 * (ymin + ymax)
            cz = 0.5 * (zmin + zmax)
            dx = xmax - xmin
            dy = ymax - ymin
            dz = zmax - zmin
            diag = math.sqrt(dx * dx + dy * dy + dz * dz)
            radius = max(diag, 1.0)

        cam = self.renderer.GetActiveCamera()
        cam.SetFocalPoint(cx, cy, cz)
        cam.SetPosition(
            cx + direction[0] * radius,
            cy + direction[1] * radius,
            cz + direction[2] * radius,
        )
        cam.SetViewUp(*up)
        cam.OrthogonalizeViewUp()
        self._reset_camera_to_framing()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()
        self._update_view_overlay()

    def set_front_view(self):
        self._set_axis_view((0.0, -1.0, 0.0), up=(0.0, 0.0, 1.0))

    def set_back_view(self):
        self._set_axis_view((0.0, 1.0, 0.0), up=(0.0, 0.0, 1.0))

    def set_left_view(self):
        self._set_axis_view((-1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0))

    def set_right_view(self):
        self._set_axis_view((1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0))

    def set_top_view(self):
        self._set_axis_view((0.0, 0.0, 1.0), up=(0.0, 1.0, 0.0))

    def set_bottom_view(self):
        self._set_axis_view((0.0, 0.0, -1.0), up=(0.0, -1.0, 0.0))

    def _transparency_factor(self):
        p = max(0, min(100, int(self._transparency_percent)))
        return max(0.0, min(1.0, 1.0 - (p / 100.0)))

    def set_faces_transparency(self, percent: int):
        self._transparency_percent = max(0, min(100, int(percent)))
        self._apply_face_opacity_state()
        self.render_window.Render()

    def set_profiles_transparency(self, percent: int):
        """Opacite des solides de profils, appliquee seulement en mode
        Profilés + Faces cachées."""
        self._profiles_transparency_percent = max(0, min(100, int(percent)))
        self._apply_face_opacity_state()
        self.render_window.Render()

    def _apply_face_opacity_state(self):
        if self._display_mode == "profiles_wire":
            # faces invisibles mais toujours dans la liste de picking (acteur visible)
            planar_opacity = _WIRE3D_FACE_OPACITY
            load_area_opacity = _WIRE3D_FACE_OPACITY
            support_planar_opacity = _WIRE3D_FACE_OPACITY
            selection_face_opacity = 0.40
        elif self._display_mode in ("full", "profiles_full"):
            planar_opacity = 1.0
            load_area_opacity = 1.0
            support_planar_opacity = 1.0
            selection_face_opacity = 0.40
        else:
            factor = self._transparency_factor()
            planar_opacity = self.planar_faces_base_opacity * factor
            load_area_opacity = self.load_areas_faces_base_opacity * factor
            support_planar_opacity = self.support_planar_faces_base_opacity * factor
            selection_face_opacity = max(0.18, 0.30 * factor)

        if self._planar_faces_actor:
            self._planar_faces_actor.GetProperty().SetOpacity(planar_opacity)
        if self._load_areas_faces_actor:
            self._load_areas_faces_actor.GetProperty().SetOpacity(load_area_opacity)
        if self._support_planar_faces_actor:
            self._support_planar_faces_actor.GetProperty().SetOpacity(support_planar_opacity)
        if self._profiles_actor:
            # solides des filaires : opacite pilotee par le slider dedie
            # "Transparence profilés", uniquement en "Profilés + Faces cachées" ;
            # opaques en "Profilés + Rendu plein".
            if self._display_mode == "profiles_hidden":
                p = max(0, min(100, int(self._profiles_transparency_percent)))
                self._profiles_actor.GetProperty().SetOpacity(1.0 - p / 100.0)
            else:
                self._profiles_actor.GetProperty().SetOpacity(1.0)
        for actor in self._selection_overlay_actors:
            if actor.GetProperty() is not None and actor.GetProperty().GetOpacity() < 1.0:
                actor.GetProperty().SetOpacity(selection_face_opacity)

    def set_colors(
        self,
        linear_color,
        planar_color,
        opening_color,
        load_area_color,
        support_punctual_color,
        support_linear_color,
        support_planar_color
    ):
        self.linear_color = tuple(float(v) for v in linear_color)
        self.planar_color = tuple(float(v) for v in planar_color)
        self.opening_color = tuple(float(v) for v in opening_color)
        self.load_area_color = tuple(float(v) for v in load_area_color)
        self.support_punctual_color = tuple(float(v) for v in support_punctual_color)
        self.support_linear_color = tuple(float(v) for v in support_linear_color)
        self.support_planar_color = tuple(float(v) for v in support_planar_color)

        if self._lines_actor:
            self._lines_actor.GetProperty().SetColor(*self.linear_color)
        if self._planar_actor:
            self._planar_actor.GetProperty().SetColor(*self.planar_color)
        if self._planar_faces_actor:
            self._planar_faces_actor.GetProperty().SetColor(*self.planar_color)
        if self._openings_actor:
            self._openings_actor.GetProperty().SetColor(*self.opening_color)
        if self._load_areas_actor:
            self._load_areas_actor.GetProperty().SetColor(*self.load_area_color)
        if self._load_areas_faces_actor:
            self._load_areas_faces_actor.GetProperty().SetColor(*self.load_area_color)
        if self._support_punctual_actor:
            self._support_punctual_actor.GetProperty().SetColor(*self.support_punctual_color)
        if self._support_linear_actor:
            self._support_linear_actor.GetProperty().SetColor(*self.support_linear_color)
        if self._support_planar_actor:
            self._support_planar_actor.GetProperty().SetColor(*self.support_planar_color)
        if self._support_planar_faces_actor:
            self._support_planar_faces_actor.GetProperty().SetColor(*self.support_planar_color)
        if self._support_planar_centroid_actor:
            self._support_planar_centroid_actor.GetProperty().SetColor(*self.selection_color)

        self._refresh_selection_overlay()

    def _apply_visibility_state(self):
        mode = self._display_mode
        profile_mode = mode in _PROFILE_MODES
        # profiles_hidden se comporte comme hidden_faces, profiles_full comme full
        show_faces = mode in ("hidden_faces", "wire_hidden", "full") or profile_mode
        show_planar_wire = mode in ("wireframe", "wire_hidden")
        show_openings = mode in ("wireframe", "hidden_faces", "wire_hidden")
        wire3d = mode == "profiles_wire"
        show_aux_wire = show_planar_wire or wire3d
        self.renderer.SetUseHiddenLineRemoval(0 if mode in ("profiles_full", "profiles_wire") else (1 if show_faces else 0))

        if self._lines_actor:
            self._lines_actor.SetVisibility(1 if (self._show_lines and not profile_mode) else 0)
        if self._profiles_actor:
            self._profiles_actor.SetVisibility(1 if (self._show_lines and profile_mode) else 0)
            # arretes visibles en rendu plein, pas en faces cachees
            self._profiles_actor.GetProperty().SetEdgeVisibility(1 if mode == "profiles_full" else 0)
            prop = self._profiles_actor.GetProperty()
            if wire3d:
                prop.SetRepresentationToWireframe()
                prop.LightingOff()
            else:
                prop.SetRepresentationToSurface()
                prop.LightingOn()
            prop.SetColor(*(_WIRE3D_COLOR if wire3d else self.linear_color))
            if wire3d != self._profiles_wire_applied:
                self._profiles_wire_applied = wire3d
                self._apply_profiles_selection_colors()
        if self._planar_actor:
            self._planar_actor.SetVisibility(1 if (self._show_planars and show_planar_wire) else 0)
        if self._planar_faces_actor:
            self._planar_faces_actor.SetVisibility(1 if (self._show_planars and show_faces) else 0)
        if self._planar_edges_actor:
            self._planar_edges_actor.SetVisibility(1 if (self._show_planars and mode in ("profiles_full", "profiles_wire")) else 0)
            self._planar_edges_actor.GetProperty().SetColor(*(_WIRE3D_COLOR if wire3d else (0.0, 0.0, 0.0)))
        if self._openings_actor:
            self._openings_actor.SetVisibility(1 if (self._show_planars and show_openings) else 0)
        if self._load_areas_actor:
            self._load_areas_actor.SetVisibility(1 if (self._show_load_areas and show_aux_wire) else 0)
        if self._load_areas_faces_actor:
            self._load_areas_faces_actor.SetVisibility(1 if (self._show_load_areas and show_faces) else 0)
        if self._support_punctual_actor:
            self._support_punctual_actor.SetVisibility(1 if self._show_support_punctual else 0)
        if self._support_linear_actor:
            self._support_linear_actor.SetVisibility(1 if self._show_support_linear else 0)
        if self._support_planar_actor:
            self._support_planar_actor.SetVisibility(1 if (self._show_support_planar and show_aux_wire) else 0)
        if self._support_planar_faces_actor:
            self._support_planar_faces_actor.SetVisibility(1 if (self._show_support_planar and show_faces) else 0)
        if self._support_planar_centroid_actor:
            self._support_planar_centroid_actor.SetVisibility(1 if self._show_support_planar else 0)

        for actor in self._selection_overlay_actors:
            opacity = actor.GetProperty().GetOpacity() if actor.GetProperty() is not None else 1.0
            face_like = opacity < 1.0
            role = self._selected_item["role"] if self._selected_item else ""
            actor.SetVisibility(1 if self._selected_role_visible(role, face=face_like) else 0)
        self._clip.refresh_edges()

        if self._mesh_actor:
            self._mesh_actor.SetVisibility(1 if self._show_mesh else 0)

        self._apply_face_opacity_state()
        self.render_window.Render()

    def _set_visible_flag(self, attr: str, visible: bool):
        """Helper commun : met a jour un attribut de visibilite et applique l'etat."""
        setattr(self, attr, visible)
        self._apply_visibility_state()

    def _sync_minimap_visibility(self):
        self._minimap.apply_visibility(
            self._show_lines, self._show_planars,
            self._show_support_punctual, self._show_support_linear, self._show_support_planar,
        )

    def set_show_lines(self, visible: bool):
        self._set_visible_flag("_show_lines", visible)
        self._sync_minimap_visibility()

    def set_show_planars(self, visible: bool):
        self._set_visible_flag("_show_planars", visible)
        self._sync_minimap_visibility()

    def set_show_load_areas(self, visible: bool):
        self._set_visible_flag("_show_load_areas", visible)

    def set_show_support_punctual(self, visible: bool):
        self._set_visible_flag("_show_support_punctual", visible)
        self._sync_minimap_visibility()

    def set_show_support_linear(self, visible: bool):
        self._set_visible_flag("_show_support_linear", visible)
        self._sync_minimap_visibility()

    def set_show_support_planar(self, visible: bool):
        self._set_visible_flag("_show_support_planar", visible)
        self._sync_minimap_visibility()

    def set_show_marker(self, visible: bool):
        self._show_marker = visible
        if self.orientation_widget:
            if visible:
                self.orientation_widget.SetEnabled(1)
                self.orientation_widget.InteractiveOff()
            else:
                self.orientation_widget.SetEnabled(0)
        self.render_window.Render()

    def set_show_mesh(self, visible: bool):
        self._show_mesh = visible
        self._apply_visibility_state()

    def set_mesh_style(self, color, line_width: float):
        self.mesh_color = tuple(float(v) for v in color)
        self.mesh_line_width = max(0.1, float(line_width))
        if self._mesh_actor:
            self._mesh_actor.GetProperty().SetColor(*self.mesh_color)
            self._mesh_actor.GetProperty().SetLineWidth(self.mesh_line_width)
            self.render_window.Render()

    def load_mesh(self, nodes, connectivity):
        """Construit l'acteur de maillage FEM à partir des noeuds et de la connectivité.

        Args:
            nodes: liste de (x, y, z) — positions des noeuds.
            connectivity: liste de listes d'indices de noeuds.
                Les indices peuvent être base-0 ou base-1 (convention FEM AD) ;
                la détection est automatique (si le max dépasse len(nodes)-1
                on suppose base-1 et on soustrait 1).
        """
        if self._mesh_actor is not None:
            self.renderer.RemoveActor(self._mesh_actor)
            self._mesh_actor = None

        if not nodes or not connectivity:
            self.render_window.Render()
            return

        n_pts = len(nodes)

        # Détection base-0 vs base-1 : si au moins un indice >= n_pts, c'est base-1
        max_idx = max((idx for face in connectivity for idx in face), default=0)
        offset = 1 if max_idx >= n_pts else 0

        pts = vtk.vtkPoints()
        for x, y, z in nodes:
            pts.InsertNextPoint(float(x), float(y), float(z))

        cells = vtk.vtkCellArray()
        valid_faces = 0
        for face in connectivity:
            adjusted = [int(idx) - offset for idx in face]
            # Écarte les faces avec des indices hors limites
            if any(i < 0 or i >= n_pts for i in adjusted):
                continue
            n = len(adjusted)
            if n == 3:
                tri = vtk.vtkTriangle()
                for i, idx in enumerate(adjusted):
                    tri.GetPointIds().SetId(i, idx)
                cells.InsertNextCell(tri)
            elif n == 4:
                quad = vtk.vtkQuad()
                for i, idx in enumerate(adjusted):
                    quad.GetPointIds().SetId(i, idx)
                cells.InsertNextCell(quad)
            else:
                poly = vtk.vtkPolygon()
                poly.GetPointIds().SetNumberOfIds(n)
                for i, idx in enumerate(adjusted):
                    poly.GetPointIds().SetId(i, idx)
                cells.InsertNextCell(poly)
            valid_faces += 1

        if valid_faces == 0:
            self.render_window.Render()
            return

        pd = vtk.vtkPolyData()
        pd.SetPoints(pts)
        pd.SetPolys(cells)

        edges = vtk.vtkExtractEdges()
        edges.SetInputData(pd)
        edges.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*self.mesh_color)
        actor.GetProperty().SetLineWidth(self.mesh_line_width)
        actor.SetVisibility(1 if self._show_mesh else 0)

        self._mesh_actor = actor
        self.renderer.AddActor(actor)
        self._clip.apply_to_actor(actor)
        self.render_window.Render()

    def reset_display_mode_default(self):
        """Repasse au mode par defaut (wire_hidden) SANS reconstruire la
        geometrie. A appeler avant le chargement d'un nouveau modele pour que
        le rebuild suivant ne construise pas inutilement les solides profils."""
        self._display_mode = "wire_hidden"
        if self._profiles_actor is not None:
            self._remove_actor(self._profiles_actor)
            self._profiles_actor = None
        self._profiles_base_pd = None
        self._profiles_base_colors = None
        self._apply_visibility_state()

    def set_display_mode(self, mode: str):
        if mode not in _ALL_DISPLAY_MODES:
            mode = "wireframe"
        # (Re)construire ou retirer _profiles_actor uniquement si on franchit la
        # frontiere des modes profils ; sinon un simple refresh de visibilite.
        crossed = (self._display_mode in _PROFILE_MODES) != (mode in _PROFILE_MODES)
        self._display_mode = mode
        if crossed:
            self._rebuild_filtered_structural_actors()
        else:
            self._apply_visibility_state()

    def apply_display_state(
        self,
        show_lines: bool,
        show_planars: bool,
        show_load_areas: bool,
        show_support_punctual: bool,
        show_support_linear: bool,
        show_support_planar: bool,
        show_marker: bool,
        display_mode: str,
        transparency_percent: int,
        profiles_transparency_percent: int = INITIAL_PROFILES_TRANSPARENCY_PERCENT,
    ) -> None:
        """Applique en une seule passe l'intégralité de l'état d'affichage.

        Utilisé au chargement du modèle pour éviter les 9 appels set_*
        séquentiels qui déclenchaient chacun _apply_visibility_state() →
        _apply_face_opacity_state() → Render(). On affecte ici tous les
        attributs privés, puis on appelle _apply_visibility_state() une seule
        fois — qui enchaîne _apply_face_opacity_state() et Render() en fin
        d'exécution.

        Les méthodes set_show_*() / set_display_mode() / set_faces_transparency()
        restent inchangées pour les interactions utilisateur en temps réel.
        """
        # Normaliser le display_mode avant toute affectation
        if display_mode not in _ALL_DISPLAY_MODES:
            display_mode = "wireframe"
        _old_mode = self._display_mode

        # Affecter tous les attributs de visibilité sans déclencher de rendu
        self._show_lines             = show_lines
        self._show_planars           = show_planars
        self._show_load_areas        = show_load_areas
        self._show_support_punctual  = show_support_punctual
        self._show_support_linear    = show_support_linear
        self._show_support_planar    = show_support_planar
        self._show_marker            = show_marker
        self._display_mode           = display_mode
        self._transparency_percent   = max(0, min(100, int(transparency_percent)))
        self._profiles_transparency_percent = max(0, min(100, int(profiles_transparency_percent)))

        # Appliquer l'orientation_widget (logique propre à show_marker,
        # normalement dans set_show_marker)
        if self.orientation_widget:
            if show_marker:
                self.orientation_widget.SetEnabled(1)
                self.orientation_widget.InteractiveOff()
            else:
                self.orientation_widget.SetEnabled(0)

        # Un seul appel — il enchaîne _apply_face_opacity_state() + Render().
        # Entrer/sortir d'un mode profils exige de (re)construire _profiles_actor.
        if (_old_mode in _PROFILE_MODES) != (self._display_mode in _PROFILE_MODES):
            self._rebuild_filtered_structural_actors()
        else:
            self._apply_visibility_state()

    def set_line_widths(self, linear_width: float, planar_width: float, opening_width: float, load_area_width: float):
        self.linear_line_width = max(0.1, float(linear_width))
        self.planar_line_width = max(0.1, float(planar_width))
        self.opening_line_width = max(0.1, float(opening_width))
        self.load_area_line_width = max(0.1, float(load_area_width))

        if self._lines_actor:
            self._lines_actor.GetProperty().SetLineWidth(self.linear_line_width)
        if self._planar_actor:
            self._planar_actor.GetProperty().SetLineWidth(self.planar_line_width)
        if self._openings_actor:
            self._openings_actor.GetProperty().SetLineWidth(self.opening_line_width)
        if self._load_areas_actor:
            self._load_areas_actor.GetProperty().SetLineWidth(self.load_area_line_width)

        self._refresh_selection_overlay()

    def set_support_styles(
        self,
        punctual_size: float,
        punctual_line_width: float,
        linear_line_width: float,
        planar_line_width: float
    ):
        self.support_punctual_size = max(0.05, float(punctual_size))
        self.support_punctual_line_width = max(0.1, float(punctual_line_width))
        self.support_linear_line_width = max(0.1, float(linear_line_width))
        self.support_planar_line_width = max(0.1, float(planar_line_width))

        if self._support_linear_actor:
            self._support_linear_actor.GetProperty().SetLineWidth(self.support_linear_line_width)
        if self._support_planar_actor:
            self._support_planar_actor.GetProperty().SetLineWidth(self.support_planar_line_width)
        if self._support_planar_centroid_actor:
            self._support_planar_centroid_actor.GetProperty().SetLineWidth(self.support_planar_line_width)

        if self._support_punctual_points:
            actor = self._make_wire_actor(
                self._build_punctual_supports_polydata(
                    self._support_punctual_points,
                    element_indexes=getattr(self, "_support_punctual_indexes", None),
                ),
                self.support_punctual_color,
                self.support_punctual_line_width,
            )
            self._replace_actor("_support_punctual_actor", actor, role="support_punctual", pickable=True)

        self._apply_visibility_state()
        self._refresh_selection_overlay()

    # ------------------------------------------------------------------
    # Charges ponctuelles — rendu VTK
    # ------------------------------------------------------------------

    def _make_load_line_actor(self, polydata, color, line_width):
        actor = self._make_polydata_actor(polydata, color, line_width=line_width)
        if actor is not None:
            actor.GetProperty().LightingOff()
        return actor

    def _make_load_fill_actor(self, polydata, color):
        actor = self._make_polydata_actor(polydata, color, opacity=0.18)
        if actor is not None:
            prop = actor.GetProperty()
            prop.SetAmbient(0.5)
            prop.SetDiffuse(0.5)
            prop.BackfaceCullingOff()
        return actor

    def _build_punctual_load_lines(self, loads: list, scale: float, case_filter=None,
                                   norm_loads: list = None, progress_cb=None):
        """Geometrie en lignes des charges ponctuelles : une fleche resultante par
        charge (tete au point d'application), longueur proportionnelle a |F|/F_max,
        et un arc par composante de moment non nulle, rayon proportionnel a |M|/M_max.
        Retourne une vtkPolyData de lignes ou None.

        F_max/M_max sont calcules sur norm_loads (defaut : charges actives).
        """
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return None
        index_of = {id(ld): i for i, ld in enumerate(self._punctual_load_data)}
        norm = active if norm_loads is None else norm_loads
        f_max = max((_resultant(ld, ("fx", "fy", "fz")) for ld in norm), default=0.0)
        m_max = max((abs(float(ld.get(c) or 0.0)) for ld in norm for c in ("mx", "my", "mz")), default=0.0)

        lines = LoadLines(self.ELEMENT_INDEX_ARRAY)
        max_tip = TIP_RATIO * scale
        for ld in active:
            idx = index_of.get(id(ld), 0)
            ox, oy, oz = ld["pos"]
            f_res = _resultant(ld, ("fx", "fy", "fz"))
            if f_max > 1e-9 and f_res > 1e-9:
                d = tuple(float(ld.get(c) or 0.0) / f_res for c in ("fx", "fy", "fz"))
                length = f_res / f_max * scale
                lines.add_arrow((ox - d[0]*length, oy - d[1]*length, oz - d[2]*length), d, length, max_tip, idx)
            if m_max > 1e-9:
                for axis, comp in enumerate(("mx", "my", "mz")):
                    m = float(ld.get(comp) or 0.0)
                    if abs(m) >= 1e-9:
                        lines.add_moment_arc((ox, oy, oz), axis, abs(m) / m_max * scale, 1 if m > 0 else -1, idx)
            if progress_cb is not None:
                progress_cb()
        return lines.to_polydata()

    def _build_punctual_load_polydata_batch(self, loads: list, scale: float,
                                             case_filter=None, progress_cb=None):
        """Version thread-safe pour BuildLoadsWorker : {'arrows': lignes ou None}."""
        return {"arrows": self._build_punctual_load_lines(loads, scale, case_filter=case_filter,
                                                          progress_cb=progress_cb)}

    def _build_punctual_load_actors(self, loads: list, scale: float, color: tuple, case_filter=None,
                                    line_width: float = 1.5, norm_loads: list = None) -> list:
        """Acteur de lignes des charges ponctuelles ; liste de (actor, -1)."""
        actor = self._make_load_line_actor(
            self._build_punctual_load_lines(loads, scale, case_filter=case_filter, norm_loads=norm_loads),
            color, line_width)
        return [(actor, -1)] if actor else []

    def load_punctual_loads(self, loads: list):
        """Stocke les données de charges ponctuelles et reconstruit le rendu si visible."""
        self._punctual_load_data = list(loads or [])
        self.punctual_load_count = len(self._punctual_load_data)
        self._rebuild_punctual_load_actors()

    def _rebuild_punctual_load_actors(self):
        """Efface et reconstruit tous les acteurs de charges ponctuelles."""
        # Effacer les acteurs existants
        for actor in self._punctual_load_actors:
            self._remove_actor(actor)
        self._punctual_load_actors = []

        if not self._show_punctual_loads or not self._punctual_load_data:
            self.render_window.Render()
            return

        actor_index_pairs = self._build_punctual_load_actors(
            self._punctual_load_data,
            self.effective_load_scale("punctual"),
            self.punctual_load_color,
            case_filter=self._punctual_load_case_filter,
            line_width=self.punctual_load_line_width,
        )
        for actor, idx in actor_index_pairs:
            self._add_actor(actor, role="punctual_load", pickable=True)
            self._punctual_load_actors.append(actor)

        self.render_window.Render()

    def set_show_punctual_loads(self, visible: bool):
        self._show_punctual_loads = visible
        self._rebuild_punctual_load_actors()

    def set_punctual_load_case_filter(self, case_eid):
        """case_eid = None pour afficher tous les cas, ou un int EID pour filtrer."""
        self._punctual_load_case_filter = int(case_eid) if case_eid is not None else None
        self._rebuild_punctual_load_actors()

    def set_punctual_load_scale(self, scale: float):
        self.punctual_load_scale = max(0.1, float(scale))
        if self._show_punctual_loads and self._punctual_load_data:
            self._rebuild_punctual_load_actors()

    def set_punctual_load_style(self, color: tuple, line_width: float):
        """Applique couleur et epaisseur de trait (px) aux charges ponctuelles."""
        self.punctual_load_color = tuple(float(v) for v in color)
        self.punctual_load_line_width = max(0.1, float(line_width))
        if self._show_punctual_loads and self._punctual_load_data:
            self._rebuild_punctual_load_actors()

    # ------------------------------------------------------------------
    # Charges linéaires
    # ------------------------------------------------------------------

    def _build_linear_load_lines(self, loads: list, scale: float, case_filter=None,
                                 global_data: list = None, norm_loads: list = None, progress_cb=None):
        """Geometrie en lignes des charges lineaires : peigne de fleches le long de
        la barre (tete sur la barre), ligne de contour par les queues, arcs de
        moment aux memes points. Retourne une vtkPolyData de lignes ou None.

        F_max/M_max sont calcules sur norm_loads (defaut : charges actives).
        """
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return None
        ref = global_data if global_data is not None else self._linear_load_data
        index_of = {id(ld): i for i, ld in enumerate(ref)}

        NB_SEGMENTS = 8

        f_max = 0.0
        m_max = 0.0
        for ld in (active if norm_loads is None else norm_loads):
            c_max = max(abs(float(ld.get("coeff1") or 1.0)), abs(float(ld.get("coeff2") or 1.0)))
            f_max = max(f_max, _resultant(ld, ("fx", "fy", "fz")) * c_max)
            m_max = max(m_max, _resultant(ld, ("mx", "my", "mz")) * c_max)

        lines = LoadLines(self.ELEMENT_INDEX_ARRAY)
        max_tip = TIP_RATIO * scale
        for ld in active:
            idx = index_of.get(id(ld), 0)
            p0, p1 = ld["pt_start"], ld["pt_end"]
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            f_res = _resultant(ld, ("fx", "fy", "fz"))
            m_res = _resultant(ld, ("mx", "my", "mz"))
            moments = [float(ld.get(c) or 0.0) for c in ("mx", "my", "mz")]
            has_force = f_max > 1e-9 and f_res > 1e-9
            has_moment = m_max > 1e-9 and m_res > 1e-9
            if has_force:
                f_dir = tuple(float(ld.get(c) or 0.0) / f_res for c in ("fx", "fy", "fz"))

            tails = []
            for i in range(NB_SEGMENTS + 1):
                t = i / NB_SEGMENTS
                p = (p0[0] + t*(p1[0] - p0[0]), p0[1] + t*(p1[1] - p0[1]), p0[2] + t*(p1[2] - p0[2]))
                coeff = c1 + t * (c2 - c1)
                if has_force:
                    length = f_res * abs(coeff) / f_max * scale
                    d = f_dir if coeff >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                    tail = (p[0] - d[0]*length, p[1] - d[1]*length, p[2] - d[2]*length)
                    tails.append(tail)
                    lines.add_arrow(tail, d, length, max_tip, idx)
                elif has_moment:
                    tails.append(p)
                if has_moment and m_res * abs(coeff) > 1e-9:
                    radius = m_res * abs(coeff) / m_max * scale
                    for axis, m in enumerate(moments):
                        if abs(m) > 1e-9:
                            lines.add_moment_arc(p, axis, radius, 1 if m * coeff >= 0 else -1, idx)
            lines.add_polyline(tails, idx)
            if progress_cb is not None:
                progress_cb()
        return lines.to_polydata()

    def _build_linear_load_actors(self, loads: list, scale: float, color: tuple,
                                   case_filter=None, line_width: float = 1.5,
                                   global_data: list = None, norm_loads: list = None) -> list:
        """Acteur de lignes des charges lineaires ; liste de (actor, -1)."""
        actor = self._make_load_line_actor(
            self._build_linear_load_lines(loads, scale, case_filter=case_filter,
                                          global_data=global_data, norm_loads=norm_loads),
            color, line_width)
        return [(actor, -1)] if actor else []

    def _build_linear_load_polydata_batch(self, loads: list, scale: float,
                                           case_filter=None, global_data: list = None,
                                           progress_cb=None) -> dict:
        """Version thread-safe pour BuildLoadsWorker : {'arrows': lignes ou None}."""
        return {"arrows": self._build_linear_load_lines(loads, scale, case_filter=case_filter,
                                                        global_data=global_data, progress_cb=progress_cb)}

    def load_linear_loads(self, loads: list):
        """Stocke les données de charges linéaires et reconstruit le rendu si visible."""
        self._linear_load_data = list(loads or [])
        self.linear_load_count = len(self._linear_load_data)
        self._rebuild_linear_load_actors()

    def _rebuild_linear_load_actors(self):
        """Efface et reconstruit tous les acteurs de charges linéaires."""
        for actor in self._linear_load_actors:
            self._remove_actor(actor)
        self._linear_load_actors = []

        if not self._show_linear_loads or not self._linear_load_data:
            self.render_window.Render()
            return

        actor_index_pairs = self._build_linear_load_actors(
            self._linear_load_data,
            self.effective_load_scale("linear"),
            self.linear_load_color,
            case_filter=self._linear_load_case_filter,
            line_width=self.linear_load_line_width,
            global_data=self._linear_load_data,
        )
        for actor, idx in actor_index_pairs:
            self._add_actor(actor, role="linear_load", pickable=True)
            self._linear_load_actors.append(actor)

        self.render_window.Render()

    def set_show_linear_loads(self, visible: bool):
        self._show_linear_loads = visible
        self._rebuild_linear_load_actors()

    def set_linear_load_case_filter(self, case_eid):
        self._linear_load_case_filter = int(case_eid) if case_eid is not None else None
        self._rebuild_linear_load_actors()

    def set_linear_load_scale(self, scale: float):
        self.linear_load_scale = max(0.1, float(scale))
        if self._show_linear_loads and self._linear_load_data:
            self._rebuild_linear_load_actors()

    def set_linear_load_style(self, color: tuple, line_width: float):
        """Applique couleur et epaisseur de trait (px) aux charges lineaires."""
        self.linear_load_color = tuple(float(v) for v in color)
        self.linear_load_line_width = max(0.1, float(line_width))
        if self._show_linear_loads and self._linear_load_data:
            self._rebuild_linear_load_actors()

    def _build_planar_load_lines(self, loads: list, scale: float, case_filter=None,
                                 global_data: list = None, norm_loads: list = None, progress_cb=None):
        """Geometrie en lignes des charges surfaciques : une fleche par sommet,
        contour ferme par les queues, et remplissage semi-transparent entre le
        polygone et le contour. Retourne (lignes, remplissage), chacun ou None.

        F_max est calcule sur norm_loads (defaut : charges actives).
        """
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return None, None
        ref = global_data if global_data is not None else self._planar_load_data
        index_of = {id(ld): i for i, ld in enumerate(ref)}

        def coeffs(ld):
            return float(ld.get("coeff1") or 1.0), float(ld.get("coeff2") or 1.0), float(ld.get("coeff3") or 1.0)

        f_max = 0.0
        for ld in (active if norm_loads is None else norm_loads):
            f_res = _resultant(ld, ("fx", "fy", "fz"))
            c1, c2, c3 = coeffs(ld)
            pts = ld.get("pts") or []
            if len(pts) >= 3:
                c_max = max(abs(self._interpolate_planar_coeff(pt, pts, c1, c2, c3)) for pt in pts)
            else:
                c_max = max(abs(c1), abs(c2), abs(c3))
            f_max = max(f_max, f_res * c_max)

        lines = LoadLines(self.ELEMENT_INDEX_ARRAY)
        max_tip = TIP_RATIO * scale
        fill_pts = vtk.vtkPoints()
        fill_polys = vtk.vtkCellArray()
        fill_ids = self._make_int_array()
        for ld in active:
            if progress_cb is not None:
                progress_cb()
            idx = index_of.get(id(ld), 0)
            pts = ld.get("pts") or []
            if len(pts) < 3:
                continue
            f_res = _resultant(ld, ("fx", "fy", "fz"))
            if f_max < 1e-9 or f_res < 1e-9:
                continue
            c1, c2, c3 = coeffs(ld)
            f_dir = (float(ld.get("fx") or 0.0) / f_res, float(ld.get("fy") or 0.0) / f_res, float(ld.get("fz") or 0.0) / f_res)
            tails = []
            for pt in pts:
                coeff = self._interpolate_planar_coeff(pt, pts, c1, c2, c3)
                length = f_res * abs(coeff) / f_max * scale
                d = f_dir if coeff >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                tail = (pt[0] - d[0]*length, pt[1] - d[1]*length, pt[2] - d[2]*length)
                tails.append(tail)
                lines.add_arrow(tail, d, length, max_tip, idx)
            lines.add_polyline(tails, idx, closed=True)
            n = len(pts)
            for i in range(n):
                j = (i + 1) % n
                quad = [fill_pts.InsertNextPoint(*p) for p in (pts[i], pts[j], tails[j], tails[i])]
                for tri in ((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3])):
                    fill_polys.InsertNextCell(3, tri)
                    fill_ids.InsertNextValue(idx)

        fill_pd = None
        if fill_polys.GetNumberOfCells():
            fill_pd = vtk.vtkPolyData()
            fill_pd.SetPoints(fill_pts)
            fill_pd.SetPolys(fill_polys)
            fill_pd.GetCellData().AddArray(fill_ids)
        return lines.to_polydata(), fill_pd

    def _build_planar_load_actors(self, loads: list, scale: float, color: tuple,
                                   case_filter=None, line_width: float = 1.5,
                                   global_data: list = None, norm_loads: list = None) -> list:
        """Acteurs de lignes + remplissage des charges surfaciques ; liste de (actor, -1)."""
        lines_pd, fill_pd = self._build_planar_load_lines(loads, scale, case_filter=case_filter,
                                                          global_data=global_data, norm_loads=norm_loads)
        actors = [self._make_load_line_actor(lines_pd, color, line_width), self._make_load_fill_actor(fill_pd, color)]
        return [(actor, -1) for actor in actors if actor]

    @staticmethod
    def _interpolate_planar_coeff(pt, pts, c1, c2, c3) -> float:
        """Interpole le coefficient de variation au point pt par le plan defini
        par les 3 premiers points du polygone avec les coefficients c1/c2/c3.

        Si le plan est degenere (points colineaires), retourne la moyenne des 3
        coefficients.
        """
        import math
        if len(pts) < 3:
            return (c1 + c2 + c3) / 3.0

        p0 = pts[0]
        p1 = pts[1]
        p2 = pts[2]

        # Vecteurs du plan
        v1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        v2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])

        # Norme de chaque vecteur
        n1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
        n2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)

        if n1 < 1e-12 or n2 < 1e-12:
            return (c1 + c2 + c3) / 3.0

        # Chercher les coordonnees barycentriques du point dans le triangle p0/p1/p2
        # par projection dans le plan
        # Systeme : pt = p0 + alpha*v1 + beta*v2
        # Resoudre par moindres carres (dot product)
        d = pt[0] - p0[0], pt[1] - p0[1], pt[2] - p0[2]

        # Matrice 2x2 : [[v1.v1, v1.v2],[v1.v2, v2.v2]]
        a11 = v1[0]*v1[0] + v1[1]*v1[1] + v1[2]*v1[2]
        a12 = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
        a22 = v2[0]*v2[0] + v2[1]*v2[1] + v2[2]*v2[2]
        b1  = d[0]*v1[0]  + d[1]*v1[1]  + d[2]*v1[2]
        b2  = d[0]*v2[0]  + d[1]*v2[1]  + d[2]*v2[2]

        det = a11*a22 - a12*a12
        if abs(det) < 1e-18:
            return (c1 + c2 + c3) / 3.0

        alpha = (b1*a22 - b2*a12) / det
        beta  = (b2*a11 - b1*a12) / det

        # Le coefficient au point = interpolation lineaire :
        # coeff(p0) = c1, coeff(p1) = c2, coeff(p2) = c3
        return c1 + alpha * (c2 - c1) + beta * (c3 - c1)

    def _build_planar_load_polydata_batch(self, loads: list, scale: float,
                                           case_filter=None, global_data: list = None,
                                           progress_cb=None) -> dict:
        """Version thread-safe pour BuildLoadsWorker : {'arrows': lignes, 'fill': remplissage}."""
        lines_pd, fill_pd = self._build_planar_load_lines(loads, scale, case_filter=case_filter,
                                                          global_data=global_data, progress_cb=progress_cb)
        return {"arrows": lines_pd, "fill": fill_pd}

    def apply_loads_polydata_batch(self, batch: dict):
        """Applique les polydata pre-construits (depuis un worker) au renderer.

        Doit etre appele depuis le thread principal.
        batch = {
          'punctual_action'/'linear_action'/'planar_action': 'build'|'keep'|'clear',
          'punctual': {'arrows': vtkPolyData|None},               # si action == 'build'
          'linear':   {'arrows': vtkPolyData|None},
          'planar':   {'arrows': vtkPolyData|None, 'fill': vtkPolyData|None},
          'punctual_color': tuple, 'linear_color': tuple, 'planar_color': tuple,
        }
        'keep' : le type n'a pas change (ni visibilite ni donnees) -> acteurs
        existants laisses tels quels, pas de reconstruction.
        'clear' : type masque -> acteurs existants retires.
        'build' (defaut, retro-compatible) : reconstruction habituelle.
        """
        for kind, role in (("punctual", "punctual_load"), ("linear", "linear_load"), ("planar", "planar_load")):
            action = batch.get(f"{kind}_action", "build")
            actors = getattr(self, f"_{kind}_load_actors")
            if action == "keep":
                continue
            for actor in actors:
                self._remove_actor(actor)
            actors.clear()
            if action != "build" or not getattr(self, f"_show_{kind}_loads"):
                continue
            color = batch.get(f"{kind}_color", getattr(self, f"{kind}_load_color"))
            data = batch.get(kind, {})
            new_actors = [
                self._make_load_line_actor(data.get("arrows"), color, getattr(self, f"{kind}_load_line_width")),
                self._make_load_fill_actor(data.get("fill"), color),
            ]
            for actor in new_actors:
                if actor:
                    self._add_actor(actor, role=role, pickable=True)
                    actors.append(actor)

        self.render_window.Render()


    def load_planar_loads(self, loads: list):
        """Stocke les donnees de charges surfaciques et reconstruit le rendu si visible."""
        self._planar_load_data = list(loads or [])
        self.planar_load_count = len(self._planar_load_data)
        self._rebuild_planar_load_actors()

    def _rebuild_planar_load_actors(self):
        """Efface et reconstruit tous les acteurs de charges surfaciques."""
        for actor in self._planar_load_actors:
            self._remove_actor(actor)
        self._planar_load_actors = []

        if not self._show_planar_loads or not self._planar_load_data:
            self.render_window.Render()
            return

        actor_index_pairs = self._build_planar_load_actors(
            self._planar_load_data,
            self.effective_load_scale("planar"),
            self.planar_load_color,
            case_filter=self._planar_load_case_filter,
            line_width=self.planar_load_line_width,
            global_data=self._planar_load_data,
        )
        for actor, idx in actor_index_pairs:
            self._add_actor(actor, role="planar_load", pickable=True)
            self._planar_load_actors.append(actor)

        self.render_window.Render()

    def set_show_planar_loads(self, visible: bool):
        self._show_planar_loads = visible
        self._rebuild_planar_load_actors()

    def set_planar_load_case_filter(self, case_eid):
        self._planar_load_case_filter = int(case_eid) if case_eid is not None else None
        self._rebuild_planar_load_actors()

    def set_planar_load_scale(self, scale: float):
        self.planar_load_scale = max(0.1, float(scale))
        if self._show_planar_loads and self._planar_load_data:
            self._rebuild_planar_load_actors()

    def set_planar_load_style(self, color: tuple, line_width: float):
        """Applique couleur et epaisseur de trait (px) aux charges surfaciques."""
        self.planar_load_color = tuple(float(v) for v in color)
        self.planar_load_line_width = max(0.1, float(line_width))
        if self._show_planar_loads and self._planar_load_data:
            self._rebuild_planar_load_actors()

    def load_model(self, model_data: dict):
        self.clear_scene()
        self._has_model = True
        self._section_color_map = {}

        self._model_data = {
            "lines": list(model_data.get("lines", [])),
            "line_eids": list(model_data.get("line_eids", [])),
            "line_properties": list(model_data.get("line_properties", [])),
            "line_sections": list(model_data.get("line_sections", []) or []),
            "planars": list(model_data.get("planars", [])),
            "planar_eids": list(model_data.get("planar_eids", [])),
            "planar_properties": list(model_data.get("planar_properties", [])),
            "planar_thicknesses": list(model_data.get("planar_thicknesses", []) or []),
            "planar_eccentricities": list(model_data.get("planar_eccentricities", []) or []),
            "load_areas": list(model_data.get("load_areas", [])),
            "punctual_supports": list(model_data.get("punctual_supports", [])),
            "punctual_support_eids": list(model_data.get("punctual_support_eids", [])),
            "linear_supports": list(model_data.get("linear_supports", [])),
            "linear_support_eids": list(model_data.get("linear_support_eids", [])),
            "planar_supports": list(model_data.get("planar_supports", [])),
            "planar_support_eids": list(model_data.get("planar_support_eids", [])),
        }
        self._support_punctual_points = list(self._model_data["punctual_supports"])
        self._support_punctual_indexes = None
        self._hidden_items = set()

        # Charges ponctuelles — désactivé à chaque nouveau chargement
        self._show_punctual_loads = False
        self._punctual_load_data = list(model_data.get("punctual_loads", []) or [])
        self.punctual_load_count = int(model_data.get("punctual_load_count", len(self._punctual_load_data)) or 0)
        self._punctual_load_case_filter = None

        # Charges linéaires — désactivé à chaque nouveau chargement
        self._show_linear_loads = False
        self._linear_load_data = list(model_data.get("linear_loads", []) or [])
        self.linear_load_count = int(model_data.get("linear_load_count", len(self._linear_load_data)) or 0)
        self._linear_load_case_filter = None

        self.lines_count = int(model_data.get("linear_count", len(self._model_data["lines"])) or 0)
        self.planars_count = int(model_data.get("planar_count", len(self._model_data["planars"])) or 0)
        self.load_areas_count = int(model_data.get("load_area_count", len(self._model_data["load_areas"])) or 0)
        self.support_punctual_count = int(model_data.get("punctual_support_count", len(self._model_data["punctual_supports"])) or 0)
        self.support_linear_count = int(model_data.get("linear_support_count", len(self._model_data["linear_supports"])) or 0)
        self.support_planar_count = int(model_data.get("planar_support_count", len(self._model_data["planar_supports"])) or 0)

        self._rebuild_filtered_structural_actors()

        self._apply_visibility_state()
        self.set_line_widths(
            self.linear_line_width,
            self.planar_line_width,
            self.opening_line_width,
            self.load_area_line_width,
        )
        self.set_support_styles(
            self.support_punctual_size,
            self.support_punctual_line_width,
            self.support_linear_line_width,
            self.support_planar_line_width,
        )
        self.set_colors(
            self.linear_color,
            self.planar_color,
            self.opening_color,
            self.load_area_color,
            self.support_punctual_color,
            self.support_linear_color,
            self.support_planar_color,
        )
        self.set_faces_transparency(self._transparency_percent)
        self.set_show_marker(self._show_marker)
        self._minimap.clear_geometry()
        self._minimap.build_geometry()
        self._update_model_extent()
        self.set_isometric_view()

    def _update_model_extent(self):
        """Plus grande dimension (m) de la boite englobante des filaires et surfaciques."""
        pts = [p for seg in self._model_data.get("lines", []) for p in seg]
        pts += [p for item in self._model_data.get("planars", []) for p in (item.get("outer") or [])]
        self._model_extent = max((max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)), default=0.0) if pts else 0.0

    def effective_load_scale(self, kind: str) -> float:
        """Longueur (m) de la plus forte charge du type : fraction de la taille du modele
        en echelle automatique, sinon l'echelle manuelle du type."""
        if self.load_auto_scale and self._model_extent > 0:
            return AUTO_LOAD_SCALE_RATIO * self._model_extent
        return getattr(self, f"{kind}_load_scale")

    def _filtered_line_indexes(self):
        items = list(self._model_data.get("line_properties", []))
        if not items:
            return []
        isolated = list(self._isolated_selection or [])
        if isolated:
            LINEAR_ROLES = {"lines", "line", "linear", "element_linear"}
            # Collecter tous les indexes de filaires isolés
            line_indexes = set()
            has_any = False
            for entry in isolated:
                role = str(entry.get("role") or "").strip()
                has_any = True
                if role in LINEAR_ROLES:
                    idx = int(entry.get("index", -1))
                    if 0 <= idx < len(items):
                        line_indexes.add(idx)
            if has_any and not line_indexes:
                # Isolation active mais sur d'autres types → aucun filaire visible
                return []
            return self._without_hidden("lines", sorted(line_indexes))
        section_names = self._filter_section_names
        material_names = self._filter_material_names
        indexes = []
        for idx, props in enumerate(items):
            props = props or {}
            section_ok = True if section_names is None else str(props.get("section", "N/A")) in section_names
            material_ok = True if material_names is None else str(props.get("material", "N/A")) in material_names
            if section_ok and material_ok:
                indexes.append(idx)
        return self._without_hidden("lines", indexes)

    def _filtered_planar_indexes(self):
        items = list(self._model_data.get("planar_properties", []))
        if not items:
            return []
        isolated = list(self._isolated_selection or [])
        if isolated:
            PLANAR_ROLES = {"planars", "planar", "element_planar"}
            planar_indexes = set()
            has_any = False
            for entry in isolated:
                role = str(entry.get("role") or "").strip()
                has_any = True
                if role in PLANAR_ROLES:
                    idx = int(entry.get("index", -1))
                    if 0 <= idx < len(items):
                        planar_indexes.add(idx)
            if has_any and not planar_indexes:
                return []
            return self._without_hidden("planars", sorted(planar_indexes))
        thickness_names = self._filter_thickness_names
        material_names = self._filter_material_names
        indexes = []
        for idx, props in enumerate(items):
            props = props or {}
            thickness_ok = True if thickness_names is None else str(props.get("thickness", "N/A")) in thickness_names
            material_ok = True if material_names is None else str(props.get("material", "N/A")) in material_names
            if thickness_ok and material_ok:
                indexes.append(idx)
        return self._without_hidden("planars", indexes)

    def _without_hidden(self, role, indexes):
        hidden = self._hidden_items
        return [i for i in indexes if (role, i) not in hidden] if hidden else indexes

    def _select_items_by_indexes(self, items, indexes):
        source = list(items or [])
        return [source[int(idx)] for idx in indexes if 0 <= int(idx) < len(source)]

    def _build_planar_edges_polydata(self, faces_pd):
        if faces_pd is None or faces_pd.GetNumberOfCells() == 0:
            return None
        merge = vtk.vtkCleanPolyData()
        merge.SetInputData(faces_pd)
        merge.Update()
        fe = vtk.vtkFeatureEdges()
        fe.SetInputData(merge.GetOutput())
        fe.BoundaryEdgesOn()
        fe.FeatureEdgesOn()
        fe.ManifoldEdgesOff()
        fe.NonManifoldEdgesOn()
        fe.SetFeatureAngle(10.0)
        fe.Update()
        out = vtk.vtkPolyData()
        out.DeepCopy(fe.GetOutput())
        return out if out.GetNumberOfCells() > 0 else None

    def _rebuild_planar_faces_actor(self):
        """Reconstruit uniquement l'acteur des faces surfaciques (plat, ou
        epaissi si _planar_thickness_enabled et mode Profiles), sans toucher
        aux autres acteurs. Separee de _rebuild_filtered_structural_actors
        pour pouvoir etre appelee seule depuis main_window._on_profiles_build_ready
        (fin du worker de construction des profils filaires) sans re-declencher
        ce dernier, qui a son propre pipeline pour _profiles_actor/_profiles_base_pd."""
        planar_indexes = self._filtered_planar_indexes()
        filtered_planars = self._select_items_by_indexes(self._model_data.get("planars", []), planar_indexes)
        if self._planar_thickness_enabled and self._display_mode in _PROFILE_MODES:
            filtered_thicknesses = self._select_items_by_indexes(self._model_data.get("planar_thicknesses", []) or [], planar_indexes)
            filtered_eccentricities = self._select_items_by_indexes(self._model_data.get("planar_eccentricities", []) or [], planar_indexes)
            planar_faces_pd = self._build_planar_thickness_polydata(
                filtered_planars, filtered_thicknesses, filtered_eccentricities, element_indexes=planar_indexes,
            )
        else:
            planar_faces_pd = self._build_faces_polydata(filtered_planars, element_indexes=planar_indexes)
        self._replace_actor(
            "_planar_faces_actor",
            self._make_surface_actor(planar_faces_pd, self.planar_color, self.planar_faces_base_opacity),
            role="planars",
            pickable=True,
        )
        self._replace_actor(
            "_planar_edges_actor",
            self._make_wire_actor(self._build_planar_edges_polydata(planar_faces_pd), (0.0, 0.0, 0.0), 1.0),
        )

    def _rebuild_profiles_actor(self, line_indexes=None, filtered_lines=None, filtered_line_sections=None, synchronous=True):
        """Reconstruit le solide des profils (couteux : tous les elements). La
        selection ne passe PAS par ici : elle ne fait qu'echanger le tableau de
        couleurs par cellule via _apply_profiles_selection_colors().

        synchronous=False : si l'affichage est en mode Profiles, ne reconstruit
        PAS ici (laisse l'acteur existant tel quel) - l'appelant relance la
        construction en arriere-plan (BuildProfilesWorker + barre de
        progression) pour eviter de geler l'UI sur un gros modele."""
        self._profiles_base_pd = None
        self._profiles_base_colors = None
        if self._display_mode not in _PROFILE_MODES:
            self._replace_actor("_profiles_actor", None, role="lines", pickable=True)
            return
        if not synchronous:
            return
        if line_indexes is None:
            line_indexes = self._filtered_line_indexes()
        if filtered_lines is None:
            filtered_lines = self._select_items_by_indexes(self._model_data.get("lines", []), line_indexes)
        if filtered_line_sections is None:
            filtered_line_sections = self._select_items_by_indexes(
                self._model_data.get("line_sections", []) or [], line_indexes
            )
        base_pd = self._build_profiles_polydata(filtered_lines, filtered_line_sections, element_indexes=line_indexes)
        self._apply_profiles_build_result(base_pd)

    def _apply_profiles_build_result(self, base_pd):
        """Cree/remplace l'acteur des profils a partir d'un polydata deja
        construit. Extrait de _rebuild_profiles_actor pour etre reutilisable
        par le callback de BuildProfilesWorker (switch de mode asynchrone)."""
        self._profiles_base_pd = base_pd
        self._profiles_base_colors = None
        if base_pd is not None:
            sc = base_pd.GetCellData().GetArray("section_colors")   # present si color_by_section
            if sc is not None:
                self._profiles_base_colors = vtk.vtkUnsignedCharArray()
                self._profiles_base_colors.DeepCopy(sc)
        self._replace_actor(
            "_profiles_actor",
            self._make_surface_actor(base_pd, self.linear_color, 1.0),
            role="lines",
            pickable=True,
        )
        self._apply_profiles_selection_colors()

    def _apply_profiles_selection_colors(self):
        """Applique la couleur de selection aux cellules des elements filaires
        selectionnes, en mutant le tableau de scalaires du polydata cache (pas de
        reconstruction geometrique). Restaure les couleurs de base sinon. Ne
        declenche pas de rendu : l'appelant s'en charge."""
        actor = self._profiles_actor
        pd = self._profiles_base_pd
        if actor is None or pd is None or actor.GetMapper() is None:
            return
        idx_arr = pd.GetCellData().GetArray(self.ELEMENT_INDEX_ARRAY)
        n = pd.GetNumberOfCells()
        if idx_arr is None or n == 0:
            return
        mapper = actor.GetMapper()
        selected = {int(it["index"]) for it in self._selected_items if it.get("role") == "lines"}
        wire3d = self._display_mode == "profiles_wire"
        base = None if wire3d else self._profiles_base_colors  # couleurs de section, ou None (toujours None en Filaire 3D)

        if not selected:
            if base is not None:
                pd.GetCellData().SetScalars(base)
                mapper.SetScalarModeToUseCellData()
                mapper.SetColorModeToDirectScalars()
                mapper.ScalarVisibilityOn()
            else:
                pd.GetCellData().SetScalars(None)
                mapper.ScalarVisibilityOff()
            pd.Modified()
            return

        sel_rgb = tuple(float(round(c * 255.0)) for c in self.selection_color)
        lin_rgb = tuple(float(round(c * 255.0)) for c in (_WIRE3D_COLOR if wire3d else self.linear_color))
        colors = vtk.vtkUnsignedCharArray()
        colors.SetName("section_colors")
        colors.SetNumberOfComponents(3)
        colors.SetNumberOfTuples(n)
        for i in range(n):
            if int(idx_arr.GetTuple1(i)) in selected:
                colors.SetTuple3(i, *sel_rgb)
            elif base is not None:
                colors.SetTuple3(i, base.GetComponent(i, 0), base.GetComponent(i, 1), base.GetComponent(i, 2))
            else:
                colors.SetTuple3(i, *lin_rgb)
        pd.GetCellData().SetScalars(colors)
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        pd.Modified()

    def _rebuild_filtered_structural_actors(self, rebuild_profiles=True):
        line_indexes = self._filtered_line_indexes()
        planar_indexes = self._filtered_planar_indexes()
        filtered_lines = self._select_items_by_indexes(self._model_data.get("lines", []), line_indexes)
        filtered_line_sections = self._select_items_by_indexes(self._model_data.get("line_sections", []) or [], line_indexes)
        filtered_planars = self._select_items_by_indexes(self._model_data.get("planars", []), planar_indexes)
        isolated = list(self._isolated_selection or [])
        is_isolated = bool(isolated)

        load_areas = list(self._model_data.get("load_areas", []) or [])
        punctual_supports = list(self._model_data.get("punctual_supports", []) or [])
        linear_supports = list(self._model_data.get("linear_supports", []) or [])
        planar_supports = list(self._model_data.get("planar_supports", []) or [])

        # Indexes d'origine (modèle) des éléments affichés, pour que le picking
        # renvoie le bon index après isolation. None = pas d'isolation (enum == index modèle).
        load_area_indexes = None
        punctual_support_indexes = None
        linear_support_indexes = None
        planar_support_indexes = None

        if is_isolated:
            # Collecter les indexes par type à partir de la liste d'isolation
            load_area_idxs = []
            punctual_idxs = []
            linear_sup_idxs = []
            planar_sup_idxs = []
            punctual_load_idxs = []
            linear_load_idxs = []
            planar_load_idxs = []
            for entry in isolated:
                role = str(entry.get("role") or "").strip()
                idx = int(entry.get("index", -1))
                if role == "load_areas" and idx >= 0:
                    load_area_idxs.append(idx)
                elif role == "support_punctual" and idx >= 0:
                    punctual_idxs.append(idx)
                elif role == "support_linear" and idx >= 0:
                    linear_sup_idxs.append(idx)
                elif role == "support_planar" and idx >= 0:
                    planar_sup_idxs.append(idx)
                elif role == "punctual_load" and idx >= 0:
                    punctual_load_idxs.append(idx)
                elif role == "linear_load" and idx >= 0:
                    linear_load_idxs.append(idx)
                elif role == "planar_load" and idx >= 0:
                    planar_load_idxs.append(idx)
            load_areas = self._select_items_by_indexes(load_areas, load_area_idxs)
            punctual_supports = self._select_items_by_indexes(punctual_supports, punctual_idxs)
            linear_supports = self._select_items_by_indexes(linear_supports, linear_sup_idxs)
            planar_supports = self._select_items_by_indexes(planar_supports, planar_sup_idxs)
            load_area_indexes = list(load_area_idxs)
            punctual_support_indexes = list(punctual_idxs)
            linear_support_indexes = list(linear_sup_idxs)
            planar_support_indexes = list(planar_sup_idxs)

            # Filtrer les charges ponctuelles selon l'isolation
            if punctual_load_idxs:
                isolated_loads = [
                    self._punctual_load_data[i]
                    for i in punctual_load_idxs
                    if 0 <= i < len(self._punctual_load_data)
                ]
                # Reconstruire les acteurs de charges avec uniquement les charges isolées
                for actor in self._punctual_load_actors:
                    self._remove_actor(actor)
                self._punctual_load_actors = []
                if self._show_punctual_loads and isolated_loads:
                    actor_index_pairs = self._build_punctual_load_actors(
                        isolated_loads,
                        self.effective_load_scale("punctual"),
                        self.punctual_load_color,
                        case_filter=None,   # déjà filtré par index
                        line_width=self.punctual_load_line_width,
                    )
                    for actor, _idx in actor_index_pairs:
                        self._add_actor(actor, role="punctual_load", pickable=True)
                        self._punctual_load_actors.append(actor)
            else:
                # Isolation active mais pas de charge sélectionnée : cacher toutes les charges
                for actor in self._punctual_load_actors:
                    self._remove_actor(actor)
                self._punctual_load_actors = []
        else:
            # Pas d'isolation : reconstruire normalement
            self._rebuild_punctual_load_actors()

        # Isolation des charges linéaires
        if is_isolated:
            if linear_load_idxs:
                isolated_linear_loads = [
                    self._linear_load_data[i]
                    for i in linear_load_idxs
                    if 0 <= i < len(self._linear_load_data)
                ]
                for actor in self._linear_load_actors:
                    self._remove_actor(actor)
                self._linear_load_actors = []
                if self._show_linear_loads and isolated_linear_loads:
                    actor_index_pairs = self._build_linear_load_actors(
                        isolated_linear_loads,
                        self.effective_load_scale("linear"),
                        self.linear_load_color,
                        case_filter=None,
                        line_width=self.linear_load_line_width,
                        global_data=self._linear_load_data,
                    )
                    for actor, _idx in actor_index_pairs:
                        self._add_actor(actor, role="linear_load", pickable=True)
                        self._linear_load_actors.append(actor)
            else:
                for actor in self._linear_load_actors:
                    self._remove_actor(actor)
                self._linear_load_actors = []
        else:
            self._rebuild_linear_load_actors()

        # Isolation des charges surfaciques
        if is_isolated:
            if planar_load_idxs:
                isolated_planar_loads = [
                    self._planar_load_data[i]
                    for i in planar_load_idxs
                    if 0 <= i < len(self._planar_load_data)
                ]
                for actor in self._planar_load_actors:
                    self._remove_actor(actor)
                self._planar_load_actors = []
                if self._show_planar_loads and isolated_planar_loads:
                    actor_index_pairs = self._build_planar_load_actors(
                        isolated_planar_loads,
                        self.effective_load_scale("planar"),
                        self.planar_load_color,
                        case_filter=None,
                        line_width=self.planar_load_line_width,
                        global_data=self._planar_load_data,
                    )
                    for actor, _idx in actor_index_pairs:
                        self._add_actor(actor, role="planar_load", pickable=True)
                        self._planar_load_actors.append(actor)
            else:
                for actor in self._planar_load_actors:
                    self._remove_actor(actor)
                self._planar_load_actors = []
        else:
            self._rebuild_planar_load_actors()

        if self._hidden_items:
            def drop_hidden(role, items, indexes):
                indexes = range(len(items)) if indexes is None else indexes
                kept = [(item, i) for item, i in zip(items, indexes) if (role, i) not in self._hidden_items]
                return [item for item, _ in kept], [i for _, i in kept]
            load_areas, load_area_indexes = drop_hidden("load_areas", load_areas, load_area_indexes)
            punctual_supports, punctual_support_indexes = drop_hidden("support_punctual", punctual_supports, punctual_support_indexes)
            linear_supports, linear_support_indexes = drop_hidden("support_linear", linear_supports, linear_support_indexes)
            planar_supports, planar_support_indexes = drop_hidden("support_planar", planar_supports, planar_support_indexes)

        # Déterminer si des appuis surfaciques sont isolés (pour le centroïde)
        isolated_has_planar_support = any(
            str(e.get("role") or "") == "support_planar" for e in isolated
        ) if is_isolated else False

        self.lines_count = len(filtered_lines)
        self.planars_count = len(filtered_planars)
        self.load_areas_count = len(load_areas)
        self.support_punctual_count = len(punctual_supports)
        self.support_linear_count = len(linear_supports)
        self.support_planar_count = len(planar_supports)
        self._support_punctual_points = list(punctual_supports)
        self._support_punctual_indexes = punctual_support_indexes

        self._replace_actor(
            "_lines_actor",
            self._make_wire_actor(self._build_lines_polydata(filtered_lines, element_indexes=line_indexes), self.linear_color, self.linear_line_width),
            role="lines",
            pickable=True,
        )
        self._rebuild_profiles_actor(line_indexes, filtered_lines, filtered_line_sections, synchronous=rebuild_profiles)
        self._replace_actor(
            "_planar_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(filtered_planars, element_indexes=planar_indexes), self.planar_color, self.planar_line_width),
            role="planars",
            pickable=True,
        )
        self._rebuild_planar_faces_actor()
        self._replace_actor(
            "_openings_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(filtered_planars, openings=True, element_indexes=planar_indexes), self.opening_color, self.opening_line_width),
            role="planars",
            pickable=False,
        )
        self._replace_actor(
            "_load_areas_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(load_areas, element_indexes=load_area_indexes), self.load_area_color, self.load_area_line_width),
            role="load_areas",
            pickable=True,
        )
        self._replace_actor(
            "_load_areas_faces_actor",
            self._make_surface_actor(self._build_faces_polydata(load_areas, element_indexes=load_area_indexes), self.load_area_color, self.load_areas_faces_base_opacity),
            role="load_areas",
            pickable=True,
        )
        self._replace_actor(
            "_support_punctual_actor",
            self._make_wire_actor(self._build_punctual_supports_polydata(punctual_supports, element_indexes=punctual_support_indexes), self.support_punctual_color, self.support_punctual_line_width),
            role="support_punctual",
            pickable=True,
        )
        self._replace_actor(
            "_support_linear_actor",
            self._make_wire_actor(self._build_lines_polydata(linear_supports, element_indexes=linear_support_indexes, include_section_colors=False), self.support_linear_color, self.support_linear_line_width),
            role="support_linear",
            pickable=True,
        )
        self._replace_actor(
            "_support_planar_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(planar_supports, element_indexes=planar_support_indexes), self.support_planar_color, self.support_planar_line_width),
            role="support_planar",
            pickable=True,
        )
        self._replace_actor(
            "_support_planar_faces_actor",
            self._make_surface_actor(self._build_faces_polydata(planar_supports, element_indexes=planar_support_indexes), self.support_planar_color, self.support_planar_faces_base_opacity),
            role="support_planar",
            pickable=True,
        )
        if not isolated_has_planar_support:
            self.clear_planar_support_result_centroid()
        self._apply_visibility_state()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def set_structural_filters(self, section_names=None, thickness_names=None, material_names=None, rebuild_profiles=True):
        """rebuild_profiles=False : ne reconstruit pas immediatement le solide
        des profils (coûteux) meme si l'affichage est en mode Profiles -
        l'appelant est alors responsable de relancer la construction en
        arriere-plan (cf. main_window._refresh_profiles_if_needed) pour
        garder la barre de progression et ne pas geler l'UI."""
        self._filter_section_names = None if section_names is None else set(str(v) for v in section_names)
        self._filter_thickness_names = None if thickness_names is None else set(str(v) for v in thickness_names)
        self._filter_material_names = None if material_names is None else set(str(v) for v in material_names)
        self._rebuild_filtered_structural_actors(rebuild_profiles=rebuild_profiles)

    def set_isolated_selection(self, selection, rebuild_profiles=True):
        """Isole un ou plusieurs éléments.

        Accepte :
        - None  → annule l'isolation
        - dict  {"role": str, "index": int} → isole un seul élément (compatibilité)
        - list  [{"role": str, "index": int}, ...] → isole plusieurs éléments

        rebuild_profiles=False : voir set_structural_filters.
        """
        if selection is None:
            self._isolated_selection = []
        elif isinstance(selection, dict):
            role = str(selection.get("role") or "").strip()
            index = int(selection.get("index", -1))
            self._isolated_selection = [{"role": role, "index": index}] if role and index >= 0 else []
        elif isinstance(selection, list):
            valid = []
            for item in selection:
                if isinstance(item, dict):
                    role = str(item.get("role") or "").strip()
                    index = int(item.get("index", -1))
                    if role and index >= 0:
                        valid.append({"role": role, "index": index})
            self._isolated_selection = valid
        else:
            self._isolated_selection = []
        self._anomaly_overlay.set_isolation(self._isolated_selection)
        self._rebuild_filtered_structural_actors(rebuild_profiles=rebuild_profiles)

    def set_hidden_items(self, items, rebuild_profiles=True):
        """Masque les items {role, index} donnes (cases decochees de l'arbre Systemes)."""
        self._hidden_items = {(item["role"], item["index"]) for item in items or []}
        self._rebuild_filtered_structural_actors(rebuild_profiles=rebuild_profiles)

    def has_isolated_selection(self) -> bool:
        return bool(self._isolated_selection)

    def get_isolated_selection(self) -> list:
        """Retourne une copie de la liste des éléments actuellement isolés."""
        return [dict(item) for item in (self._isolated_selection or [])]

    def get_visible_planar_eids(self) -> list:
        """Retourne les EIDs des éléments surfaciques actuellement visibles (filtres + isolation)."""
        indexes = self._filtered_planar_indexes()
        all_eids = list(self._model_data.get("planar_eids", []) or [])
        return [int(all_eids[i]) for i in indexes if 0 <= i < len(all_eids) and all_eids[i] is not None]

    def get_visible_linear_eids(self) -> list:
        """Retourne les EIDs des éléments filaires actuellement visibles (filtres + isolation)."""
        indexes = self._filtered_line_indexes()
        all_eids = list(self._model_data.get("line_eids", []) or [])
        return [int(all_eids[i]) for i in indexes if 0 <= i < len(all_eids) and all_eids[i] is not None]

    def refresh_mesh(self, all_nodes: list, all_connectivity_by_eid: dict):
        """Reconstruit le maillage VTK en ne gardant que les éléments visibles.

        Args:
            all_nodes: liste complète de (x, y, z) — positions de tous les nœuds FEM.
            all_connectivity_by_eid: dict {eid: [[n0,n1,n2], ...]} — faces par EID.
        """
        visible_planar = set(self.get_visible_planar_eids())
        visible_linear = set(self.get_visible_linear_eids())
        visible = visible_planar | visible_linear

        filtered_connectivity = []
        for eid, faces in (all_connectivity_by_eid or {}).items():
            if int(eid) in visible:
                filtered_connectivity.extend(faces)

        # S'assurer que le flag est activé avant de (re)construire l'acteur,
        # puisque load_mesh utilise _show_mesh pour fixer la visibilité initiale.
        self._show_mesh = True
        self.load_mesh(all_nodes, filtered_connectivity)

    def set_linear_result_scale_factor(self, scale_factor: float):
        try:
            value = float(scale_factor)
        except Exception:
            value = 1.0
        self._linear_result_scale_factor = max(0.1, min(10.0, value))

    def sizeHint(self):
        return QSize(900, 600)

    def minimumSizeHint(self):
        return QSize(400, 300)

