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
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QVBoxLayout

from viewer_config import (
    LINEAR_LOAD_COLOR, LINEAR_LOAD_SCALE, LINEAR_LOAD_ARROW_WIDTH,
    PLANAR_LOAD_COLOR, PLANAR_LOAD_SCALE, PLANAR_LOAD_ARROW_WIDTH,
    BG, PANEL, BORDER, ACCENT, ACCENT2, WARN, ERROR_COL,
    FG, FG_DIM, VTK_BG,
    LINEAR_LINE_WIDTH, PLANAR_LINE_WIDTH, OPENING_LINE_WIDTH, LOAD_AREA_LINE_WIDTH,
    SUPPORT_PUNCTUAL_SIZE, SUPPORT_PUNCTUAL_LINE_WIDTH,
    SUPPORT_LINEAR_LINE_WIDTH, SUPPORT_PLANAR_LINE_WIDTH,
    INITIAL_TRANSPARENCY_PERCENT,
    DEFAULT_VIEW_PROJECTION,
    MESH_LINE_WIDTH,
    MESH_COLOR,
    PUNCTUAL_LOAD_COLOR,
    PUNCTUAL_LOAD_SCALE,
    _DARK_VTK_BG,
)

from ad_model_data import _build_ad_local_axes, _cross_vector3, _normalize_vector3, _rotate_vector_around_axis

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
    ELEMENT_INDEX_ARRAY = "element_index"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.vtk_widget = QVTKRenderWindowInteractor(self)
        layout.addWidget(self.vtk_widget)

        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(*VTK_BG)

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
        self._planar_actor = None
        self._planar_faces_actor = None
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
        self.punctual_load_arrow_width = 0.04   # rayon de tige en mètres (défaut)
        self.punctual_load_count = 0

        self._linear_load_actors: list = []
        self._linear_load_data: list = []
        self._linear_load_case_filter: int | None = None
        self._show_linear_loads = False
        self.linear_load_scale = float(LINEAR_LOAD_SCALE)
        self.linear_load_color = tuple(LINEAR_LOAD_COLOR)
        self.linear_load_arrow_width = float(LINEAR_LOAD_ARROW_WIDTH)
        self.linear_load_count = 0

        self._planar_load_actors: list = []
        self._planar_load_data: list = []
        self._planar_load_case_filter: int | None = None
        self._show_planar_loads = False
        self.planar_load_scale = float(PLANAR_LOAD_SCALE)
        self.planar_load_color = tuple(PLANAR_LOAD_COLOR)
        self.planar_load_arrow_width = float(PLANAR_LOAD_ARROW_WIDTH)
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
        self._section_color_map = {}
        self._display_mode = "wire_hidden"

        self.lines_count = 0
        self.planars_count = 0
        self.load_areas_count = 0
        self.support_punctual_count = 0
        self.support_linear_count = 0
        self.support_planar_count = 0

        self._support_punctual_points = []

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
        self.planar_faces_base_opacity = 0.35
        self.load_areas_faces_base_opacity = 0.30
        self.support_planar_faces_base_opacity = 0.35
        self._filter_section_names = None
        self._filter_thickness_names = None
        self._filter_material_names = None
        self._isolated_selection = []   # liste de {"role","index"} — vide = pas d'isolation
        self._linear_result_scale_factor = 1.0
        self._projection_mode = DEFAULT_VIEW_PROJECTION

        self.orientation_widget = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.vtk_widget.setFocusPolicy(Qt.StrongFocus)

        self._build_scene_base()
        self.set_projection_mode(self._projection_mode)
        self.set_isometric_view()

        self.interactor.AddObserver("RightButtonPressEvent", self._on_right_button_press, 1.0)
        self.interactor.AddObserver("LeftButtonPressEvent", self._on_left_button_press, 1.0)
        self.interactor.AddObserver("LeftButtonReleaseEvent", self._on_left_button_release, 1.0)
        self.interactor.AddObserver("KeyPressEvent", self._on_key_press, 1.0)

        # Position du dernier press gauche — pour distinguer clic de glisser
        self._left_press_pos = None
        self._left_press_ctrl = False

        self.vtk_widget.Initialize()
        self.vtk_widget.Start()

    def apply_theme(self):
        self.setStyleSheet(f"border:1px solid {BORDER};")
        if hasattr(self, "_diagram_label_actors"):
            is_dark_theme = tuple(VTK_BG) == tuple(_DARK_VTK_BG)
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
        if hasattr(self, "renderer") and self.renderer is not None:
            self.renderer.SetBackground(*VTK_BG)
            if hasattr(self, "render_window") and self.render_window is not None:
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

        normal = None
        for i in range(1, len(outer) - 1):
            ax, ay, az = outer[0]
            bx, by, bz = outer[i]
            cx2, cy2, cz2 = outer[i + 1]
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx2 - ax, cy2 - ay, cz2 - az
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
        normals.AutoOrientNormalsOn()
        normals.SplittingOff()
        normals.Update()

        out = vtk.vtkPolyData()
        out.ShallowCopy(normals.GetOutput())
        return out

    def _build_punctual_supports_polydata(self, support_points):
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        elem_ids = self._make_int_array()
        pid = 0
        size = self.support_punctual_size

        for idx, point in enumerate(support_points or []):
            if not point or len(point) != 3:
                continue
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
                elem_ids.InsertNextValue(int(idx))

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

    def _get_pick_hit(self, x: int, y: int):
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.0035)
        picker.PickFromListOn()
        picker.InitializePickList()

        visible = False
        for info in self._pickable_actors.values():
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

        info = self._pickable_actors.get(self._actor_key(actor))
        if not info:
            return None

        polydata = self._get_actor_polydata(actor)
        if polydata is None:
            return None

        arr = polydata.GetCellData().GetArray(self.ELEMENT_INDEX_ARRAY)
        if arr is None or cell_id >= arr.GetNumberOfTuples():
            return None

        element_index = int(arr.GetTuple1(cell_id))
        return {
            "role": info["role"],
            "index": element_index,
            "actor": actor,
            "cell_id": cell_id,
        }

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
        found = {}
        for dx, dy in offsets:
            hit = self._get_pick_hit(x + dx, y + dy)
            if hit is None:
                continue
            key = (hit["role"], int(hit["index"]))
            dist2 = dx * dx + dy * dy
            current = found.get(key)
            if current is None or dist2 < current["distance2"]:
                hit["distance2"] = dist2
                found[key] = hit

        results = list(found.values())
        results.sort(key=lambda item: (item["distance2"], item["role"], item["index"]))
        return results

    def _clear_selection_overlay(self):
        for actor in list(self._selection_overlay_actors):
            self._remove_actor(actor)
        self._selection_overlay_actors = []

    def _selected_role_visible(self, role: str, face: bool = False):
        mode = self._display_mode
        show_faces = mode in ("hidden_faces", "wire_hidden", "full")
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
                face_poly = self._build_faces_polydata([item])
                face_actor = self._make_surface_actor(face_poly, self.selection_color, max(0.18, 0.30 * self._transparency_factor()))
                if face_actor:
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

        elif role == "punctual_load":
            # Reconstruire la flèche + arcs de moment en couleur de sélection
            import math
            loads = self._punctual_load_data
            if 0 <= index < len(loads):
                ld = loads[index]
                fx = float(ld.get("fx") or 0.0)
                fy = float(ld.get("fy") or 0.0)
                fz = float(ld.get("fz") or 0.0)
                f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
                ox, oy, oz = ld["pos"]

                # F_max et M_max sur la liste active (meme filtrage)
                active = [ld2 for ld2 in loads
                          if self._punctual_load_case_filter is None
                          or ld2.get("load_case_eid") == self._punctual_load_case_filter]
                f_max = max(
                    math.sqrt(float(l.get("fx") or 0)**2 + float(l.get("fy") or 0)**2 + float(l.get("fz") or 0)**2)
                    for l in active
                ) if active else max(f_res, 1e-9)
                m_max = max(
                    (abs(float(l.get(c) or 0)) for l in active for c in ("mx", "my", "mz")),
                    default=0.0,
                )

                shaft_r = max(0.005, self.punctual_load_arrow_width)

                # Fleche
                if f_max > 1e-9 and f_res > 1e-9:
                    length = f_res / f_max * self.punctual_load_scale
                    direction = (fx/f_res, fy/f_res, fz/f_res)
                    start = (ox - direction[0]*length, oy - direction[1]*length, oz - direction[2]*length)
                    actor = self._make_arrow_actor(
                        start, direction, length, self.selection_color,
                        shaft_radius_abs=shaft_r*1.3,
                        tip_radius_abs=shaft_r*2.5*1.3,
                        tip_length_abs=shaft_r*5.0,
                    )
                    if actor:
                        overlays.append(actor)

                # Arcs de moment
                if m_max > 1e-9:
                    for axis_idx, comp in enumerate(("mx", "my", "mz")):
                        m_val = float(ld.get(comp) or 0.0)
                        if abs(m_val) < 1e-9:
                            continue
                        radius = abs(m_val) / m_max * self.punctual_load_scale
                        sign   = 1 if m_val > 0 else -1
                        actor = self._make_moment_arc_actor(
                            (ox, oy, oz), axis_idx, radius, sign, self.selection_color,
                            tube_radius_abs=shaft_r*0.5*1.3,
                        )
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

        elif role == "linear_load":
            loads = self._linear_load_data
            if 0 <= index < len(loads):
                ld = loads[index]
                actor_pairs = self._build_linear_load_actors(
                    [ld],
                    self.linear_load_scale,
                    self.selection_color,
                    case_filter=None,
                    arrow_width=self.linear_load_arrow_width * 1.3,
                    global_data=self._linear_load_data,
                )
                for a, _ in actor_pairs:
                    overlays.append(a)

        elif role == "planar_load":
            loads = self._planar_load_data
            if 0 <= index < len(loads):
                ld = loads[index]
                actor_pairs = self._build_planar_load_actors(
                    [ld],
                    self.planar_load_scale,
                    self.selection_color,
                    case_filter=None,
                    arrow_width=self.planar_load_arrow_width * 1.3,
                    global_data=self._planar_load_data,
                )
                for a, _ in actor_pairs:
                    overlays.append(a)

        return overlays

    def _refresh_selection_overlay(self):
        self._clear_selection_overlay()
        if not self._selected_items:
            self.render_window.Render()
            return
        for item in self._selected_items:
            overlays = self._make_selection_overlay_actors(item["role"], item["index"])
            for actor in overlays:
                self.renderer.AddActor(actor)
                self._actors.append(actor)
                self._selection_overlay_actors.append(actor)
        self._apply_visibility_state()

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

    def _build_linear_diagram_actors(self, line_points, series, title: str = "", line_property: dict = None, unit: str = ""):
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
            rebuilt = _build_ad_local_axes(p1, p2, (line_property or {}).get("section_orientation_angle_deg", 0.0) if isinstance(line_property, dict) else 0.0)
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
            if abs(value) < 0.001:
                formatted = "+0" if value >= 0.0 else "-0"
            else:
                formatted = f"{value:.3f}"
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
            is_dark_theme = tuple(VTK_BG) == tuple(_DARK_VTK_BG)
            applied_color = (1.0, 1.0, 1.0) if is_dark_theme else color
            text_prop.SetColor(*applied_color)
            actor._diagram_original_color = tuple(color)
            actor.PickableOff()
            self.renderer.AddActor(actor)
            self._actors.append(actor)
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

    def set_linear_result_diagram(self, line_points, series, title: str = "", line_property: dict = None, unit: str = ""):
        """Remplace le diagramme courant (clear + reconstruction d'un seul élément)."""
        self.clear_result_diagram()
        actors = self._build_linear_diagram_actors(line_points, series, title, line_property, unit=unit)
        self._diagram_overlay_actors = actors
        self.render_window.Render()

    def add_linear_result_diagram(self, line_points, series, title: str = "", line_property: dict = None, unit: str = ""):
        """Ajoute un diagramme filaire SANS effacer les diagrammes existants.

        Utilisé pour la sélection multiple de filaires : chaque filaire est
        chargé séquentiellement et superposé dans la vue.
        Les acteurs sont ajoutés directement au renderer, puis enregistrés
        dans _diagram_overlay_actors pour que clear_result_diagram() les retire.
        """
        actors = self._build_linear_diagram_actors(line_points, series, title, line_property, unit=unit)
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

    def _on_right_button_press(self, obj, event):
        self.vtk_widget.setFocus()
        x, y = self.interactor.GetEventPosition()
        ctrl = bool(self.interactor.GetControlKey())
        candidates = self._pick_selection_candidates(x, y)
        if candidates:
            candidate_keys = [(c["role"], int(c["index"])) for c in candidates]
            if not ctrl and candidate_keys == self._selection_candidate_keys:
                self._selection_cycle_index = (self._selection_cycle_index + 1) % len(candidates)
            else:
                self._selection_candidates = candidates
                self._selection_candidate_keys = candidate_keys
                self._selection_cycle_index = 0
            selected = candidates[self._selection_cycle_index]
            self._select_item(selected["role"], selected["index"], additive=ctrl)
            return
        self.interactor_style.OnRightButtonDown()

    def _on_left_button_press(self, obj, event):
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
        self.interactor_style.OnLeftButtonDown()

    def _on_left_button_release(self, obj, event):
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

    def _on_key_press(self, obj, event):
        key = self.interactor.GetKeySym() if self.interactor is not None else ""
        if key in ("Escape", "escape"):
            self.clear_selection()
            return

    def get_selected_items(self) -> list:
        """Retourne la liste des items actuellement sélectionnés : [{"role", "index"}, ...]."""
        return list(self._selected_items)

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

    def _build_scene_base(self):
        light = vtk.vtkLight()
        light.SetLightTypeToSceneLight()
        light.SetPosition(50, 50, 80)
        light.SetFocalPoint(0, 0, 0)
        light.SetIntensity(0.9)
        self.renderer.AddLight(light)
        self._setup_corner_axes()

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
        widget.SetViewport(0.02, 0.02, 0.12, 0.12)
        widget.SetEnabled(1)
        widget.InteractiveOff()
        self.orientation_widget = widget

    def clear_scene(self):
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
        self._planar_actor = None
        self._planar_faces_actor = None
        self._openings_actor = None
        self._load_areas_actor = None
        self._load_areas_faces_actor = None
        self._support_punctual_actor = None
        self._support_linear_actor = None
        self._support_planar_actor = None
        self._support_planar_faces_actor = None
        self._support_planar_centroid_actor = None
        self._support_punctual_points = []
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
        self._apply_visibility_state()

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
        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def _get_visible_bounds(self):
        bounds = [0.0] * 6
        self.renderer.ComputeVisiblePropBounds(bounds)
        if bounds[0] > bounds[1] or bounds[2] > bounds[3] or bounds[4] > bounds[5]:
            return None
        if not all(math.isfinite(v) for v in bounds):
            return None
        return bounds

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
        bounds = self._get_visible_bounds()
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
        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def _set_axis_view(self, direction, up=(0.0, 0.0, 1.0)):
        bounds = self._get_visible_bounds()
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
        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

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

    def _apply_face_opacity_state(self):
        if self._display_mode == "full":
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
        show_faces = mode in ("hidden_faces", "wire_hidden", "full")
        show_planar_wire = mode in ("wireframe", "wire_hidden")
        show_openings = mode in ("wireframe", "hidden_faces", "wire_hidden")
        self.renderer.SetUseHiddenLineRemoval(1 if show_faces else 0)

        if self._lines_actor:
            self._lines_actor.SetVisibility(1 if self._show_lines else 0)
        if self._planar_actor:
            self._planar_actor.SetVisibility(1 if (self._show_planars and show_planar_wire) else 0)
        if self._planar_faces_actor:
            self._planar_faces_actor.SetVisibility(1 if (self._show_planars and show_faces) else 0)
        if self._openings_actor:
            self._openings_actor.SetVisibility(1 if (self._show_planars and show_openings) else 0)
        if self._load_areas_actor:
            self._load_areas_actor.SetVisibility(1 if (self._show_load_areas and show_planar_wire) else 0)
        if self._load_areas_faces_actor:
            self._load_areas_faces_actor.SetVisibility(1 if (self._show_load_areas and show_faces) else 0)
        if self._support_punctual_actor:
            self._support_punctual_actor.SetVisibility(1 if self._show_support_punctual else 0)
        if self._support_linear_actor:
            self._support_linear_actor.SetVisibility(1 if self._show_support_linear else 0)
        if self._support_planar_actor:
            self._support_planar_actor.SetVisibility(1 if (self._show_support_planar and show_planar_wire) else 0)
        if self._support_planar_faces_actor:
            self._support_planar_faces_actor.SetVisibility(1 if (self._show_support_planar and show_faces) else 0)
        if self._support_planar_centroid_actor:
            self._support_planar_centroid_actor.SetVisibility(1 if self._show_support_planar else 0)

        for actor in self._selection_overlay_actors:
            opacity = actor.GetProperty().GetOpacity() if actor.GetProperty() is not None else 1.0
            face_like = opacity < 1.0
            role = self._selected_item["role"] if self._selected_item else ""
            actor.SetVisibility(1 if self._selected_role_visible(role, face=face_like) else 0)

        if self._mesh_actor:
            self._mesh_actor.SetVisibility(1 if self._show_mesh else 0)

        self._apply_face_opacity_state()
        self.render_window.Render()

    def _set_visible_flag(self, attr: str, visible: bool):
        """Helper commun : met a jour un attribut de visibilite et applique l'etat."""
        setattr(self, attr, visible)
        self._apply_visibility_state()

    def set_show_lines(self, visible: bool):
        self._set_visible_flag("_show_lines", visible)

    def set_show_planars(self, visible: bool):
        self._set_visible_flag("_show_planars", visible)

    def set_show_load_areas(self, visible: bool):
        self._set_visible_flag("_show_load_areas", visible)

    def set_show_support_punctual(self, visible: bool):
        self._set_visible_flag("_show_support_punctual", visible)

    def set_show_support_linear(self, visible: bool):
        self._set_visible_flag("_show_support_linear", visible)

    def set_show_support_planar(self, visible: bool):
        self._set_visible_flag("_show_support_planar", visible)

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
        self.render_window.Render()

    def set_display_mode(self, mode: str):
        if mode not in ("wireframe", "hidden_faces", "wire_hidden", "full"):
            mode = "wireframe"
        self._display_mode = mode
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
        if display_mode not in ("wireframe", "hidden_faces", "wire_hidden", "full"):
            display_mode = "wireframe"

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

        # Appliquer l'orientation_widget (logique propre à show_marker,
        # normalement dans set_show_marker)
        if self.orientation_widget:
            if show_marker:
                self.orientation_widget.SetEnabled(1)
                self.orientation_widget.InteractiveOff()
            else:
                self.orientation_widget.SetEnabled(0)

        # Un seul appel — il enchaîne _apply_face_opacity_state() + Render()
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
                self._build_punctual_supports_polydata(self._support_punctual_points),
                self.support_punctual_color,
                self.support_punctual_line_width,
            )
            self._replace_actor("_support_punctual_actor", actor, role="support_punctual", pickable=True)

        self._apply_visibility_state()
        self._refresh_selection_overlay()

    # ------------------------------------------------------------------
    # Charges ponctuelles — rendu VTK
    # ------------------------------------------------------------------

    def _make_arrow_actor(self, origin, direction, length, color,
                          shaft_radius_abs=0.04, tip_radius_abs=0.10, tip_length_abs=0.20,
                          element_index: int = -1):
        """Crée un acteur flèche VTK orientée depuis origin dans direction, de longueur length.

        shaft_radius_abs, tip_radius_abs, tip_length_abs : dimensions absolues en mètres.
        element_index : si >= 0, injecté dans les cell data pour le picking.
        """
        import math

        dx, dy, dz = direction
        norm = math.sqrt(dx*dx + dy*dy + dz*dz)
        if norm < 1e-9:
            return None
        dx, dy, dz = dx/norm, dy/norm, dz/norm

        eff_length = max(length, tip_length_abs * 1.05)
        tip_frac = tip_length_abs / eff_length
        tip_frac = max(0.05, min(0.95, tip_frac))
        shaft_r_frac = shaft_radius_abs / eff_length
        tip_r_frac   = tip_radius_abs   / eff_length

        arrow_src = vtk.vtkArrowSource()
        arrow_src.SetShaftRadius(shaft_r_frac)
        arrow_src.SetTipRadius(tip_r_frac)
        arrow_src.SetTipLength(tip_frac)
        arrow_src.SetShaftResolution(12)
        arrow_src.SetTipResolution(12)
        arrow_src.Update()

        dot = max(-1.0, min(1.0, dx))
        ax, ay, az = 0.0, -dz, dy
        ax_norm = math.sqrt(ax*ax + ay*ay + az*az)

        transform = vtk.vtkTransform()
        transform.Translate(*origin)
        transform.Scale(eff_length, eff_length, eff_length)
        if ax_norm > 1e-9:
            angle_deg = math.degrees(math.acos(dot))
            transform.RotateWXYZ(angle_deg, ax/ax_norm, ay/ax_norm, az/ax_norm)
        elif dot < 0:
            transform.RotateWXYZ(180.0, 0.0, 0.0, 1.0)

        tf_filter = vtk.vtkTransformPolyDataFilter()
        tf_filter.SetInputConnection(arrow_src.GetOutputPort())
        tf_filter.SetTransform(transform)
        tf_filter.Update()

        polydata = tf_filter.GetOutput()

        # Injecter l'index élément dans les cell data pour le picking
        if element_index >= 0:
            num_cells = polydata.GetNumberOfCells()
            elem_ids = self._make_int_array()
            for _ in range(num_cells):
                elem_ids.InsertNextValue(element_index)
            polydata.GetCellData().AddArray(elem_ids)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetAmbient(0.3)
        actor.GetProperty().SetDiffuse(0.7)
        return actor

    def _make_moment_arc_actor(self, center, axis, radius, sign, color, element_index: int = -1,
                               tube_radius_abs=0.015, arc_degrees=270.0, n_segments=32):
        """Crée un acteur arc de cercle représentant un moment.

        center      : (x, y, z) — point d'application
        axis        : 0=X, 1=Y, 2=Z — axe autour duquel tourne le moment
        radius      : rayon de l'arc en mètres
        sign        : +1 ou -1 — sens de rotation (détermine l'orientation de la flèche)
        tube_radius_abs : rayon du tube en mètres
        arc_degrees : ouverture de l'arc (270° comme dans AD)
        """
        import math

        # Points de l'arc dans le plan perpendiculaire à axis
        # axis=0 (X) → plan YZ, axis=1 (Y) → plan XZ, axis=2 (Z) → plan XY
        cx, cy, cz = center
        points_vtk = vtk.vtkPoints()
        lines_vtk  = vtk.vtkCellArray()
        elem_ids   = self._make_int_array()

        # Vecteurs du plan de l'arc selon l'axe
        if axis == 0:    # autour de X → plan YZ
            u = (0.0,  1.0, 0.0)
            v = (0.0,  0.0, 1.0)
        elif axis == 1:  # autour de Y → plan XZ
            u = (1.0,  0.0, 0.0)
            v = (0.0,  0.0, 1.0)
        else:            # autour de Z → plan XY
            u = (1.0,  0.0, 0.0)
            v = (0.0,  1.0, 0.0)

        # Avec signe : le sens de progression de l'arc change
        if sign < 0:
            v = (-v[0], -v[1], -v[2])

        start_angle = 45.0   # décalage de départ pour que la flèche soit visible
        arc_rad = math.radians(arc_degrees)
        pts = []
        for i in range(n_segments + 1):
            t = start_angle + math.degrees(arc_rad * i / n_segments)
            t_rad = math.radians(t)
            cos_t, sin_t = math.cos(t_rad), math.sin(t_rad)
            px = cx + radius * (u[0]*cos_t + v[0]*sin_t)
            py = cy + radius * (u[1]*cos_t + v[1]*sin_t)
            pz = cz + radius * (u[2]*cos_t + v[2]*sin_t)
            pid = points_vtk.InsertNextPoint(px, py, pz)
            pts.append(pid)

        for i in range(len(pts) - 1):
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, pts[i])
            line.GetPointIds().SetId(1, pts[i+1])
            lines_vtk.InsertNextCell(line)
            elem_ids.InsertNextValue(element_index)

        # Pointe de flèche à l'extrémité de l'arc (petite flèche tangentielle)
        # Direction tangente au dernier point
        t_end = math.radians(start_angle + arc_degrees)
        t_pen = math.radians(start_angle + arc_degrees - 5.0)
        tip_len = radius * 0.18

        # Point final
        end_x = cx + radius * (u[0]*math.cos(t_end) + v[0]*math.sin(t_end))
        end_y = cy + radius * (u[1]*math.cos(t_end) + v[1]*math.sin(t_end))
        end_z = cz + radius * (u[2]*math.cos(t_end) + v[2]*math.sin(t_end))

        # Tangente (direction de la flèche) : normaliser end - pen
        pen_x = cx + radius * (u[0]*math.cos(t_pen) + v[0]*math.sin(t_pen))
        pen_y = cy + radius * (u[1]*math.cos(t_pen) + v[1]*math.sin(t_pen))
        pen_z = cz + radius * (u[2]*math.cos(t_pen) + v[2]*math.sin(t_pen))
        tang = (end_x - pen_x, end_y - pen_y, end_z - pen_z)
        tang_n = math.sqrt(tang[0]**2 + tang[1]**2 + tang[2]**2)
        if tang_n > 1e-9:
            tang = (tang[0]/tang_n, tang[1]/tang_n, tang[2]/tang_n)

        # Deux barbes de la flèche, dans le plan de l'arc
        # Normale au plan : axe lui-même
        if axis == 0:   norm = (1.0, 0.0, 0.0)
        elif axis == 1: norm = (0.0, 1.0, 0.0)
        else:           norm = (0.0, 0.0, 1.0)

        # Barbe 1 : tang × norm
        b1 = (tang[1]*norm[2]-tang[2]*norm[1], tang[2]*norm[0]-tang[0]*norm[2], tang[0]*norm[1]-tang[1]*norm[0])
        b1_n = math.sqrt(b1[0]**2+b1[1]**2+b1[2]**2)
        if b1_n > 1e-9:
            b1 = (b1[0]/b1_n * tip_len, b1[1]/b1_n * tip_len, b1[2]/b1_n * tip_len)
            for barbe in (b1, (-b1[0], -b1[1], -b1[2])):
                p_barb = (end_x - tang[0]*tip_len + barbe[0],
                          end_y - tang[1]*tip_len + barbe[1],
                          end_z - tang[2]*tip_len + barbe[2])
                pid_end  = points_vtk.InsertNextPoint(end_x, end_y, end_z)
                pid_barb = points_vtk.InsertNextPoint(*p_barb)
                line = vtk.vtkLine()
                line.GetPointIds().SetId(0, pid_end)
                line.GetPointIds().SetId(1, pid_barb)
                lines_vtk.InsertNextCell(line)
                elem_ids.InsertNextValue(element_index)

        poly = vtk.vtkPolyData()
        poly.SetPoints(points_vtk)
        poly.SetLines(lines_vtk)
        poly.GetCellData().AddArray(elem_ids)

        # Tube pour épaissir l'arc
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(poly)
        tube.SetRadius(max(0.003, tube_radius_abs))
        tube.SetNumberOfSides(8)
        tube.CappingOn()
        tube.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tube.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetAmbient(0.3)
        actor.GetProperty().SetDiffuse(0.7)
        return actor

    def _build_punctual_load_polydata_batch(self, loads: list, scale: float,
                                             case_filter=None, arrow_width: float = 0.04):
        """Construit les polydata batchés pour les charges ponctuelles (thread-safe).

        Retourne un dict:
          'arrows' : vtkPolyData fusionné (fleches + arcs), ou None
        """
        import math

        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return {"arrows": None}

        resultants = []
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            resultants.append((fx, fy, fz, math.sqrt(fx*fx + fy*fy + fz*fz)))

        f_max = max((r[3] for r in resultants), default=0.0)
        m_max = 0.0
        for ld in active:
            for comp in ("mx", "my", "mz"):
                v = abs(float(ld.get(comp) or 0.0))
                if v > m_max:
                    m_max = v

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        ARROW_SHAFT_RES = 8
        ARROW_TIP_RES   = 8
        TUBE_SIDES      = 8
        ARC_SEGS        = 24

        append_all = vtk.vtkAppendPolyData()
        has_any = False

        def _arrow_pd(origin, direction, length, element_index):
            dx, dy, dz = direction
            n = math.sqrt(dx*dx + dy*dy + dz*dz)
            if n < 1e-9:
                return None
            dx, dy, dz = dx/n, dy/n, dz/n
            eff_length = max(length, tip_l * 1.05)
            tip_frac = max(0.05, min(0.95, tip_l / eff_length))
            src = vtk.vtkArrowSource()
            src.SetShaftRadius(shaft_r / eff_length)
            src.SetTipRadius(tip_r / eff_length)
            src.SetTipLength(tip_frac)
            src.SetShaftResolution(ARROW_SHAFT_RES)
            src.SetTipResolution(ARROW_TIP_RES)
            src.Update()
            dot = max(-1.0, min(1.0, dx))
            ax, ay, az = 0.0, -dz, dy
            ax_norm = math.sqrt(ax*ax + ay*ay + az*az)
            t = vtk.vtkTransform()
            t.Translate(*origin)
            t.Scale(eff_length, eff_length, eff_length)
            if ax_norm > 1e-9:
                t.RotateWXYZ(math.degrees(math.acos(dot)), ax/ax_norm, ay/ax_norm, az/ax_norm)
            elif dot < 0:
                t.RotateWXYZ(180.0, 0.0, 0.0, 1.0)
            tf = vtk.vtkTransformPolyDataFilter()
            tf.SetInputConnection(src.GetOutputPort())
            tf.SetTransform(t)
            tf.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tf.GetOutput())
            if element_index >= 0:
                ids = self._make_int_array()
                for _ in range(pd.GetNumberOfCells()):
                    ids.InsertNextValue(element_index)
                pd.GetCellData().AddArray(ids)
            return pd

        def _arc_pd(center, axis, radius, sign, element_index):
            cx, cy, cz = center
            if axis == 0:
                u, v_vec = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (1.0, 0.0, 0.0)
            elif axis == 1:
                u, v_vec = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (0.0, 1.0, 0.0)
            else:
                u, v_vec = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
                norm_ax = (0.0, 0.0, 1.0)
            if sign < 0:
                v_vec = (-v_vec[0], -v_vec[1], -v_vec[2])
            start_a = 45.0
            arc_deg = 270.0
            arc_rad = math.radians(arc_deg)
            pts_list = []
            points_vtk = vtk.vtkPoints()
            lines_vtk = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for i in range(ARC_SEGS + 1):
                t = start_a + math.degrees(arc_rad * i / ARC_SEGS)
                tr = math.radians(t)
                c, s = math.cos(tr), math.sin(tr)
                pid = points_vtk.InsertNextPoint(
                    cx + radius * (u[0]*c + v_vec[0]*s),
                    cy + radius * (u[1]*c + v_vec[1]*s),
                    cz + radius * (u[2]*c + v_vec[2]*s),
                )
                pts_list.append(pid)
            for i in range(len(pts_list) - 1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, pts_list[i])
                seg.GetPointIds().SetId(1, pts_list[i+1])
                lines_vtk.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            t_end = math.radians(start_a + arc_deg)
            t_pen = math.radians(start_a + arc_deg - 5.0)
            tip_len = radius * 0.18
            ex = cx + radius * (u[0]*math.cos(t_end) + v_vec[0]*math.sin(t_end))
            ey = cy + radius * (u[1]*math.cos(t_end) + v_vec[1]*math.sin(t_end))
            ez = cz + radius * (u[2]*math.cos(t_end) + v_vec[2]*math.sin(t_end))
            px = cx + radius * (u[0]*math.cos(t_pen) + v_vec[0]*math.sin(t_pen))
            py = cy + radius * (u[1]*math.cos(t_pen) + v_vec[1]*math.sin(t_pen))
            pz = cz + radius * (u[2]*math.cos(t_pen) + v_vec[2]*math.sin(t_pen))
            tang = (ex-px, ey-py, ez-pz)
            tn = math.sqrt(tang[0]**2+tang[1]**2+tang[2]**2)
            if tn > 1e-9:
                tang = (tang[0]/tn, tang[1]/tn, tang[2]/tn)
            b1 = (tang[1]*norm_ax[2]-tang[2]*norm_ax[1], tang[2]*norm_ax[0]-tang[0]*norm_ax[2], tang[0]*norm_ax[1]-tang[1]*norm_ax[0])
            b1n = math.sqrt(b1[0]**2+b1[1]**2+b1[2]**2)
            if b1n > 1e-9:
                b1 = (b1[0]/b1n*tip_len, b1[1]/b1n*tip_len, b1[2]/b1n*tip_len)
                for barb in (b1, (-b1[0], -b1[1], -b1[2])):
                    pb = (ex-tang[0]*tip_len+barb[0], ey-tang[1]*tip_len+barb[1], ez-tang[2]*tip_len+barb[2])
                    pe = points_vtk.InsertNextPoint(ex, ey, ez)
                    pb_ = points_vtk.InsertNextPoint(*pb)
                    seg = vtk.vtkLine()
                    seg.GetPointIds().SetId(0, pe)
                    seg.GetPointIds().SetId(1, pb_)
                    lines_vtk.InsertNextCell(seg)
                    ids_arr.InsertNextValue(element_index)
            poly = vtk.vtkPolyData()
            poly.SetPoints(points_vtk)
            poly.SetLines(lines_vtk)
            poly.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(poly)
            tube.SetRadius(max(0.003, tube_r))
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        for ld, (fx, fy, fz, f_res) in zip(active, resultants):
            global_idx = self._punctual_load_data.index(ld) if ld in self._punctual_load_data else 0
            ox, oy, oz = ld["pos"]
            if f_max > 1e-9 and f_res > 1e-9:
                direction = (fx/f_res, fy/f_res, fz/f_res)
                length = f_res / f_max * scale
                start = (ox - direction[0]*length, oy - direction[1]*length, oz - direction[2]*length)
                pd = _arrow_pd(start, direction, length, global_idx)
                if pd is not None:
                    append_all.AddInputData(pd)
                    has_any = True
            if m_max > 1e-9:
                for axis_idx, comp in enumerate(("mx", "my", "mz")):
                    m_val = float(ld.get(comp) or 0.0)
                    if abs(m_val) < 1e-9:
                        continue
                    radius = abs(m_val) / m_max * scale
                    sign   = 1 if m_val > 0 else -1
                    pd = _arc_pd((ox, oy, oz), axis_idx, radius, sign, global_idx)
                    if pd is not None:
                        append_all.AddInputData(pd)
                        has_any = True

        if not has_any:
            return {"arrows": None}
        append_all.Update()
        result_pd = vtk.vtkPolyData()
        result_pd.DeepCopy(append_all.GetOutput())
        return {"arrows": result_pd}

    def _build_punctual_load_actors(self, loads: list, scale: float, color: tuple, case_filter=None, arrow_width: float = 0.04) -> list:
        """Construit les acteurs pour les charges ponctuelles (forces + moments).

        Forces  : une fleche resultante par charge, longueur proportionnelle a |F|/F_max.
        Moments : un arc de cercle par composante non nulle (Mx, My, Mz),
                  rayon proportionnel a |M|/M_max, independant de l'echelle des forces.
        Retourne une liste de (actor, global_idx).
        """
        import math

        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return []

        # Normalisation forces
        resultants = []
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            resultants.append((fx, fy, fz, math.sqrt(fx*fx + fy*fy + fz*fz)))

        f_max = max((r[3] for r in resultants), default=0.0)

        # Normalisation moments
        m_max = 0.0
        for ld in active:
            for comp in ("mx", "my", "mz"):
                v = abs(float(ld.get(comp) or 0.0))
                if v > m_max:
                    m_max = v

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        actors = []

        for ld, (fx, fy, fz, f_res) in zip(active, resultants):
            global_idx = self._punctual_load_data.index(ld) if ld in self._punctual_load_data else 0
            ox, oy, oz = ld["pos"]

            # Fleche resultante
            if f_max > 1e-9 and f_res > 1e-9:
                direction = (fx/f_res, fy/f_res, fz/f_res)
                length = f_res / f_max * scale
                start = (ox - direction[0]*length, oy - direction[1]*length, oz - direction[2]*length)
                actor = self._make_arrow_actor(
                    start, direction, length, color,
                    shaft_radius_abs=shaft_r, tip_radius_abs=tip_r, tip_length_abs=tip_l,
                    element_index=global_idx,
                )
                if actor:
                    actors.append((actor, global_idx))

            # Arcs de moment
            if m_max > 1e-9:
                for axis_idx, comp in enumerate(("mx", "my", "mz")):
                    m_val = float(ld.get(comp) or 0.0)
                    if abs(m_val) < 1e-9:
                        continue
                    radius = abs(m_val) / m_max * scale
                    sign   = 1 if m_val > 0 else -1
                    actor = self._make_moment_arc_actor(
                        (ox, oy, oz), axis_idx, radius, sign, color,
                        element_index=global_idx,
                        tube_radius_abs=tube_r,
                    )
                    if actor:
                        actors.append((actor, global_idx))

        return actors

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
            self.punctual_load_scale,
            self.punctual_load_color,
            case_filter=self._punctual_load_case_filter,
            arrow_width=self.punctual_load_arrow_width,
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

    def set_punctual_load_style(self, color: tuple, arrow_width: float):
        """Applique couleur et épaisseur (rayon tige en m) aux flèches de charges ponctuelles."""
        self.punctual_load_color = tuple(float(v) for v in color)
        self.punctual_load_arrow_width = max(0.005, float(arrow_width))
        if self._show_punctual_loads and self._punctual_load_data:
            self._rebuild_punctual_load_actors()

    # ------------------------------------------------------------------
    # Charges linéaires
    # ------------------------------------------------------------------

    def _build_linear_load_actors(self, loads: list, scale: float, color: tuple,
                                   case_filter=None, arrow_width: float = 0.02,
                                   global_data: list = None) -> list:
        """Construit les acteurs pour les charges linéaires — version batch optimisée.

        Toute la géométrie (fleches + tubes) est fusionnée en 2 acteurs au total
        via vtkAppendPolyData, quel que soit le nombre de charges. Cela évite les
        milliers d'acteurs individuels qui pénalisent VTK à la rotation.

        global_data : liste de référence pour le calcul des index globaux (utile en isolation).
                      Si None, on utilise self._linear_load_data.
        """
        import math

        ref_data = global_data if global_data is not None else self._linear_load_data
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return []

        NB_SEGMENTS = 8
        # Résolutions réduites pour les charges linéaires (nombreuses) — assez pour la lisibilité
        ARROW_SHAFT_RES = 6
        ARROW_TIP_RES   = 6
        TUBE_SIDES      = 6
        ARC_SEGS        = 20

        # Calcul des valeurs max sur toutes les charges actives pour normalisation
        f_max = 0.0
        m_max = 0.0
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            mx = float(ld.get("mx") or 0.0)
            my = float(ld.get("my") or 0.0)
            mz = float(ld.get("mz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            m_res = math.sqrt(mx*mx + my*my + mz*mz)
            f_max = max(f_max, f_res * abs(c1), f_res * abs(c2))
            m_max = max(m_max, m_res * abs(c1), m_res * abs(c2))

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        # Accumulateurs batch : un pour les fleches (surface), un pour les tubes (lignes+arcs)
        append_arrows = vtk.vtkAppendPolyData()
        append_tubes  = vtk.vtkAppendPolyData()
        has_arrows = False
        has_tubes  = False

        def _arrow_polydata(origin, direction, length, element_index):
            """Retourne le polydata d'une fleche transformée, avec cell data d'index."""
            dx, dy, dz = direction
            n = math.sqrt(dx*dx + dy*dy + dz*dz)
            if n < 1e-9:
                return None
            dx, dy, dz = dx/n, dy/n, dz/n
            eff_length = max(length, tip_l * 1.05)
            tip_frac   = max(0.05, min(0.95, tip_l / eff_length))
            src = vtk.vtkArrowSource()
            src.SetShaftRadius(shaft_r / eff_length)
            src.SetTipRadius(tip_r / eff_length)
            src.SetTipLength(tip_frac)
            src.SetShaftResolution(ARROW_SHAFT_RES)
            src.SetTipResolution(ARROW_TIP_RES)
            src.Update()
            dot = max(-1.0, min(1.0, dx))
            ax, ay, az = 0.0, -dz, dy
            ax_norm = math.sqrt(ax*ax + ay*ay + az*az)
            t = vtk.vtkTransform()
            t.Translate(*origin)
            t.Scale(eff_length, eff_length, eff_length)
            if ax_norm > 1e-9:
                t.RotateWXYZ(math.degrees(math.acos(dot)), ax/ax_norm, ay/ax_norm, az/ax_norm)
            elif dot < 0:
                t.RotateWXYZ(180.0, 0.0, 0.0, 1.0)
            tf = vtk.vtkTransformPolyDataFilter()
            tf.SetInputConnection(src.GetOutputPort())
            tf.SetTransform(t)
            tf.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tf.GetOutput())
            if element_index >= 0:
                ids = self._make_int_array()
                for _ in range(pd.GetNumberOfCells()):
                    ids.InsertNextValue(element_index)
                pd.GetCellData().AddArray(ids)
            return pd

        def _tube_polydata(points_list, element_index, radius):
            """Retourne le polydata tubé d'une polyligne (liste de tuples (x,y,z))."""
            if len(points_list) < 2:
                return None
            pts = vtk.vtkPoints()
            lines = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in points_list:
                pts.InsertNextPoint(*p)
            for j in range(len(points_list) - 1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j + 1)
                lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(pts)
            raw.SetLines(lines)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(radius)
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        def _arc_polydata(center, axis, radius, sign, element_index):
            """Retourne le polydata tubé d'un arc de moment."""
            cx, cy, cz = center
            if axis == 0:
                u, v = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (1.0, 0.0, 0.0)
            elif axis == 1:
                u, v = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (0.0, 1.0, 0.0)
            else:
                u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
                norm_ax = (0.0, 0.0, 1.0)
            if sign < 0:
                v = (-v[0], -v[1], -v[2])
            start_angle = 45.0
            arc_deg = 270.0
            arc_rad = math.radians(arc_deg)
            pts_list = []
            for i in range(ARC_SEGS + 1):
                t = start_angle + math.degrees(arc_rad * i / ARC_SEGS)
                tr = math.radians(t)
                c, s = math.cos(tr), math.sin(tr)
                pts_list.append((
                    cx + radius * (u[0]*c + v[0]*s),
                    cy + radius * (u[1]*c + v[1]*s),
                    cz + radius * (u[2]*c + v[2]*s),
                ))
            # Pointe de fleche
            t_end = math.radians(start_angle + arc_deg)
            t_pen = math.radians(start_angle + arc_deg - 5.0)
            tip_len = radius * 0.18
            ex = cx + radius * (u[0]*math.cos(t_end) + v[0]*math.sin(t_end))
            ey = cy + radius * (u[1]*math.cos(t_end) + v[1]*math.sin(t_end))
            ez = cz + radius * (u[2]*math.cos(t_end) + v[2]*math.sin(t_end))
            px = cx + radius * (u[0]*math.cos(t_pen) + v[0]*math.sin(t_pen))
            py = cy + radius * (u[1]*math.cos(t_pen) + v[1]*math.sin(t_pen))
            pz = cz + radius * (u[2]*math.cos(t_pen) + v[2]*math.sin(t_pen))
            tang = (ex-px, ey-py, ez-pz)
            tn = math.sqrt(tang[0]**2+tang[1]**2+tang[2]**2)
            if tn > 1e-9:
                tang = (tang[0]/tn, tang[1]/tn, tang[2]/tn)
            b1 = (tang[1]*norm_ax[2]-tang[2]*norm_ax[1],
                  tang[2]*norm_ax[0]-tang[0]*norm_ax[2],
                  tang[0]*norm_ax[1]-tang[1]*norm_ax[0])
            b1n = math.sqrt(b1[0]**2+b1[1]**2+b1[2]**2)
            barb_lines = []
            if b1n > 1e-9:
                b1 = (b1[0]/b1n*tip_len, b1[1]/b1n*tip_len, b1[2]/b1n*tip_len)
                for barb in (b1, (-b1[0],-b1[1],-b1[2])):
                    pb = (ex-tang[0]*tip_len+barb[0], ey-tang[1]*tip_len+barb[1], ez-tang[2]*tip_len+barb[2])
                    barb_lines.append([(ex,ey,ez), pb])
            # Assembler arc + barbes dans un seul polydata puis tuber
            all_pts = vtk.vtkPoints()
            all_lines = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in pts_list:
                all_pts.InsertNextPoint(*p)
            for j in range(len(pts_list)-1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j+1)
                all_lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            for seg_pts in barb_lines:
                i0 = all_pts.InsertNextPoint(*seg_pts[0])
                i1 = all_pts.InsertNextPoint(*seg_pts[1])
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, i0)
                seg.GetPointIds().SetId(1, i1)
                all_lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(all_pts)
            raw.SetLines(all_lines)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(max(0.003, tube_r))
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        # --- Boucle principale : accumulation batch ---
        for ld in active:
            try:
                global_idx = ref_data.index(ld)
            except ValueError:
                global_idx = 0

            pt_start = ld["pt_start"]
            pt_end   = ld["pt_end"]
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            mx = float(ld.get("mx") or 0.0)
            my = float(ld.get("my") or 0.0)
            mz = float(ld.get("mz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)

            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            m_res = math.sqrt(mx*mx + my*my + mz*mz)
            has_force  = f_max > 1e-9 and f_res > 1e-9
            has_moment = m_max > 1e-9 and m_res > 1e-9

            if has_force:
                f_dir = (fx/f_res, fy/f_res, fz/f_res)
            if has_moment:
                moment_axes = [
                    (ax_idx, mval)
                    for ax_idx, mval in enumerate([mx, my, mz])
                    if abs(mval) > 1e-9
                ]

            arrow_origins = []

            for i in range(NB_SEGMENTS + 1):
                t = i / NB_SEGMENTS
                ox = pt_start[0] + t * (pt_end[0] - pt_start[0])
                oy = pt_start[1] + t * (pt_end[1] - pt_start[1])
                oz = pt_start[2] + t * (pt_end[2] - pt_start[2])
                coeff_local = c1 + t * (c2 - c1)

                if has_force:
                    f_local = f_res * abs(coeff_local)
                    length = f_local / f_max * scale if f_local > 1e-9 else 0.0
                    origin = (ox - f_dir[0]*length,
                              oy - f_dir[1]*length,
                              oz - f_dir[2]*length)
                    arrow_origins.append(origin)

                    if f_local > 1e-9:
                        direction = f_dir if coeff_local >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                        pd = _arrow_polydata(origin, direction, length, global_idx)
                        if pd is not None:
                            append_arrows.AddInputData(pd)
                            has_arrows = True

                elif has_moment:
                    arrow_origins.append((ox, oy, oz))

                if has_moment:
                    m_local = m_res * abs(coeff_local)
                    if m_local > 1e-9:
                        radius = m_local / m_max * scale
                        for ax_idx, mval in moment_axes:
                            sign = 1 if mval * coeff_local >= 0 else -1
                            pd = _arc_polydata((ox, oy, oz), ax_idx, radius, sign, global_idx)
                            if pd is not None:
                                append_tubes.AddInputData(pd)
                                has_tubes = True

            # Tube de la ligne de base (relie les sommets des fleches)
            if len(arrow_origins) >= 2:
                pd = _tube_polydata(arrow_origins, global_idx, shaft_r)
                if pd is not None:
                    append_tubes.AddInputData(pd)
                    has_tubes = True

        # --- Construire les acteurs fusionnés ---
        actors = []
        if has_arrows:
            append_arrows.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(append_arrows.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetAmbient(0.3)
            actor.GetProperty().SetDiffuse(0.7)
            actors.append((actor, 0))

        if has_tubes:
            append_tubes.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(append_tubes.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetAmbient(0.3)
            actor.GetProperty().SetDiffuse(0.7)
            actors.append((actor, 0))

        return actors

    def _build_linear_load_polydata_batch(self, loads: list, scale: float,
                                           case_filter=None, arrow_width: float = 0.02,
                                           global_data: list = None) -> dict:
        """Construit les polydata batchés pour les charges linéaires (thread-safe).

        Retourne un dict:
          'arrows' : vtkPolyData (fleches), ou None
          'tubes'  : vtkPolyData (tubes de contour + arcs), ou None
        """
        import math
        ref_data = global_data if global_data is not None else self._linear_load_data
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return {"arrows": None, "tubes": None}

        NB_SEGMENTS = 8
        ARROW_SHAFT_RES = 6
        ARROW_TIP_RES   = 6
        TUBE_SIDES      = 6
        ARC_SEGS        = 20

        f_max = 0.0
        m_max = 0.0
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            mx = float(ld.get("mx") or 0.0)
            my = float(ld.get("my") or 0.0)
            mz = float(ld.get("mz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            m_res = math.sqrt(mx*mx + my*my + mz*mz)
            f_max = max(f_max, f_res * abs(c1), f_res * abs(c2))
            m_max = max(m_max, m_res * abs(c1), m_res * abs(c2))

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        append_arrows = vtk.vtkAppendPolyData()
        append_tubes  = vtk.vtkAppendPolyData()
        has_arrows = False
        has_tubes  = False

        def _arrow_pd(origin, direction, length, element_index):
            dx, dy, dz = direction
            n = math.sqrt(dx*dx + dy*dy + dz*dz)
            if n < 1e-9:
                return None
            dx, dy, dz = dx/n, dy/n, dz/n
            eff_length = max(length, tip_l * 1.05)
            tip_frac   = max(0.05, min(0.95, tip_l / eff_length))
            src = vtk.vtkArrowSource()
            src.SetShaftRadius(shaft_r / eff_length)
            src.SetTipRadius(tip_r / eff_length)
            src.SetTipLength(tip_frac)
            src.SetShaftResolution(ARROW_SHAFT_RES)
            src.SetTipResolution(ARROW_TIP_RES)
            src.Update()
            dot = max(-1.0, min(1.0, dx))
            ax, ay, az = 0.0, -dz, dy
            ax_norm = math.sqrt(ax*ax + ay*ay + az*az)
            t = vtk.vtkTransform()
            t.Translate(*origin)
            t.Scale(eff_length, eff_length, eff_length)
            if ax_norm > 1e-9:
                t.RotateWXYZ(math.degrees(math.acos(dot)), ax/ax_norm, ay/ax_norm, az/ax_norm)
            elif dot < 0:
                t.RotateWXYZ(180.0, 0.0, 0.0, 1.0)
            tf = vtk.vtkTransformPolyDataFilter()
            tf.SetInputConnection(src.GetOutputPort())
            tf.SetTransform(t)
            tf.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tf.GetOutput())
            if element_index >= 0:
                ids = self._make_int_array()
                for _ in range(pd.GetNumberOfCells()):
                    ids.InsertNextValue(element_index)
                pd.GetCellData().AddArray(ids)
            return pd

        def _tube_pd(points_list, element_index, radius):
            if len(points_list) < 2:
                return None
            pts = vtk.vtkPoints()
            lines = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in points_list:
                pts.InsertNextPoint(*p)
            for j in range(len(points_list) - 1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j + 1)
                lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(pts)
            raw.SetLines(lines)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(radius)
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        def _arc_pd(center, axis, radius, sign, element_index):
            cx, cy, cz = center
            if axis == 0:
                u, v_vec = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (1.0, 0.0, 0.0)
            elif axis == 1:
                u, v_vec = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
                norm_ax = (0.0, 1.0, 0.0)
            else:
                u, v_vec = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
                norm_ax = (0.0, 0.0, 1.0)
            if sign < 0:
                v_vec = (-v_vec[0], -v_vec[1], -v_vec[2])
            start_angle = 45.0
            arc_deg = 270.0
            arc_rad = math.radians(arc_deg)
            pts_list = []
            for i in range(ARC_SEGS + 1):
                t = start_angle + math.degrees(arc_rad * i / ARC_SEGS)
                tr = math.radians(t)
                c, s = math.cos(tr), math.sin(tr)
                pts_list.append((
                    cx + radius * (u[0]*c + v_vec[0]*s),
                    cy + radius * (u[1]*c + v_vec[1]*s),
                    cz + radius * (u[2]*c + v_vec[2]*s),
                ))
            t_end = math.radians(start_angle + arc_deg)
            t_pen = math.radians(start_angle + arc_deg - 5.0)
            tip_len = radius * 0.18
            ex = cx + radius * (u[0]*math.cos(t_end) + v_vec[0]*math.sin(t_end))
            ey = cy + radius * (u[1]*math.cos(t_end) + v_vec[1]*math.sin(t_end))
            ez = cz + radius * (u[2]*math.cos(t_end) + v_vec[2]*math.sin(t_end))
            px = cx + radius * (u[0]*math.cos(t_pen) + v_vec[0]*math.sin(t_pen))
            py = cy + radius * (u[1]*math.cos(t_pen) + v_vec[1]*math.sin(t_pen))
            pz = cz + radius * (u[2]*math.cos(t_pen) + v_vec[2]*math.sin(t_pen))
            tang = (ex-px, ey-py, ez-pz)
            tn = math.sqrt(tang[0]**2+tang[1]**2+tang[2]**2)
            if tn > 1e-9:
                tang = (tang[0]/tn, tang[1]/tn, tang[2]/tn)
            b1 = (tang[1]*norm_ax[2]-tang[2]*norm_ax[1], tang[2]*norm_ax[0]-tang[0]*norm_ax[2], tang[0]*norm_ax[1]-tang[1]*norm_ax[0])
            b1n = math.sqrt(b1[0]**2+b1[1]**2+b1[2]**2)
            barb_lines = []
            if b1n > 1e-9:
                b1 = (b1[0]/b1n*tip_len, b1[1]/b1n*tip_len, b1[2]/b1n*tip_len)
                for barb in (b1, (-b1[0], -b1[1], -b1[2])):
                    pb = (ex-tang[0]*tip_len+barb[0], ey-tang[1]*tip_len+barb[1], ez-tang[2]*tip_len+barb[2])
                    barb_lines.append([(ex, ey, ez), pb])
            all_pts = vtk.vtkPoints()
            all_lines = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in pts_list:
                all_pts.InsertNextPoint(*p)
            for j in range(len(pts_list)-1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j+1)
                all_lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            base_off = len(pts_list)
            for bl in barb_lines:
                for pp in bl:
                    all_pts.InsertNextPoint(*pp)
            for k, bl in enumerate(barb_lines):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, base_off + k*2)
                seg.GetPointIds().SetId(1, base_off + k*2 + 1)
                all_lines.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(all_pts)
            raw.SetLines(all_lines)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(max(0.003, tube_r))
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        for ld in active:
            try:
                global_idx = ref_data.index(ld)
            except ValueError:
                global_idx = 0

            pt_start = ld["pt_start"]
            pt_end   = ld["pt_end"]
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            mx = float(ld.get("mx") or 0.0)
            my = float(ld.get("my") or 0.0)
            mz = float(ld.get("mz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)

            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            m_res = math.sqrt(mx*mx + my*my + mz*mz)
            has_force  = f_max > 1e-9 and f_res > 1e-9
            has_moment = m_max > 1e-9 and m_res > 1e-9

            if has_force:
                f_dir = (fx/f_res, fy/f_res, fz/f_res)
            if has_moment:
                moment_axes = [(ax_idx, mval) for ax_idx, mval in enumerate([mx, my, mz]) if abs(mval) > 1e-9]

            arrow_origins = []
            for i in range(NB_SEGMENTS + 1):
                t = i / NB_SEGMENTS
                ox = pt_start[0] + t * (pt_end[0] - pt_start[0])
                oy = pt_start[1] + t * (pt_end[1] - pt_start[1])
                oz = pt_start[2] + t * (pt_end[2] - pt_start[2])
                coeff_local = c1 + t * (c2 - c1)
                if has_force:
                    f_local = f_res * abs(coeff_local)
                    length = f_local / f_max * scale if f_local > 1e-9 else 0.0
                    origin = (ox - f_dir[0]*length, oy - f_dir[1]*length, oz - f_dir[2]*length)
                    arrow_origins.append(origin)
                    if f_local > 1e-9:
                        direction = f_dir if coeff_local >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                        pd = _arrow_pd(origin, direction, length, global_idx)
                        if pd is not None:
                            append_arrows.AddInputData(pd)
                            has_arrows = True
                elif has_moment:
                    arrow_origins.append((ox, oy, oz))
                if has_moment:
                    m_local = m_res * abs(coeff_local)
                    if m_local > 1e-9:
                        radius = m_local / m_max * scale
                        for ax_idx, mval in moment_axes:
                            sign = 1 if mval * coeff_local >= 0 else -1
                            pd = _arc_pd((ox, oy, oz), ax_idx, radius, sign, global_idx)
                            if pd is not None:
                                append_tubes.AddInputData(pd)
                                has_tubes = True

            if len(arrow_origins) >= 2:
                pd = _tube_pd(arrow_origins, global_idx, shaft_r)
                if pd is not None:
                    append_tubes.AddInputData(pd)
                    has_tubes = True

        arrows_pd = None
        tubes_pd  = None
        if has_arrows:
            append_arrows.Update()
            arrows_pd = vtk.vtkPolyData()
            arrows_pd.DeepCopy(append_arrows.GetOutput())
        if has_tubes:
            append_tubes.Update()
            tubes_pd = vtk.vtkPolyData()
            tubes_pd.DeepCopy(append_tubes.GetOutput())
        return {"arrows": arrows_pd, "tubes": tubes_pd}

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
            self.linear_load_scale,
            self.linear_load_color,
            case_filter=self._linear_load_case_filter,
            arrow_width=self.linear_load_arrow_width,
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

    def set_linear_load_style(self, color: tuple, arrow_width: float):
        """Applique couleur et épaisseur aux fleches de charges linéaires."""
        self.linear_load_color = tuple(float(v) for v in color)
        self.linear_load_arrow_width = max(0.005, float(arrow_width))
        if self._show_linear_loads and self._linear_load_data:
            self._rebuild_linear_load_actors()

    def _build_planar_load_actors(self, loads: list, scale: float, color: tuple,
                                   case_filter=None, arrow_width: float = 0.02,
                                   global_data: list = None) -> list:
        """Construit les acteurs VTK pour les charges surfaciques.

        Rendu : fleches perpendiculaires a la surface (selon la resultante des forces),
        tube de contour en partie superieure (pointe des fleches), zone remplie
        semi-transparente. La variation est interpolee par le plan defini par les
        3 premiers coefficients.

        global_data : liste de reference pour le calcul des index globaux.
        """
        import math

        ref_data = global_data if global_data is not None else self._planar_load_data
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return []

        ARROW_SHAFT_RES = 6
        ARROW_TIP_RES   = 6
        TUBE_SIDES      = 6

        # Calcul du max global pour normalisation
        f_max = 0.0
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            c3 = float(ld.get("coeff3") or 1.0)
            # Max sur tous les sommets via le plan de variation
            pts = ld.get("pts") or []
            if len(pts) >= 3:
                for i, pt in enumerate(pts):
                    coeff = self._interpolate_planar_coeff(pt, pts, c1, c2, c3)
                    f_max = max(f_max, f_res * abs(coeff))
            else:
                f_max = max(f_max, f_res * max(abs(c1), abs(c2), abs(c3)))

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        append_arrows  = vtk.vtkAppendPolyData()
        append_tubes   = vtk.vtkAppendPolyData()
        append_fill    = vtk.vtkAppendPolyData()
        has_arrows = False
        has_tubes  = False
        has_fill   = False

        def _arrow_polydata(origin, direction, length, element_index):
            dx, dy, dz = direction
            n = math.sqrt(dx*dx + dy*dy + dz*dz)
            if n < 1e-9:
                return None
            dx, dy, dz = dx/n, dy/n, dz/n
            eff_length = max(length, tip_l * 1.05)
            tip_frac   = max(0.05, min(0.95, tip_l / eff_length))
            src = vtk.vtkArrowSource()
            src.SetShaftRadius(shaft_r / eff_length)
            src.SetTipRadius(tip_r / eff_length)
            src.SetTipLength(tip_frac)
            src.SetShaftResolution(ARROW_SHAFT_RES)
            src.SetTipResolution(ARROW_TIP_RES)
            src.Update()
            dot = max(-1.0, min(1.0, dx))
            ax, ay, az = 0.0, -dz, dy
            ax_norm = math.sqrt(ax*ax + ay*ay + az*az)
            t = vtk.vtkTransform()
            t.Translate(*origin)
            t.Scale(eff_length, eff_length, eff_length)
            if ax_norm > 1e-9:
                t.RotateWXYZ(math.degrees(math.acos(dot)), ax/ax_norm, ay/ax_norm, az/ax_norm)
            elif dot < 0:
                t.RotateWXYZ(180.0, 0.0, 0.0, 1.0)
            tf = vtk.vtkTransformPolyDataFilter()
            tf.SetInputConnection(src.GetOutputPort())
            tf.SetTransform(t)
            tf.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tf.GetOutput())
            if element_index >= 0:
                ids = self._make_int_array()
                for _ in range(pd.GetNumberOfCells()):
                    ids.InsertNextValue(element_index)
                pd.GetCellData().AddArray(ids)
            return pd

        def _tube_polydata_pts(points_list, element_index, radius):
            if len(points_list) < 2:
                return None
            pts_vtk = vtk.vtkPoints()
            lines_vtk = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in points_list:
                pts_vtk.InsertNextPoint(*p)
            for j in range(len(points_list) - 1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j + 1)
                lines_vtk.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(pts_vtk)
            raw.SetLines(lines_vtk)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(radius)
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        def _quad_fill_polydata(base_i, base_j, tip_i, tip_j, element_index):
            """Retourne un quad (2 triangles) entre 2 sommets de base et leurs
            origines de fleches respectives. Represente un troncon de la 'jupe'
            de la charge surfacique.
            base_i, base_j : sommets du polygone (pointe de la fleche = sommet)
            tip_i,  tip_j  : origines des fleches (pied de la fleche)
            """
            vtk_pts = vtk.vtkPoints()
            vtk_cells = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            vtk_pts.InsertNextPoint(*base_i)   # 0
            vtk_pts.InsertNextPoint(*base_j)   # 1
            vtk_pts.InsertNextPoint(*tip_j)    # 2
            vtk_pts.InsertNextPoint(*tip_i)    # 3
            # Triangle 0-1-2
            tri1 = vtk.vtkTriangle()
            tri1.GetPointIds().SetId(0, 0)
            tri1.GetPointIds().SetId(1, 1)
            tri1.GetPointIds().SetId(2, 2)
            vtk_cells.InsertNextCell(tri1)
            ids_arr.InsertNextValue(element_index)
            # Triangle 0-2-3
            tri2 = vtk.vtkTriangle()
            tri2.GetPointIds().SetId(0, 0)
            tri2.GetPointIds().SetId(1, 2)
            tri2.GetPointIds().SetId(2, 3)
            vtk_cells.InsertNextCell(tri2)
            ids_arr.InsertNextValue(element_index)
            pd = vtk.vtkPolyData()
            pd.SetPoints(vtk_pts)
            pd.SetPolys(vtk_cells)
            pd.GetCellData().AddArray(ids_arr)
            return pd

        for ld in active:
            try:
                global_idx = ref_data.index(ld)
            except ValueError:
                global_idx = 0

            pts = ld.get("pts") or []
            if len(pts) < 3:
                continue

            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            c3 = float(ld.get("coeff3") or 1.0)

            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            has_force = f_max > 1e-9 and f_res > 1e-9

            if not has_force:
                continue

            f_dir = (fx / f_res, fy / f_res, fz / f_res)

            # Pour chaque sommet : calculer l'origine de la fleche (pied)
            # tip = sommet du polygone (pointe de la fleche)
            # origin = pied de la fleche (depart)
            tip_points    = []   # pointes = sommets originaux du polygone
            origin_points = []   # pieds des fleches

            for pt in pts:
                coeff = self._interpolate_planar_coeff(pt, pts, c1, c2, c3)
                f_local = f_res * abs(coeff)
                length = f_local / f_max * scale if f_local > 1e-9 else 0.0
                direction = f_dir if coeff >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                origin = (
                    pt[0] - direction[0] * length,
                    pt[1] - direction[1] * length,
                    pt[2] - direction[2] * length,
                )
                tip_points.append(pt)
                origin_points.append(origin)

                if length > 1e-9:
                    pd = _arrow_polydata(origin, direction, length, global_idx)
                    if pd is not None:
                        append_arrows.AddInputData(pd)
                        has_arrows = True

            # Tube de contour superieur reliant les PIEDS des fleches
            # (c'est la ligne basse visible entre les fleches, style Advance Design)
            contour_base = list(origin_points) + [origin_points[0]]
            pd = _tube_polydata_pts(contour_base, global_idx, tube_r)
            if pd is not None:
                append_tubes.AddInputData(pd)
                has_tubes = True

            # Remplissage : un quad par arete du polygone
            # entre (tip_i, tip_{i+1}) et (origin_i, origin_{i+1})
            n_pts = len(pts)
            for i in range(n_pts):
                j = (i + 1) % n_pts
                pd = _quad_fill_polydata(
                    tip_points[i], tip_points[j],
                    origin_points[i], origin_points[j],
                    global_idx,
                )
                if pd is not None:
                    append_fill.AddInputData(pd)
                    has_fill = True

        actors = []
        if has_arrows:
            append_arrows.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(append_arrows.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetAmbient(0.3)
            actor.GetProperty().SetDiffuse(0.7)
            actors.append((actor, 0))

        if has_tubes:
            append_tubes.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(append_tubes.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetAmbient(0.3)
            actor.GetProperty().SetDiffuse(0.7)
            actors.append((actor, 0))

        if has_fill:
            append_fill.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(append_fill.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetOpacity(0.18)
            actor.GetProperty().SetAmbient(0.5)
            actor.GetProperty().SetDiffuse(0.5)
            actor.GetProperty().BackfaceCullingOff()
            actors.append((actor, 0))

        return actors

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
                                           case_filter=None, arrow_width: float = 0.02,
                                           global_data: list = None) -> dict:
        """Construit les polydata batchés pour les charges surfaciques (thread-safe).

        Retourne un dict:
          'arrows' : vtkPolyData (fleches), ou None
          'tubes'  : vtkPolyData (tubes de contour), ou None
          'fill'   : vtkPolyData (remplissage semi-transparent), ou None
        """
        import math
        ref_data = global_data if global_data is not None else self._planar_load_data
        active = [ld for ld in (loads or []) if case_filter is None or ld.get("load_case_eid") == case_filter]
        if not active:
            return {"arrows": None, "tubes": None, "fill": None}

        ARROW_SHAFT_RES = 6
        ARROW_TIP_RES   = 6
        TUBE_SIDES      = 6

        f_max = 0.0
        for ld in active:
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            c3 = float(ld.get("coeff3") or 1.0)
            pts = ld.get("pts") or []
            if len(pts) >= 3:
                for pt in pts:
                    coeff = self._interpolate_planar_coeff(pt, pts, c1, c2, c3)
                    f_max = max(f_max, f_res * abs(coeff))
            else:
                f_max = max(f_max, f_res * max(abs(c1), abs(c2), abs(c3)))

        shaft_r = max(0.005, float(arrow_width))
        tip_r   = shaft_r * 2.5
        tip_l   = shaft_r * 5.0
        tube_r  = shaft_r * 0.5

        append_arrows = vtk.vtkAppendPolyData()
        append_tubes  = vtk.vtkAppendPolyData()
        append_fill   = vtk.vtkAppendPolyData()
        has_arrows = has_tubes = has_fill = False

        def _arrow_pd(origin, direction, length, element_index):
            dx, dy, dz = direction
            n = math.sqrt(dx*dx + dy*dy + dz*dz)
            if n < 1e-9:
                return None
            dx, dy, dz = dx/n, dy/n, dz/n
            eff_length = max(length, tip_l * 1.05)
            tip_frac   = max(0.05, min(0.95, tip_l / eff_length))
            src = vtk.vtkArrowSource()
            src.SetShaftRadius(shaft_r / eff_length)
            src.SetTipRadius(tip_r / eff_length)
            src.SetTipLength(tip_frac)
            src.SetShaftResolution(ARROW_SHAFT_RES)
            src.SetTipResolution(ARROW_TIP_RES)
            src.Update()
            dot = max(-1.0, min(1.0, dx))
            ax, ay, az = 0.0, -dz, dy
            ax_norm = math.sqrt(ax*ax + ay*ay + az*az)
            t = vtk.vtkTransform()
            t.Translate(*origin)
            t.Scale(eff_length, eff_length, eff_length)
            if ax_norm > 1e-9:
                t.RotateWXYZ(math.degrees(math.acos(dot)), ax/ax_norm, ay/ax_norm, az/ax_norm)
            elif dot < 0:
                t.RotateWXYZ(180.0, 0.0, 0.0, 1.0)
            tf = vtk.vtkTransformPolyDataFilter()
            tf.SetInputConnection(src.GetOutputPort())
            tf.SetTransform(t)
            tf.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tf.GetOutput())
            if element_index >= 0:
                ids = self._make_int_array()
                for _ in range(pd.GetNumberOfCells()):
                    ids.InsertNextValue(element_index)
                pd.GetCellData().AddArray(ids)
            return pd

        def _tube_pd(points_list, element_index, radius):
            if len(points_list) < 2:
                return None
            pts_vtk = vtk.vtkPoints()
            lines_vtk = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            for p in points_list:
                pts_vtk.InsertNextPoint(*p)
            for j in range(len(points_list) - 1):
                seg = vtk.vtkLine()
                seg.GetPointIds().SetId(0, j)
                seg.GetPointIds().SetId(1, j + 1)
                lines_vtk.InsertNextCell(seg)
                ids_arr.InsertNextValue(element_index)
            raw = vtk.vtkPolyData()
            raw.SetPoints(pts_vtk)
            raw.SetLines(lines_vtk)
            raw.GetCellData().AddArray(ids_arr)
            tube = vtk.vtkTubeFilter()
            tube.SetInputData(raw)
            tube.SetRadius(radius)
            tube.SetNumberOfSides(TUBE_SIDES)
            tube.CappingOn()
            tube.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tube.GetOutput())
            return pd

        def _quad_pd(base_i, base_j, tip_i, tip_j, element_index):
            vtk_pts = vtk.vtkPoints()
            vtk_cells = vtk.vtkCellArray()
            ids_arr = self._make_int_array()
            vtk_pts.InsertNextPoint(*base_i)
            vtk_pts.InsertNextPoint(*base_j)
            vtk_pts.InsertNextPoint(*tip_j)
            vtk_pts.InsertNextPoint(*tip_i)
            tri1 = vtk.vtkTriangle()
            tri1.GetPointIds().SetId(0, 0)
            tri1.GetPointIds().SetId(1, 1)
            tri1.GetPointIds().SetId(2, 2)
            vtk_cells.InsertNextCell(tri1)
            ids_arr.InsertNextValue(element_index)
            tri2 = vtk.vtkTriangle()
            tri2.GetPointIds().SetId(0, 0)
            tri2.GetPointIds().SetId(1, 2)
            tri2.GetPointIds().SetId(2, 3)
            vtk_cells.InsertNextCell(tri2)
            ids_arr.InsertNextValue(element_index)
            pd = vtk.vtkPolyData()
            pd.SetPoints(vtk_pts)
            pd.SetPolys(vtk_cells)
            pd.GetCellData().AddArray(ids_arr)
            return pd

        for ld in active:
            try:
                global_idx = ref_data.index(ld)
            except ValueError:
                global_idx = 0
            pts = ld.get("pts") or []
            if len(pts) < 3:
                continue
            fx = float(ld.get("fx") or 0.0)
            fy = float(ld.get("fy") or 0.0)
            fz = float(ld.get("fz") or 0.0)
            c1 = float(ld.get("coeff1") or 1.0)
            c2 = float(ld.get("coeff2") or 1.0)
            c3 = float(ld.get("coeff3") or 1.0)
            f_res = math.sqrt(fx*fx + fy*fy + fz*fz)
            if f_max < 1e-9 or f_res < 1e-9:
                continue
            f_dir = (fx / f_res, fy / f_res, fz / f_res)
            tip_points    = []
            origin_points = []
            for pt in pts:
                coeff = self._interpolate_planar_coeff(pt, pts, c1, c2, c3)
                f_local = f_res * abs(coeff)
                length = f_local / f_max * scale if f_local > 1e-9 else 0.0
                direction = f_dir if coeff >= 0 else (-f_dir[0], -f_dir[1], -f_dir[2])
                origin = (pt[0] - direction[0]*length, pt[1] - direction[1]*length, pt[2] - direction[2]*length)
                tip_points.append(pt)
                origin_points.append(origin)
                if length > 1e-9:
                    pd = _arrow_pd(origin, direction, length, global_idx)
                    if pd is not None:
                        append_arrows.AddInputData(pd)
                        has_arrows = True
            contour_base = list(origin_points) + [origin_points[0]]
            pd = _tube_pd(contour_base, global_idx, tube_r)
            if pd is not None:
                append_tubes.AddInputData(pd)
                has_tubes = True
            n_pts = len(pts)
            for i in range(n_pts):
                j = (i + 1) % n_pts
                pd = _quad_pd(tip_points[i], tip_points[j], origin_points[i], origin_points[j], global_idx)
                if pd is not None:
                    append_fill.AddInputData(pd)
                    has_fill = True

        arrows_pd = tubes_pd = fill_pd = None
        if has_arrows:
            append_arrows.Update()
            arrows_pd = vtk.vtkPolyData()
            arrows_pd.DeepCopy(append_arrows.GetOutput())
        if has_tubes:
            append_tubes.Update()
            tubes_pd = vtk.vtkPolyData()
            tubes_pd.DeepCopy(append_tubes.GetOutput())
        if has_fill:
            append_fill.Update()
            fill_pd = vtk.vtkPolyData()
            fill_pd.DeepCopy(append_fill.GetOutput())
        return {"arrows": arrows_pd, "tubes": tubes_pd, "fill": fill_pd}

    def apply_loads_polydata_batch(self, batch: dict):
        """Applique les polydata pre-construits (depuis un worker) au renderer.

        Doit etre appele depuis le thread principal.
        batch = {
          'punctual': {'arrows': vtkPolyData|None},
          'linear':   {'arrows': vtkPolyData|None, 'tubes': vtkPolyData|None},
          'planar':   {'arrows': vtkPolyData|None, 'tubes': vtkPolyData|None, 'fill': vtkPolyData|None},
          'punctual_color': tuple, 'linear_color': tuple, 'planar_color': tuple,
        }
        """
        def _make_solid_actor(pd, color, ambient=0.3, diffuse=0.7, opacity=1.0):
            if pd is None or pd.GetNumberOfCells() == 0:
                return None
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(pd)
            mapper.ScalarVisibilityOff()
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetAmbient(ambient)
            actor.GetProperty().SetDiffuse(diffuse)
            actor.GetProperty().SetOpacity(opacity)
            return actor

        # --- Ponctuelles ---
        for actor in self._punctual_load_actors:
            self._remove_actor(actor)
        self._punctual_load_actors = []
        if self._show_punctual_loads:
            p_color = batch.get("punctual_color", self.punctual_load_color)
            p_data  = batch.get("punctual", {})
            actor = _make_solid_actor(p_data.get("arrows"), p_color)
            if actor:
                self._add_actor(actor, role="punctual_load", pickable=True)
                self._punctual_load_actors.append(actor)

        # --- Linéaires ---
        for actor in self._linear_load_actors:
            self._remove_actor(actor)
        self._linear_load_actors = []
        if self._show_linear_loads:
            l_color = batch.get("linear_color", self.linear_load_color)
            l_data  = batch.get("linear", {})
            for key in ("arrows", "tubes"):
                actor = _make_solid_actor(l_data.get(key), l_color)
                if actor:
                    self._add_actor(actor, role="linear_load", pickable=True)
                    self._linear_load_actors.append(actor)

        # --- Surfaciques ---
        for actor in self._planar_load_actors:
            self._remove_actor(actor)
        self._planar_load_actors = []
        if self._show_planar_loads:
            s_color = batch.get("planar_color", self.planar_load_color)
            s_data  = batch.get("planar", {})
            for key in ("arrows", "tubes"):
                actor = _make_solid_actor(s_data.get(key), s_color)
                if actor:
                    self._add_actor(actor, role="planar_load", pickable=True)
                    self._planar_load_actors.append(actor)
            fill_actor = _make_solid_actor(s_data.get("fill"), s_color, ambient=0.5, diffuse=0.5, opacity=0.18)
            if fill_actor:
                fill_actor.GetProperty().BackfaceCullingOff()
                self._add_actor(fill_actor, role="planar_load", pickable=True)
                self._planar_load_actors.append(fill_actor)

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
            self.planar_load_scale,
            self.planar_load_color,
            case_filter=self._planar_load_case_filter,
            arrow_width=self.planar_load_arrow_width,
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

    def set_planar_load_style(self, color: tuple, arrow_width: float):
        """Applique couleur et epaisseur aux charges surfaciques."""
        self.planar_load_color = tuple(float(v) for v in color)
        self.planar_load_arrow_width = max(0.005, float(arrow_width))
        if self._show_planar_loads and self._planar_load_data:
            self._rebuild_planar_load_actors()

    def load_model(self, model_data: dict):
        self.clear_scene()
        self._section_color_map = {}

        self._model_data = {
            "lines": list(model_data.get("lines", [])),
            "line_eids": list(model_data.get("line_eids", [])),
            "line_properties": list(model_data.get("line_properties", [])),
            "planars": list(model_data.get("planars", [])),
            "planar_eids": list(model_data.get("planar_eids", [])),
            "planar_properties": list(model_data.get("planar_properties", [])),
            "load_areas": list(model_data.get("load_areas", [])),
            "punctual_supports": list(model_data.get("punctual_supports", [])),
            "punctual_support_eids": list(model_data.get("punctual_support_eids", [])),
            "linear_supports": list(model_data.get("linear_supports", [])),
            "linear_support_eids": list(model_data.get("linear_support_eids", [])),
            "planar_supports": list(model_data.get("planar_supports", [])),
            "planar_support_eids": list(model_data.get("planar_support_eids", [])),
        }
        self._support_punctual_points = list(self._model_data["punctual_supports"])

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
        self.set_isometric_view()

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
            return sorted(line_indexes)
        section_names = self._filter_section_names
        material_names = self._filter_material_names
        indexes = []
        for idx, props in enumerate(items):
            props = props or {}
            section_ok = True if section_names is None else str(props.get("section", "N/A")) in section_names
            material_ok = True if material_names is None else str(props.get("material", "N/A")) in material_names
            if section_ok and material_ok:
                indexes.append(idx)
        return indexes

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
            return sorted(planar_indexes)
        thickness_names = self._filter_thickness_names
        material_names = self._filter_material_names
        indexes = []
        for idx, props in enumerate(items):
            props = props or {}
            thickness_ok = True if thickness_names is None else str(props.get("thickness", "N/A")) in thickness_names
            material_ok = True if material_names is None else str(props.get("material", "N/A")) in material_names
            if thickness_ok and material_ok:
                indexes.append(idx)
        return indexes

    def _select_items_by_indexes(self, items, indexes):
        source = list(items or [])
        return [source[int(idx)] for idx in indexes if 0 <= int(idx) < len(source)]

    def _rebuild_filtered_structural_actors(self):
        line_indexes = self._filtered_line_indexes()
        planar_indexes = self._filtered_planar_indexes()
        filtered_lines = self._select_items_by_indexes(self._model_data.get("lines", []), line_indexes)
        filtered_planars = self._select_items_by_indexes(self._model_data.get("planars", []), planar_indexes)
        isolated = list(self._isolated_selection or [])
        is_isolated = bool(isolated)

        load_areas = list(self._model_data.get("load_areas", []) or [])
        punctual_supports = list(self._model_data.get("punctual_supports", []) or [])
        linear_supports = list(self._model_data.get("linear_supports", []) or [])
        planar_supports = list(self._model_data.get("planar_supports", []) or [])

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
                        self.punctual_load_scale,
                        self.punctual_load_color,
                        case_filter=None,   # déjà filtré par index
                        arrow_width=self.punctual_load_arrow_width,
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
                        self.linear_load_scale,
                        self.linear_load_color,
                        case_filter=None,
                        arrow_width=self.linear_load_arrow_width,
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
                        self.planar_load_scale,
                        self.planar_load_color,
                        case_filter=None,
                        arrow_width=self.planar_load_arrow_width,
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

        self._replace_actor(
            "_lines_actor",
            self._make_wire_actor(self._build_lines_polydata(filtered_lines, element_indexes=line_indexes), self.linear_color, self.linear_line_width),
            role="lines",
            pickable=True,
        )
        self._replace_actor(
            "_planar_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(filtered_planars, element_indexes=planar_indexes), self.planar_color, self.planar_line_width),
            role="planars",
            pickable=True,
        )
        self._replace_actor(
            "_planar_faces_actor",
            self._make_surface_actor(self._build_faces_polydata(filtered_planars, element_indexes=planar_indexes), self.planar_color, self.planar_faces_base_opacity),
            role="planars",
            pickable=True,
        )
        self._replace_actor(
            "_openings_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(filtered_planars, openings=True, element_indexes=planar_indexes), self.opening_color, self.opening_line_width),
            role="planars",
            pickable=False,
        )
        self._replace_actor(
            "_load_areas_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(load_areas), self.load_area_color, self.load_area_line_width),
            role="load_areas",
            pickable=True,
        )
        self._replace_actor(
            "_load_areas_faces_actor",
            self._make_surface_actor(self._build_faces_polydata(load_areas), self.load_area_color, self.load_areas_faces_base_opacity),
            role="load_areas",
            pickable=True,
        )
        self._replace_actor(
            "_support_punctual_actor",
            self._make_wire_actor(self._build_punctual_supports_polydata(punctual_supports), self.support_punctual_color, self.support_punctual_line_width),
            role="support_punctual",
            pickable=True,
        )
        self._replace_actor(
            "_support_linear_actor",
            self._make_wire_actor(self._build_lines_polydata(linear_supports, include_section_colors=False), self.support_linear_color, self.support_linear_line_width),
            role="support_linear",
            pickable=True,
        )
        self._replace_actor(
            "_support_planar_actor",
            self._make_wire_actor(self._build_loops_wire_polydata(planar_supports), self.support_planar_color, self.support_planar_line_width),
            role="support_planar",
            pickable=True,
        )
        self._replace_actor(
            "_support_planar_faces_actor",
            self._make_surface_actor(self._build_faces_polydata(planar_supports), self.support_planar_color, self.support_planar_faces_base_opacity),
            role="support_planar",
            pickable=True,
        )
        if not isolated_has_planar_support:
            self.clear_planar_support_result_centroid()
        self._apply_visibility_state()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def set_structural_filters(self, section_names=None, thickness_names=None, material_names=None):
        self._filter_section_names = None if section_names is None else set(str(v) for v in section_names)
        self._filter_thickness_names = None if thickness_names is None else set(str(v) for v in thickness_names)
        self._filter_material_names = None if material_names is None else set(str(v) for v in material_names)
        self._rebuild_filtered_structural_actors()

    def set_isolated_selection(self, selection):
        """Isole un ou plusieurs éléments.

        Accepte :
        - None  → annule l'isolation
        - dict  {"role": str, "index": int} → isole un seul élément (compatibilité)
        - list  [{"role": str, "index": int}, ...] → isole plusieurs éléments
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
        self._rebuild_filtered_structural_actors()

    def has_isolated_selection(self) -> bool:
        return bool(self._isolated_selection)

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

