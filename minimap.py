# -*- coding: utf-8 -*-
"""
minimap.py
Calculs purs pour la minicarte du viewer 3D : rectangle de viewport
normalise selon le coin choisi et la taille de fenetre, triangle 2D
representant le cone de vue (position + direction + FOV) de la camera
principale projete en vue de dessus, et conversion FOV vertical -> FOV
horizontal reel.

Extrait comme module autonome (meme pattern que flight_navigation.py /
scene_light.py) pour rester testable sans fenetre VTK reelle.
"""

import math


def viewport_rect(corner: str, window_width: float, window_height: float, size_px: float = 300.0):
    """Rectangle normalise [0,1] pour vtkRenderer.SetViewport(), positionne
    dans le coin demande et clampe pour ne jamais depasser la fenetre sur une
    petite fenetre. Coin inconnu -> repli sur "bottom_left"."""
    w = max(1.0, float(window_width))
    h = max(1.0, float(window_height))
    size_w = min(float(size_px), w)
    size_h = min(float(size_px), h)
    frac_w = size_w / w
    frac_h = size_h / h
    if corner == "bottom_right":
        xmin, xmax = 1.0 - frac_w, 1.0
    else:
        xmin, xmax = 0.0, frac_w
    ymin, ymax = 0.0, frac_h
    return (xmin, ymin, xmax, ymax)


def camera_fov_triangle(position_xy, direction_xy, half_angle_deg: float, size: float):
    """Triangle 2D (apex, base_left, base_right) representant le cone de vue
    vu de dessus : apex = position camera, base centree a `size` le long de
    `direction_xy`, largeur de base = 2 * size * tan(half_angle_deg).
    Direction degeneree (norme quasi nulle, camera verticale) -> replie sur
    (0, 1) pour rester numeriquement stable (pas de NaN)."""
    px, py = float(position_xy[0]), float(position_xy[1])
    dx, dy = float(direction_xy[0]), float(direction_xy[1])
    dlen = math.sqrt(dx * dx + dy * dy)
    if dlen < 1e-9:
        dx, dy = 0.0, 1.0
    else:
        dx, dy = dx / dlen, dy / dlen
    base_cx, base_cy = px + dx * size, py + dy * size
    half_width = size * math.tan(math.radians(half_angle_deg))
    # Perpendiculaire a (dx, dy) dans le plan XY.
    perp_x, perp_y = -dy, dx
    base_left = (base_cx + perp_x * half_width, base_cy + perp_y * half_width)
    base_right = (base_cx - perp_x * half_width, base_cy - perp_y * half_width)
    return [(px, py), base_left, base_right]


def horizontal_half_fov_deg(camera_view_angle_deg: float, aspect_ratio: float, is_parallel: bool = False) -> float:
    """Demi-angle de champ de vision horizontal reel. VTK expose l'angle
    vertical (camera.GetViewAngle()) ; conversion via l'aspect ratio du
    viewport. En projection orthogonale (is_parallel=True), pas de FOV
    angulaire reel : angle fixe de 45 degres (decision de design)."""
    if is_parallel:
        return 45.0
    half_vertical_rad = math.radians(float(camera_view_angle_deg)) / 2.0
    half_horizontal_rad = math.atan(math.tan(half_vertical_rad) * float(aspect_ratio))
    return math.degrees(half_horizontal_rad)


import vtk
from PySide6.QtCore import QTimer


