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
        self.support_punctual_actor = None
        self.support_linear_actor = None
        self.support_planar_actor = None

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

    def apply_theme(self, color):
        import viewer_config as _cfg

        if self.frame_actor is not None:
            self.frame_actor.GetProperty().SetColor(*color)
        if self.renderer is not None:
            self.renderer.SetBackground(*_cfg.VTK_BG)

    def set_corner(self, corner: str):
        self.corner = corner if corner in ("bottom_left", "bottom_right") else "bottom_left"
        self.update_viewport()

    def update_viewport(self):
        import viewer_config as _cfg
        from minimap import viewport_rect

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
