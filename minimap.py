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