class MinimapController:
    """Minicarte (vue orthographique 2D en incrustation). `host` est le
    VTKViewerWidget qui le possede - MinimapController s'appuie sur
    host.renderer, host.render_window, host.width()/height() et sur les
    helpers de construction de polydata deja definis sur VTKViewerWidget
    (_build_lines_polydata, _build_loops_wire_polydata,
    _build_punctual_supports_polydata, _make_wire_actor)."""

    FRAME_MARGIN_PX = 2.0

    def __init__(self, host):
        self.host = host
        self.renderer = None
        self.frame_actor = None
        self.corner = None
        self.visible = False
        self.lines_actor = None
        self.planar_actor = None
        self.planar_faces_actor = None
        self.support_punctual_actor = None
        self.support_linear_actor = None
        self.support_planar_actor = None
        self.support_planar_faces_actor = None
        self.marker_actor = None
        self.cone_actor = None
        self.timer = None
        self.model_diagonal = 0.0
        self.model_zmax = 0.0
        self._last_camera_mtime = -1

    def setup(self):
        import viewer_config as _cfg

        self.corner = _cfg.MINIMAP_DEFAULT_CORNER

        renderer = vtk.vtkRenderer()
        renderer.InteractiveOff()
        camera = renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.SetPosition(0.0, 0.0, 1.0)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        self.renderer = renderer

        points = vtk.vtkPoints()
        for _ in range(4):
            points.InsertNextPoint(0.0, 0.0, 0.0)
        cell = vtk.vtkPolyLine()
        cell.GetPointIds().SetNumberOfIds(5)
        for i in range(5):
            cell.GetPointIds().SetId(i, i % 4)
        cells = vtk.vtkCellArray()
        cells.InsertNextCell(cell)
        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)

        coord = vtk.vtkCoordinate()
        coord.SetCoordinateSystemToNormalizedViewport()
        mapper2d = vtk.vtkPolyDataMapper2D()
        mapper2d.SetInputData(poly)
        mapper2d.SetTransformCoordinate(coord)

        frame_actor = vtk.vtkActor2D()
        frame_actor.SetMapper(mapper2d)
        frame_actor.GetProperty().SetLineWidth(1.5)
        frame_actor.SetVisibility(False)
        frame_actor.PickableOff()
        self.frame_actor = frame_actor
        self.host.renderer.AddViewProp(frame_actor)

        marker_source = vtk.vtkDiskSource()
        marker_source.SetInnerRadius(0.0)
        marker_source.SetOuterRadius(1.0)
        marker_source.SetCircumferentialResolution(24)
        marker_mapper = vtk.vtkPolyDataMapper()
        marker_mapper.SetInputConnection(marker_source.GetOutputPort())
        marker_actor = vtk.vtkActor()
        marker_actor.SetMapper(marker_mapper)
        marker_actor.PickableOff()
        marker_actor.GetProperty().LightingOff()
        marker_actor.GetProperty().SetColor(*_cfg.MINIMAP_CAMERA_COLOR)
        self.marker_actor = marker_actor
        self.renderer.AddActor(marker_actor)

        cone_points = vtk.vtkPoints()
        for _ in range(3):
            cone_points.InsertNextPoint(0.0, 0.0, 0.0)
        cone_cell = vtk.vtkTriangle()
        cone_cell.GetPointIds().SetId(0, 0)
        cone_cell.GetPointIds().SetId(1, 1)
        cone_cell.GetPointIds().SetId(2, 2)
        cone_cells = vtk.vtkCellArray()
        cone_cells.InsertNextCell(cone_cell)
        cone_poly = vtk.vtkPolyData()
        cone_poly.SetPoints(cone_points)
        cone_poly.SetPolys(cone_cells)
        cone_mapper = vtk.vtkPolyDataMapper()
        cone_mapper.SetInputData(cone_poly)
        cone_actor = vtk.vtkActor()
        cone_actor.SetMapper(cone_mapper)
        cone_actor.PickableOff()
        cone_actor.GetProperty().LightingOff()
        cone_actor.GetProperty().SetColor(*_cfg.MINIMAP_CAMERA_COLOR)
        cone_actor.GetProperty().SetOpacity(0.4)
        self.cone_actor = cone_actor
        self.renderer.AddActor(cone_actor)

        self.timer = QTimer(self.host)
        self.timer.setInterval(_cfg.MINIMAP_SYNC_INTERVAL_MS)
        self.timer.timeout.connect(self.sync_tick)

    def apply_theme(self, color):
        import viewer_config as _cfg

        if self.frame_actor is not None:
            self.frame_actor.GetProperty().SetColor(*color)
        for attr in (
            "lines_actor", "planar_actor", "planar_faces_actor",
            "support_punctual_actor", "support_linear_actor",
            "support_planar_actor", "support_planar_faces_actor",
        ):
            actor = getattr(self, attr)
            if actor is not None:
                actor.GetProperty().SetColor(*color)
        if self.renderer is not None:
            self.renderer.SetBackground(*_cfg.VTK_BG)

    def set_corner(self, corner: str):
        self.corner = corner if corner in ("bottom_left", "bottom_right") else "bottom_left"
        self.update_viewport()

    def update_viewport(self):
        import viewer_config as _cfg

        if self.renderer is None:
            return
        w = max(1, self.host.width())
        h = max(1, self.host.height())
        rect = viewport_rect(self.corner, float(w), float(h), size_px=_cfg.MINIMAP_SIZE_PX)
        self.renderer.SetViewport(*rect)

        margin_x = self.FRAME_MARGIN_PX / float(w)
        margin_y = self.FRAME_MARGIN_PX / float(h)
        xmin, ymin, xmax, ymax = rect
        xmin = max(0.0, xmin - margin_x)
        ymin = max(0.0, ymin - margin_y)
        xmax = min(1.0, xmax + margin_x)
        ymax = min(1.0, ymax + margin_y)
        poly = self.frame_actor.GetMapper().GetInput()
        pts = poly.GetPoints()
        pts.SetPoint(0, xmin, ymin, 0.0)
        pts.SetPoint(1, xmax, ymin, 0.0)
        pts.SetPoint(2, xmax, ymax, 0.0)
        pts.SetPoint(3, xmin, ymax, 0.0)
        pts.Modified()

        if self.visible:
            self._fit_camera_to_model()
            if self.host.render_window is not None:
                self.host.render_window.Render()

    def build_geometry(self):
        import viewer_config as _cfg

        host = self.host
        is_dark = tuple(_cfg.VTK_BG) == tuple(_cfg._DARK_VTK_BG)
        line_color = (0.92, 0.94, 0.98) if is_dark else (0.12, 0.16, 0.22)

        lines_pd = host._build_lines_polydata(host._model_data.get("lines", []), include_section_colors=False)
        self.lines_actor = host._make_wire_actor(lines_pd, line_color, 1.0)
        if self.lines_actor is not None:
            self.renderer.AddActor(self.lines_actor)

        planars = host._model_data.get("planars", [])
        planar_pd = host._build_loops_wire_polydata(planars)
        self.planar_actor = host._make_wire_actor(planar_pd, line_color, 1.0)
        if self.planar_actor is not None:
            self.renderer.AddActor(self.planar_actor)

        planar_faces_pd = host._build_faces_polydata(planars)
        self.planar_faces_actor = host._make_surface_actor(planar_faces_pd, line_color, 0.5)
        if self.planar_faces_actor is not None:
            self.renderer.AddActor(self.planar_faces_actor)

        punctual_pd = host._build_punctual_supports_polydata(host._model_data.get("punctual_supports", []))
        self.support_punctual_actor = host._make_wire_actor(punctual_pd, line_color, 1.0)
        if self.support_punctual_actor is not None:
            self.renderer.AddActor(self.support_punctual_actor)

        linear_sup_pd = host._build_lines_polydata(host._model_data.get("linear_supports", []), include_section_colors=False)
        self.support_linear_actor = host._make_wire_actor(linear_sup_pd, line_color, 1.0)
        if self.support_linear_actor is not None:
            self.renderer.AddActor(self.support_linear_actor)

        planar_supports = host._model_data.get("planar_supports", [])
        planar_sup_pd = host._build_loops_wire_polydata(planar_supports)
        self.support_planar_actor = host._make_wire_actor(planar_sup_pd, line_color, 1.0)
        if self.support_planar_actor is not None:
            self.renderer.AddActor(self.support_planar_actor)

        support_planar_faces_pd = host._build_faces_polydata(planar_supports)
        self.support_planar_faces_actor = host._make_surface_actor(support_planar_faces_pd, line_color, 0.5)
        if self.support_planar_faces_actor is not None:
            self.renderer.AddActor(self.support_planar_faces_actor)

        self.apply_visibility(
            host._show_lines, host._show_planars,
            host._show_support_punctual, host._show_support_linear, host._show_support_planar,
        )
        if self.visible:
            self._fit_camera_to_model()

    def clear_geometry(self):
        for attr in (
            "lines_actor", "planar_actor", "planar_faces_actor",
            "support_punctual_actor", "support_linear_actor",
            "support_planar_actor", "support_planar_faces_actor",
        ):
            actor = getattr(self, attr)
            if actor is not None and self.renderer is not None:
                self.renderer.RemoveActor(actor)
            setattr(self, attr, None)

    def apply_visibility(self, show_lines, show_planars, show_support_punctual, show_support_linear, show_support_planar):
        if self.lines_actor is not None:
            self.lines_actor.SetVisibility(1 if show_lines else 0)
        if self.planar_actor is not None:
            self.planar_actor.SetVisibility(1 if show_planars else 0)
        if self.planar_faces_actor is not None:
            self.planar_faces_actor.SetVisibility(1 if show_planars else 0)
        if self.support_punctual_actor is not None:
            self.support_punctual_actor.SetVisibility(1 if show_support_punctual else 0)
        if self.support_linear_actor is not None:
            self.support_linear_actor.SetVisibility(1 if show_support_linear else 0)
        if self.support_planar_actor is not None:
            self.support_planar_actor.SetVisibility(1 if show_support_planar else 0)
        if self.support_planar_faces_actor is not None:
            self.support_planar_faces_actor.SetVisibility(1 if show_support_planar else 0)

    def _fit_camera_to_model(self, extra_point=None):
        """Cadre la camera minicarte sur les bornes du modele (acteurs de
        geometrie uniquement - marqueur/cone caches pendant le calcul, cf.
        _fit_camera_to_model). `extra_point`, si fourni (x, y, z), est un
        point supplementaire a inclure dans le cadrage (position de la
        camera principale) : necessaire car cette derniere se trouve
        typiquement hors des bornes du modele (vue isometrique, zoom
        arriere...), sinon le marqueur/cone tombe hors du champ visible de
        la minicarte des que l'utilisateur n'est pas exactement a la
        verticale du modele. `self.model_diagonal`/`self.model_zmax`
        restent calcules sur la geometrie seule (taille de l'indicateur
        stable, independante du cadrage elargi)."""
        if self.renderer is None:
            return
        marker_prev_vis = self.marker_actor.GetVisibility() if self.marker_actor is not None else None
        cone_prev_vis = self.cone_actor.GetVisibility() if self.cone_actor is not None else None
        if self.marker_actor is not None:
            self.marker_actor.SetVisibility(0)
        if self.cone_actor is not None:
            self.cone_actor.SetVisibility(0)
        try:
            bounds = [0.0, -1.0, 0.0, -1.0, 0.0, -1.0]
            self.renderer.ComputeVisiblePropBounds(bounds)
        finally:
            if self.marker_actor is not None:
                self.marker_actor.SetVisibility(marker_prev_vis)
            if self.cone_actor is not None:
                self.cone_actor.SetVisibility(cone_prev_vis)
        if bounds[1] < bounds[0]:
            # Aucun acteur/bornes degenerees (modele vide) : rien a cadrer.
            self.model_diagonal = 0.0
            return
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        self.model_diagonal = (dx * dx + dy * dy + dz * dz) ** 0.5
        self.model_zmax = zmax

        frame_bounds = list(bounds)
        if extra_point is not None:
            ex, ey, ez = extra_point
            frame_bounds[0] = min(frame_bounds[0], ex)
            frame_bounds[1] = max(frame_bounds[1], ex)
            frame_bounds[2] = min(frame_bounds[2], ey)
            frame_bounds[3] = max(frame_bounds[3], ey)
            frame_bounds[4] = min(frame_bounds[4], ez)
            frame_bounds[5] = max(frame_bounds[5], ez)

        cx = (frame_bounds[0] + frame_bounds[1]) / 2.0
        cy = (frame_bounds[2] + frame_bounds[3]) / 2.0
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(cx, cy, 0.0)
        camera.SetPosition(cx, cy, 1.0)
        camera.SetViewUp(0.0, 1.0, 0.0)
        self.renderer.ResetCamera(frame_bounds)
        near, far = camera.GetClippingRange()
        camera.SetClippingRange(near, far + max(self.model_diagonal, 1.0))

    def sync_tick(self):
        if not self.visible or self.renderer is None:
            return
        host = self.host
        main_camera = host.renderer.GetActiveCamera() if host.renderer is not None else None
        if main_camera is None:
            return

        mtime = main_camera.GetMTime()
        if mtime == self._last_camera_mtime:
            return
        self._last_camera_mtime = mtime

        px, py, pz = main_camera.GetPosition()
        fx, fy, fz = main_camera.GetFocalPoint()
        dx, dy = fx - px, fy - py

        marker_z = self.model_zmax + 0.001 * max(self.model_diagonal, 1.0)
        self._fit_camera_to_model(extra_point=(px, py, marker_z))
        self.marker_actor.SetPosition(px, py, marker_z)
        radius = max(self.model_diagonal * 0.01, 1e-3)
        self.marker_actor.SetScale(radius, radius, 1.0)

        is_parallel = bool(main_camera.GetParallelProjection())
        w, h = host.renderer.GetSize() if host.renderer is not None else (1, 1)
        aspect = (w / h) if h else 1.0
        half_fov = horizontal_half_fov_deg(main_camera.GetViewAngle(), aspect, is_parallel=is_parallel)
        cone_size = max(self.model_diagonal * 0.15, 1e-3)
        triangle = camera_fov_triangle((px, py), (dx, dy), half_fov, cone_size)

        poly = self.cone_actor.GetMapper().GetInput()
        pts = poly.GetPoints()
        for i, (x, y) in enumerate(triangle):
            pts.SetPoint(i, x, y, marker_z)
        pts.Modified()

        if host.render_window is not None:
            host.render_window.Render()

    def set_visible(self, visible: bool):
        visible = bool(visible)
        if visible == self.visible:
            return
        self.visible = visible
        if visible:
            if self.host.render_window is not None:
                self.host.render_window.AddRenderer(self.renderer)
            self.frame_actor.SetVisibility(True)
            self.update_viewport()
            self.timer.start()
            self.sync_tick()
        else:
            self.timer.stop()
            if self.host.render_window is not None:
                self.host.render_window.RemoveRenderer(self.renderer)
            self.frame_actor.SetVisibility(False)
            if self.host.render_window is not None:
                self.host.render_window.Render()
