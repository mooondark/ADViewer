# -*- coding: utf-8 -*-
"""
flight_navigation.py
Mode Navigation (camera libre) du viewer 3D : fonctions de calcul pur
(deplacement, regard, position sure), l'overlay de controles, et le
controleur d'etat (FlightController) qui pilote la camera VTK.

Extrait de VTKViewerWidget (viewer_widget.py). FlightController garde une
reference vers le widget hote pour les quelques points reellement partages
avec les autres modes d'interaction (style neutre, exclusion mutuelle avec
la selection/zoom par fenetre, overlay de vue, fit_view) - ce n'est pas un
composant totalement independant, mais un sous-ensemble de responsabilite
isole et testable separement (voir tests/test_flight_mode.py).
"""

import math
import time

import vtk
from PySide6.QtCore import QTimer

import viewer_config as _cfg
from viewer_config import (
    FLIGHT_DEFAULT_SPEED, FLIGHT_FAST_MULTIPLIER, FLIGHT_SLOW_MULTIPLIER,
    FLIGHT_MOUSE_SENSITIVITY, FLIGHT_VERTICAL_SPEED_FACTOR, FLIGHT_PITCH_LIMIT_DEG,
    FLIGHT_NEAR_CLIP,
)

# Distance fixe (unites modele) utilisee pour placer le point focal devant la
# camera pendant le regard - seule la direction compte, une distance fixe
# evite les soucis numeriques si la distance d'origine etait tres petite ou
# tres grande.
LOOK_DISTANCE = 10.0


# ----------------------------------------------------------------------
# Fonctions de calcul pur, testables sans fenetre VTK reelle.
# ----------------------------------------------------------------------

def direction_vectors(yaw: float):
    """Vecteurs forward/right/up pour le deplacement : forward est la
    direction de visee horizontale (independante du pitch), up est l'axe
    Z mondial fixe - voir section 3 de la spec."""
    forward = (math.sin(yaw), math.cos(yaw), 0.0)
    right = (math.cos(yaw), -math.sin(yaw), 0.0)
    up = (0.0, 0.0, 1.0)
    return forward, right, up


def look_direction(yaw: float, pitch: float):
    """Direction de visee complete (regard), meme convention azimut/
    elevation que scene_light.azimuth_elevation_to_position (yaw=azimut,
    pitch=elevation, distance=1)."""
    cp = math.cos(pitch)
    return (cp * math.sin(yaw), cp * math.cos(yaw), math.sin(pitch))


def movement_vector(keys_held: set, forward, right, up, key_bindings: dict):
    """Somme les contributions des touches actives puis normalise le
    resultat (une touche en diagonale ne va pas plus vite qu'une seule)."""
    ax, ay, az = 0.0, 0.0, 0.0
    if key_bindings.get("forward") in keys_held:
        ax, ay, az = ax + forward[0], ay + forward[1], az + forward[2]
    if key_bindings.get("backward") in keys_held:
        ax, ay, az = ax - forward[0], ay - forward[1], az - forward[2]
    if key_bindings.get("right") in keys_held:
        ax, ay, az = ax + right[0], ay + right[1], az + right[2]
    if key_bindings.get("left") in keys_held:
        ax, ay, az = ax - right[0], ay - right[1], az - right[2]
    if key_bindings.get("up") in keys_held:
        ax, ay, az = ax + up[0], ay + up[1], az + up[2]
    if key_bindings.get("down") in keys_held:
        ax, ay, az = ax - up[0], ay - up[1], az - up[2]
    length = math.sqrt(ax * ax + ay * ay + az * az)
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (ax / length, ay / length, az / length)


