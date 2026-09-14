# -*- coding: utf-8 -*-
"""
test_loads_progress.py
Garde-fou du callback de progression des charges (ponctuelles/lineaires/
surfaciques) : progress_cb doit etre appele une fois par charge traitee,
meme quand une charge est ignoree en cours de boucle (continue).

Depend de vtk (PySide6). `python test_loads_progress.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk

from viewer_widget import VTKViewerWidget


def _widget():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._punctual_load_data = []
    return w


def test_punctual_progress_cb_called_once_per_load():
    w = _widget()
    loads = [
        {"pos": (0, 0, 0), "fx": 1.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
        {"pos": (1, 0, 0), "fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},  # force nulle
        {"pos": (2, 0, 0), "fx": 2.0, "fy": 0.0, "fz": 0.0, "mx": 1.0, "my": 0.0, "mz": 0.0},
    ]
    calls = []
    w._build_punctual_load_polydata_batch(loads, 1.0, progress_cb=lambda: calls.append(1))
    assert len(calls) == 3, calls


def test_linear_progress_cb_called_once_per_load():
    w = _widget()
    loads = [
        {"pt_start": (0, 0, 0), "pt_end": (4, 0, 0), "fx": 1.0, "fy": 0.0, "fz": 0.0,
         "mx": 0.0, "my": 0.0, "mz": 0.0, "coeff1": 1.0, "coeff2": 1.0},
        {"pt_start": (0, 1, 0), "pt_end": (4, 1, 0), "fx": 0.0, "fy": 0.0, "fz": 0.0,
         "mx": 0.0, "my": 0.0, "mz": 0.0, "coeff1": 1.0, "coeff2": 1.0},
    ]
    calls = []
    w._build_linear_load_polydata_batch(loads, 1.0, global_data=loads, progress_cb=lambda: calls.append(1))
    assert len(calls) == 2, calls


def test_planar_progress_cb_called_once_per_load_including_skipped():
    w = _widget()
    loads = [
        {"pts": [(0, 0, 0), (1, 0, 0), (1, 1, 0)], "fx": 1.0, "fy": 0.0, "fz": 0.0,
         "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0},
        {"pts": [(0, 0, 0), (1, 0, 0)], "fx": 1.0, "fy": 0.0, "fz": 0.0,   # < 3 pts -> continue
         "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0},
        {"pts": [(0, 0, 0), (1, 0, 0), (1, 1, 0)], "fx": 0.0, "fy": 0.0, "fz": 0.0,  # force nulle -> continue
         "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0},
    ]
    calls = []
    w._build_planar_load_polydata_batch(loads, 1.0, global_data=loads, progress_cb=lambda: calls.append(1))
    assert len(calls) == 3, calls   # meme les 2 charges ignorees comptent (total coherent avec BuildLoadsWorker)


def _render_widget():
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w.renderer = vtk.vtkRenderer()
    w.render_window = vtk.vtkRenderWindow()
    w.render_window.SetOffScreenRendering(1)
    w.render_window.AddRenderer(w.renderer)
    w._actors = []
    w._selection_overlay_actors = []
    w._diagram_overlay_actors = []
    w._pickable_actors = {}
    w._punctual_load_actors = []
    w._linear_load_actors = []
    w._planar_load_actors = []
    w._punctual_load_data = []
    w._show_punctual_loads = True
    w._show_linear_loads = True
    w._show_planar_loads = False
    w.punctual_load_color = (1.0, 0.0, 0.0)
    w.linear_load_color = (0.0, 1.0, 0.0)
    w.planar_load_color = (0.0, 0.0, 1.0)
    return w


def test_apply_loads_batch_keep_preserves_untouched_actors():
    # Reproduit le cas signale : afficher des charges surfaciques ne doit pas
    # reconstruire les charges ponctuelles/lineaires deja affichees et inchangees.
    w = _render_widget()
    punctual_loads = [{"pos": (0, 0, 0), "fx": 1.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}]
    linear_loads = [{"pt_start": (0, 0, 0), "pt_end": (4, 0, 0), "fx": 1.0, "fy": 0.0, "fz": 0.0,
                      "mx": 0.0, "my": 0.0, "mz": 0.0, "coeff1": 1.0, "coeff2": 1.0}]
    planar_loads = [{"pts": [(0, 0, 0), (1, 0, 0), (1, 1, 0)], "fx": 1.0, "fy": 0.0, "fz": 0.0,
                      "coeff1": 1.0, "coeff2": 1.0, "coeff3": 1.0}]

    # Etape 1 : ponctuelles + lineaires affichees (surfaciques masquees).
    w.apply_loads_polydata_batch({
        "punctual_action": "build",
        "linear_action": "build",
        "planar_action": "clear",
        "punctual": w._build_punctual_load_polydata_batch(punctual_loads, 1.0),
        "linear": w._build_linear_load_polydata_batch(linear_loads, 1.0, global_data=linear_loads),
        "punctual_color": w.punctual_load_color,
        "linear_color": w.linear_load_color,
    })
    assert len(w._punctual_load_actors) >= 1
    assert len(w._linear_load_actors) >= 1
    assert len(w._planar_load_actors) == 0
    punctual_actors_before = list(w._punctual_load_actors)
    linear_actors_before = list(w._linear_load_actors)

    # Etape 2 : l'utilisateur coche "surfaciques" -> seules les surfaciques
    # sont a construire ('build'), ponctuelles/lineaires 'keep'.
    w._show_planar_loads = True
    w.apply_loads_polydata_batch({
        "punctual_action": "keep",
        "linear_action": "keep",
        "planar_action": "build",
        "planar": w._build_planar_load_polydata_batch(planar_loads, 1.0, global_data=planar_loads),
        "planar_color": w.planar_load_color,
    })

    assert len(w._planar_load_actors) > 0
    # Ponctuelles/lineaires inchangees : memes objets acteurs qu'avant (pas de reconstruction).
    assert w._punctual_load_actors == punctual_actors_before
    assert w._linear_load_actors == linear_actors_before


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for _fn in _tests:
        _fn()
        print("ok", _fn.__name__)
    print(f"\n{len(_tests)} tests OK")
