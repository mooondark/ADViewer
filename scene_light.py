# -*- coding: utf-8 -*-
"""
scene_light.py
Calculs et etat pour la lumiere de scene VTK du viewer 3D : conversion
azimut/elevation <-> position XYZ, et repere visuel temporaire (origine ->
position de la lumiere) affiche pendant la boite de dialogue Eclairage.

Extrait de VTKViewerWidget (viewer_widget.py) pour isoler ce sous-ensemble
autonome, sans dependance au reste du viewer.
"""

import math

import vtk

# Position par defaut de la sceneLight : distance fixe (non exposee), azimut/
# elevation calcules a partir de cette position servent de valeurs de reset.
DEFAULT_POSITION = (50.0, 50.0, 80.0)
DEFAULT_INTENSITY = 0.9

GIZMO_COLOR = (1.0, 0.85, 0.2)


def position_to_azimuth_elevation(x: float, y: float, z: float):
    distance = math.sqrt(x * x + y * y + z * z) or 1.0
    azimuth = math.degrees(math.atan2(x, y))
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, z / distance))))
    return azimuth, elevation


def azimuth_elevation_to_position(azimuth_deg: float, elevation_deg: float, distance: float = None):
    if distance is None:
        distance = math.sqrt(sum(c * c for c in DEFAULT_POSITION))
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    x = distance * math.cos(el) * math.sin(az)
    y = distance * math.cos(el) * math.cos(az)
    z = distance * math.sin(el)
    return x, y, z


def default_azimuth_elevation():
    return position_to_azimuth_elevation(*DEFAULT_POSITION)


class SceneLightGizmo:
    """Repere visuel temporaire (origine -> position de la lumiere), affiche
    uniquement pendant que la boite de dialogue Eclairage est ouverte."""

    def __init__(self, renderer, render_window):
        self._renderer = renderer
        self._render_window = render_window
        self._actor = None
        self._source = None

    def show(self, position):
        if self._actor is None:
            source = vtk.vtkLineSource()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(source.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.PickableOff()
            actor.GetProperty().SetColor(*GIZMO_COLOR)
            actor.GetProperty().SetLineWidth(2.0)
            actor.GetProperty().LightingOff()
            self._source = source
            self._actor = actor
            self._renderer.AddActor(actor)
        self._source.SetPoint1(0.0, 0.0, 0.0)
        self._source.SetPoint2(*position)
        self._source.Update()
        self._render_window.Render()

    def hide(self):
        if self._actor is not None:
            self._renderer.RemoveActor(self._actor)
            self._actor = None
            self._source = None
            self._render_window.Render()
