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
    BG, PANEL, BORDER, ACCENT, ACCENT2, WARN, ERROR_COL,
    FG, FG_DIM, VTK_BG,
    LINEAR_LINE_WIDTH, PLANAR_LINE_WIDTH, OPENING_LINE_WIDTH, LOAD_AREA_LINE_WIDTH,
    SUPPORT_PUNCTUAL_SIZE, SUPPORT_PUNCTUAL_LINE_WIDTH,
    SUPPORT_LINEAR_LINE_WIDTH, SUPPORT_PLANAR_LINE_WIDTH,
    INITIAL_TRANSPARENCY_PERCENT,
    DEFAULT_VIEW_PROJECTION,
    MESH_LINE_WIDTH,
    MESH_COLOR,
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
    selectionChanged = Signal(dict)
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
        self._selected_item = None
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

        self._show_lines = True
        self._show_planars = True
        self._show_load_areas = True
        self._show_support_punctual = True
        self._show_support_linear = True
        self._show_support_planar = True
        self._show_marker = True
        self._show_mesh = False
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
        self._isolated_selection = None
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
        self.interactor.AddObserver("KeyPressEvent", self._on_key_press, 1.0)

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

        return overlays

    def _refresh_selection_overlay(self):
        current = self._selected_item
        self._clear_selection_overlay()
        if not current:
            self.render_window.Render()
            return
        overlays = self._make_selection_overlay_actors(current["role"], current["index"])
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

    def set_linear_result_diagram(self, line_points, series, title: str = "", line_property: dict = None):
        self.clear_result_diagram()
        if not isinstance(line_points, (list, tuple)) or len(line_points) != 2:
            return
        if not isinstance(series, list) or len(series) < 2:
            return

        try:
            p1 = tuple(float(v) for v in line_points[0])
            p2 = tuple(float(v) for v in line_points[1])
        except Exception:
            return

        axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
        length = math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2])
        if length <= 1e-9:
            return
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
            return
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

        max_abs = max(abs(float((entry or {}).get("value", 0.0))) for entry in series)
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
            stems.append((base, tip))
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

        def build_segments(segments_list):
            points = vtk.vtkPoints()
            cells = vtk.vtkCellArray()
            for start, end in segments_list:
                pid0 = points.InsertNextPoint(*start)
                pid1 = points.InsertNextPoint(*end)
                line = vtk.vtkLine()
                line.GetPointIds().SetId(0, pid0)
                line.GetPointIds().SetId(1, pid1)
                cells.InsertNextCell(line)
            poly = vtk.vtkPolyData()
            poly.SetPoints(points)
            poly.SetLines(cells)
            return poly

        def _format_diagram_label_value(text_value):
            try:
                value = float(text_value)
            except Exception:
                return str(text_value)
            if abs(value) < 0.001:
                return "+0" if value >= 0.0 else "-0"
            return f"{value:.3f}"

        def add_billboard_label(text_value, point, color, offset_factor=0.06):
            if point is None:
                return None
            try:
                actor = vtkBillboardTextActor3D()
            except Exception:
                return None
            offset = max(0.03, scale_height * offset_factor)
            pos = (
                float(point[0]) + normal[0] * offset,
                float(point[1]) + normal[1] * offset,
                float(point[2]) + normal[2] * offset,
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
            self._diagram_label_actors.append(actor)
            return actor

        actors = []
        baseline_actor = self._make_wire_actor(build_polyline(baseline_points), (0.45, 0.45, 0.45), 1.5)
        stems_actor = self._make_wire_actor(build_segments(stems), (0.80, 0.40, 0.15), 1.3)
        diagram_actor = self._make_wire_actor(build_polyline(diagram_points), (0.05, 0.45, 0.95), max(2.0, self.linear_line_width + 1.0))
        for actor in (baseline_actor, stems_actor, diagram_actor):
            if actor is None:
                continue
            actor.PickableOff()
            actors.append(self._add_actor(actor, role=None, pickable=False))

        if samples:
            min_sample = min(samples, key=lambda item: float(item["value"]))
            max_sample = max(samples, key=lambda item: float(item["value"]))
            if abs(float(max_sample["value"]) - float(min_sample["value"])) <= 1e-12:
                label_actor = add_billboard_label(max_sample["value"], max_sample["tip"], (1.0, 0.0, 0.0))
                if label_actor is not None:
                    actors.append(label_actor)
            else:
                min_actor = add_billboard_label(min_sample["value"], min_sample["tip"], (0.05, 0.35, 1.0))
                max_actor = add_billboard_label(max_sample["value"], max_sample["tip"], (1.0, 0.0, 0.0))
                if min_actor is not None:
                    actors.append(min_actor)
                if max_actor is not None:
                    actors.append(max_actor)

        self._diagram_overlay_actors = [actor for actor in actors if actor is not None]
        self.render_window.Render()

    def clear_selection(self):
        self._selected_item = None
        self._selection_candidates = []
        self._selection_candidate_keys = []
        self._selection_cycle_index = -1
        self.selectionChanged.emit({})
        self._refresh_selection_overlay()

    def set_selection_style(self, selection_color, selection_line_width: float):
        self.selection_color = tuple(float(v) for v in selection_color)
        self.selection_line_width = max(0.1, float(selection_line_width))
        self._refresh_selection_overlay()

    def _select_item(self, role: str, index: int):
        self._selected_item = {"role": role, "index": int(index)}
        self.selectionChanged.emit(dict(self._selected_item))
        self._refresh_selection_overlay()
        return True

    def _on_right_button_press(self, obj, event):
        self.vtk_widget.setFocus()
        x, y = self.interactor.GetEventPosition()
        candidates = self._pick_selection_candidates(x, y)
        if candidates:
            candidate_keys = [(c["role"], int(c["index"])) for c in candidates]
            if candidate_keys == self._selection_candidate_keys:
                self._selection_cycle_index = (self._selection_cycle_index + 1) % len(candidates)
            else:
                self._selection_candidates = candidates
                self._selection_candidate_keys = candidate_keys
                self._selection_cycle_index = 0
            selected = candidates[self._selection_cycle_index]
            self._select_item(selected["role"], selected["index"])
            return
        self.interactor_style.OnRightButtonDown()

    def _on_left_button_press(self, obj, event):
        self.vtk_widget.setFocus()
        x, y = self.interactor.GetEventPosition()
        candidates = self._pick_selection_candidates(x, y)
        if candidates:
            self._selection_candidates = candidates
            self._selection_candidate_keys = [(c["role"], int(c["index"])) for c in candidates]
            self._selection_cycle_index = 0
            selected = candidates[0]
            self._select_item(selected["role"], selected["index"])
            return
        self.interactor_style.OnLeftButtonDown()

    def _on_key_press(self, obj, event):
        key = self.interactor.GetKeySym() if self.interactor is not None else ""
        if key in ("Escape", "escape"):
            self.clear_selection()
            return

    def get_display_counts(self):
        return {
            "lines": self.lines_count,
            "planars": self.planars_count,
            "load_areas": self.load_areas_count,
            "support_punctual": self.support_punctual_count,
            "support_linear": self.support_linear_count,
            "support_planar": self.support_planar_count,
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
        self._isolated_selection = None
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

    def set_show_lines(self, visible: bool):
        self._show_lines = visible
        self._apply_visibility_state()

    def set_show_planars(self, visible: bool):
        self._show_planars = visible
        self._apply_visibility_state()

    def set_show_load_areas(self, visible: bool):
        self._show_load_areas = visible
        self._apply_visibility_state()

    def set_show_support_punctual(self, visible: bool):
        self._show_support_punctual = visible
        self._apply_visibility_state()

    def set_show_support_linear(self, visible: bool):
        self._show_support_linear = visible
        self._apply_visibility_state()

    def set_show_support_planar(self, visible: bool):
        self._show_support_planar = visible
        self._apply_visibility_state()

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
        isolated = self._isolated_selection or {}
        isolated_role = str(isolated.get("role") or "").strip()
        if isolated_role:
            if isolated_role in ("lines", "line", "linear", "element_linear"):
                idx = int(isolated.get("index", -1))
                return [idx] if 0 <= idx < len(items) else []
            return []
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
        isolated = self._isolated_selection or {}
        isolated_role = str(isolated.get("role") or "").strip()
        if isolated_role:
            if isolated_role in ("planars", "planar", "element_planar"):
                idx = int(isolated.get("index", -1))
                return [idx] if 0 <= idx < len(items) else []
            return []
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
        isolated = self._isolated_selection or {}
        isolated_role = str(isolated.get("role") or "").strip()
        isolated_index = int(isolated.get("index", -1))

        load_areas = list(self._model_data.get("load_areas", []) or [])
        punctual_supports = list(self._model_data.get("punctual_supports", []) or [])
        linear_supports = list(self._model_data.get("linear_supports", []) or [])
        planar_supports = list(self._model_data.get("planar_supports", []) or [])

        if isolated_role:
            if isolated_role == "load_areas":
                load_areas = self._select_items_by_indexes(load_areas, [isolated_index])
            else:
                load_areas = []
            if isolated_role == "support_punctual":
                punctual_supports = self._select_items_by_indexes(punctual_supports, [isolated_index])
            else:
                punctual_supports = []
            if isolated_role == "support_linear":
                linear_supports = self._select_items_by_indexes(linear_supports, [isolated_index])
            else:
                linear_supports = []
            if isolated_role == "support_planar":
                planar_supports = self._select_items_by_indexes(planar_supports, [isolated_index])
            else:
                planar_supports = []

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
            self._make_wire_actor(self._build_lines_polydata(linear_supports), self.support_linear_color, self.support_linear_line_width),
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
        if isolated_role != "support_planar":
            self.clear_planar_support_result_centroid()
        self._apply_visibility_state()
        self.renderer.ResetCameraClippingRange()
        self.render_window.Render()

    def set_structural_filters(self, section_names=None, thickness_names=None, material_names=None):
        self._filter_section_names = None if section_names is None else set(str(v) for v in section_names)
        self._filter_thickness_names = None if thickness_names is None else set(str(v) for v in thickness_names)
        self._filter_material_names = None if material_names is None else set(str(v) for v in material_names)
        self._rebuild_filtered_structural_actors()

    def set_isolated_selection(self, selection: dict | None):
        if not isinstance(selection, dict):
            self._isolated_selection = None
        else:
            role = str(selection.get("role") or "").strip()
            index = int(selection.get("index", -1))
            if role and index >= 0:
                self._isolated_selection = {"role": role, "index": index}
            else:
                self._isolated_selection = None
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