def safe_position(position, bounds, view_direction, margin_ratio: float = 0.02):
    """Heuristique par boite englobante (pas une vraie collision, cf.
    section 6 de la spec) : si la position est a l'interieur (ou trop
    proche) de la boite visible, on la repousse le long de l'axe
    centre -> position jusqu'a une distance sure a l'exterieur. Cas
    degenere (position == centre exact) : repli sur -view_direction."""
    if bounds is None:
        return tuple(position)
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    cx, cy, cz = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0
    diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    if diag < 1e-9:
        return tuple(position)
    margin = diag * margin_ratio
    px, py, pz = position
    inside = (
        xmin - margin <= px <= xmax + margin
        and ymin - margin <= py <= ymax + margin
        and zmin - margin <= pz <= zmax + margin
    )
    if not inside:
        return tuple(position)
    vx, vy, vz = px - cx, py - cy, pz - cz
    vlen = math.sqrt(vx * vx + vy * vy + vz * vz)
    if vlen < 1e-9:
        dvx, dvy, dvz = view_direction
        dlen = math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz) or 1.0
        vx, vy, vz, vlen = -dvx / dlen, -dvy / dlen, -dvz / dlen, 1.0
    safe_distance = diag / 2.0 + margin
    scale = safe_distance / vlen
    return (cx + vx * scale, cy + vy * scale, cz + vz * scale)


def clamp_pitch(pitch: float, limit: float) -> float:
    """Borne le tangage pour eviter que la camera ne se retourne (critere
    d'acceptation de la spec) - fonction pure, testable independamment du
    reste de FlightController.on_mouse_move."""
    return max(-limit, min(limit, pitch))


