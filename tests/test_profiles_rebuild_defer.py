# -*- coding: utf-8 -*-
"""Garde-fou : isoler/filtrer pendant que l'affichage est en mode "Profiles"
ne doit pas reconstruire le solide des profils de facon synchrone (ca gele
l'UI sans barre de progression sur un gros modele) - cf. rebuild_profiles /
synchronous=False dans set_isolated_selection / _rebuild_profiles_actor.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viewer_widget import VTKViewerWidget


def _widget(display_mode):
    w = VTKViewerWidget.__new__(VTKViewerWidget)
    w._display_mode = display_mode
    w._profiles_base_pd = "stale"
    w._profiles_base_colors = "stale"
    return w


def test_deferred_rebuild_skips_expensive_build_in_profile_mode():
    w = _widget("profiles_full")

    def _boom(*a, **k):
        raise AssertionError("_build_profiles_polydata ne doit pas etre appele quand synchronous=False")
    w._build_profiles_polydata = _boom

    w._rebuild_profiles_actor(synchronous=False)
    assert w._profiles_base_pd is None  # cache invalide en attendant le rebuild async


def test_synchronous_rebuild_still_works_in_profile_mode():
    w = _widget("profiles_full")
    w._model_data = {"lines": ["L"], "line_sections": ["S"]}
    calls = []
    w._filtered_line_indexes = lambda: [0]
    w._select_items_by_indexes = lambda items, idx: [items[i] for i in idx]
    w._build_profiles_polydata = lambda lines, sections, element_indexes=None: "PD"
    w._apply_profiles_build_result = lambda pd: calls.append(pd)

    w._rebuild_profiles_actor(synchronous=True)
    assert calls == ["PD"]


def test_non_profile_mode_clears_actor_regardless_of_synchronous():
    w = _widget("wireframe")
    cleared = []
    w._replace_actor = lambda name, actor, role=None, pickable=None: cleared.append((name, actor))

    w._rebuild_profiles_actor(synchronous=False)
    assert cleared == [("_profiles_actor", None)]


def test_trigger_during_running_build_is_deferred_not_parallel():
    from main_window import MainWindow

    class _Worker:
        def wait(self):
            pass

    h = MainWindow.__new__(MainWindow)
    h._profiles_worker = _Worker()
    h._profiles_pending_mode = None
    h._trigger_profiles_build("profiles_full")
    h._trigger_profiles_build("profiles_hidden")
    assert isinstance(h._profiles_worker, _Worker)  # aucun 2e worker
    assert h._finish_profiles_worker() == "profiles_hidden"  # derniere demande seule rejouee
    assert h._profiles_worker is None and h._profiles_pending_mode is None


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for _fn in _tests:
        _fn()
        print("ok", _fn.__name__)
    print(f"\n{len(_tests)} tests OK")