def controls_overlay_text(key_bindings: dict) -> str:
    def pair(action_a, action_b):
        return f"{key_bindings.get(action_a, '?').upper()}/{key_bindings.get(action_b, '?').upper()}"
    lines = [
        f"{_cfg.tr_ui('flight_control_forward_back')} : {pair('forward', 'backward')}",
        f"{_cfg.tr_ui('flight_control_left_right')} : {pair('left', 'right')}",
        f"{_cfg.tr_ui('flight_control_up_down')} : {pair('up', 'down')}",
        _cfg.tr_ui("flight_control_look"),
        _cfg.tr_ui("flight_control_fast"),
        _cfg.tr_ui("flight_control_slow"),
        _cfg.tr_ui("flight_control_reset"),
        _cfg.tr_ui("flight_control_exit"),
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Overlay de controles (haut-droite, visible uniquement pendant le mode).
# ----------------------------------------------------------------------

class FlightControlsOverlay:
    def __init__(self):
        self.actor = None

    def create(self, renderer):
        actor = vtk.vtkTextActor()
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        actor.GetPositionCoordinate().SetValue(0.988, 0.985)
        actor.SetTextScaleModeToNone()
        actor.SetPickable(False)
        actor.SetVisibility(False)
        tp = actor.GetTextProperty()
        tp.SetFontFamilyToArial()
        tp.SetFontSize(12)
        tp.SetJustificationToRight()
        tp.SetVerticalJustificationToTop()
        tp.SetLineSpacing(1.2)
        tp.ShadowOff()
        self.actor = actor
        renderer.AddViewProp(actor)

    def show(self, text):
        if self.actor is not None:
            self.actor.SetInput(text)
            self.actor.SetVisibility(True)

    def hide(self):
        if self.actor is not None:
            self.actor.SetVisibility(False)

    def apply_theme(self, color):
        if self.actor is not None:
            self.actor.GetTextProperty().SetColor(*color)


# ----------------------------------------------------------------------
# Controleur d'etat : pilote la camera VTK du widget hote.
# ----------------------------------------------------------------------

class FlightController:
    """Mode Navigation (camera libre). `host` est le VTKViewerWidget qui le
    possede - FlightController s'appuie sur host.renderer, host.interactor,
    host.vtk_widget, host.interactor_style, host._ensure_plain_style(),
    host._get_visible_bounds(), host.fit_view(), host._update_view_overlay()
    et host.flightModeChanged (signal Qt, doit rester sur le widget)."""

    def __init__(self, host):
        self.host = host
        self.active = False
        self.timer = None
        self.keys_held = set()
        self.key_bindings = {}
        self.yaw = 0.0
        self.pitch = 0.0
        self.looking = False
        self.last_look_pos = (0, 0)
        self.last_tick = 0.0
        self.saved_camera_state = None
        self.overlay = FlightControlsOverlay()

    def setup_overlay(self):
        self.overlay.create(self.host.renderer)
        self.host._apply_view_overlay_theme()

    def apply_overlay_theme(self, color):
        self.overlay.apply_theme(color)

    def activate(self):
        host = self.host
        if self.active:
            return
        if host._window_select_mode:
            host.set_window_select_mode(False)
        if host._zoom_window_mode:
            host.set_zoom_window_mode(False)
        camera = host.renderer.GetActiveCamera()
        self.saved_camera_state = {
            "position": camera.GetPosition(),
            "focal_point": camera.GetFocalPoint(),
            "view_up": camera.GetViewUp(),
            "view_angle": camera.GetViewAngle(),
            "parallel_projection": bool(camera.GetParallelProjection()),
        }
        # Seule la projection change (perspective, necessaire pour une camera
        # libre) : le champ de vision (ViewAngle) n'est pas touche, pour ne
        # pas modifier le niveau de zoom apparent a l'activation du mode.
        camera.SetParallelProjection(0)

        px, py, pz = camera.GetPosition()
        fx, fy, fz = camera.GetFocalPoint()
        direction = camera.GetDirectionOfProjection()
        bounds = host._get_visible_bounds()
        safe = safe_position((px, py, pz), bounds, direction)
        if safe != (px, py, pz):
            ddx, ddy, ddz = fx - px, fy - py, fz - pz
            camera.SetPosition(*safe)
            camera.SetFocalPoint(safe[0] + ddx, safe[1] + ddy, safe[2] + ddz)

        self._resync_yaw_pitch_from_camera()

        self.keys_held = set()
        self.key_bindings = _cfg.get_flight_key_bindings()
        self.looking = False
        self.last_look_pos = (0, 0)
        self.active = True

        host.interactor.SetInteractorStyle(host._ensure_plain_style())
        host.vtk_widget.setFocus()

        self._clamp_clip_and_render()
        self._show_overlay()

        self.last_tick = time.monotonic()
        if self.timer is None:
            self.timer = QTimer(host)
            self.timer.setInterval(16)
            self.timer.timeout.connect(self.tick)
        self.timer.start()

    def deactivate(self):
        host = self.host
        if not self.active:
            return
        self.active = False
        if self.timer is not None:
            self.timer.stop()
        self.keys_held = set()
        self.looking = False
        state = self.saved_camera_state
        if state is not None:
            # On quitte le mode a la position/orientation atteinte (pas de
            # retour a la position de depart) : seule la projection
            # (orthogonale/perspective) redevient celle d'avant l'activation.
            camera = host.renderer.GetActiveCamera()
            camera.SetParallelProjection(1 if state["parallel_projection"] else 0)
            self.saved_camera_state = None
        host.interactor.SetInteractorStyle(host.interactor_style)
        host.renderer.ResetCameraClippingRange()
        self._hide_overlay()
        if host.render_window is not None:
            host.render_window.Render()
        host._update_view_overlay()

    def _resync_yaw_pitch_from_camera(self):
        """Recalcule yaw/pitch a partir de la direction reelle de la camera.
        A appeler avant tout usage de yaw/pitch qui pourrait suivre un
        changement de camera hors mode Navigation (boutons de vue,
        raccourcis Alt+...)."""
        camera = self.host.renderer.GetActiveCamera()
        direction = camera.GetDirectionOfProjection()
        dnorm = math.sqrt(sum(c * c for c in direction)) or 1.0
        dx, dy, dz = direction[0] / dnorm, direction[1] / dnorm, direction[2] / dnorm
        self.pitch = math.asin(max(-1.0, min(1.0, dz)))
        self.yaw = math.atan2(dx, dy)

    def _clamp_clip_and_render(self):
        host = self.host
        host.renderer.ResetCameraClippingRange()
        camera = host.renderer.GetActiveCamera()
        near, far = camera.GetClippingRange()
        if near < FLIGHT_NEAR_CLIP:
            camera.SetClippingRange(FLIGHT_NEAR_CLIP, far)
        if host.render_window is not None:
            host.render_window.Render()

    def apply_look(self):
        host = self.host
        camera = host.renderer.GetActiveCamera()
        px, py, pz = camera.GetPosition()
        dx, dy, dz = look_direction(self.yaw, self.pitch)
        camera.SetFocalPoint(px + dx * LOOK_DISTANCE, py + dy * LOOK_DISTANCE, pz + dz * LOOK_DISTANCE)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.OrthogonalizeViewUp()
        self._clamp_clip_and_render()

    def tick(self):
        host = self.host
        if not self.active or host.renderer is None:
            return
        if not host.vtk_widget.hasFocus():
            self.keys_held = set()
            return
        self._resync_yaw_pitch_from_camera()
        now = time.monotonic()
        dt = now - self.last_tick
        self.last_tick = now
        if dt <= 0.0 or dt > 0.5:
            return
        # Avancer/reculer suit la direction de visee complete (yaw + pitch),
        # pour pouvoir plonger/remonter en avancant. Gauche/droite (strafe)
        # et monter/descendre restent horizontaux/verticaux purs.
        _, right, up = direction_vectors(self.yaw)
        forward = look_direction(self.yaw, self.pitch)
        move = movement_vector(self.keys_held, forward, right, up, self.key_bindings)
        if move == (0.0, 0.0, 0.0):
            return
        if host.interactor is not None and host.interactor.GetShiftKey():
            multiplier = FLIGHT_FAST_MULTIPLIER
        elif host.interactor is not None and host.interactor.GetControlKey():
            multiplier = FLIGHT_SLOW_MULTIPLIER
        else:
            multiplier = 1.0
        speed = FLIGHT_DEFAULT_SPEED * multiplier * dt
        dx = move[0] * speed
        dy = move[1] * speed
        dz = move[2] * speed * FLIGHT_VERTICAL_SPEED_FACTOR
        camera = host.renderer.GetActiveCamera()
        px, py, pz = camera.GetPosition()
        fx, fy, fz = camera.GetFocalPoint()
        camera.SetPosition(px + dx, py + dy, pz + dz)
        camera.SetFocalPoint(fx + dx, fy + dy, fz + dz)
        self._clamp_clip_and_render()

    def _show_overlay(self):
        self.host._update_view_overlay(render=False)
        self.overlay.show(controls_overlay_text(self.key_bindings))

    def _hide_overlay(self):
        self.overlay.hide()

    # --- gestionnaires d'evenements, appeles depuis le dispatch de VTKViewerWidget ---

    def on_right_button_press(self):
        self._resync_yaw_pitch_from_camera()
        self.looking = True
        self.last_look_pos = self.host.interactor.GetEventPosition()

    def on_right_button_release(self):
        self.looking = False

    def on_mouse_move(self):
        if not self.looking:
            return
        host = self.host
        x, y = host.interactor.GetEventPosition()
        last_x, last_y = self.last_look_pos
        dx = x - last_x
        dy = y - last_y
        self.last_look_pos = (x, y)
        self.yaw += math.radians(dx * FLIGHT_MOUSE_SENSITIVITY)
        self.pitch -= math.radians(dy * FLIGHT_MOUSE_SENSITIVITY)
        self.pitch = clamp_pitch(self.pitch, math.radians(FLIGHT_PITCH_LIMIT_DEG))
        self.apply_look()

    def on_key_press(self, key):
        if key in ("Escape", "escape"):
            self.host.set_flight_mode(False)
            return
        if key == "Home":
            self.host.fit_view()
            return
        self.keys_held.add(key.lower())

    def on_key_release(self, key):
        self.keys_held.discard(key.lower())
