# -*- coding: utf-8 -*-
"""Fenetre principale : configuration, charges, ruban et etat de l'API (config.ini dans un dossier temporaire)."""

import configparser
import os
import sys

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main_window as mw


def _new_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    if app.platformName() == "offscreen":
        pytest.skip("VTK exige un vrai contexte OpenGL (lancer avec QT_QPA_PLATFORM=windows)")
    return mw.MainWindow(app=app)


@pytest.fixture(scope="module")
def _shared(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("viewer")
    patches = pytest.MonkeyPatch()
    patches.setattr(mw, "get_app_dir", lambda: str(tmp_path))
    patches.setattr(mw.UpdateCheckWorker, "start", lambda self: None)     # pas de reseau
    w = _new_window(tmp_path)
    yield w
    w.close()
    w.deleteLater()
    patches.undo()


@pytest.fixture
def window(_shared):
    """Une seule fenetre pour tout le module (la creer coute plusieurs secondes), remise a zero entre les tests."""
    yield _shared
    w = _shared
    w.api_server_process, w.api_server_started_by_viewer, w.project_session = None, False, None
    w._suspend_config_save = False
    w.act_minimap_bottom_left.trigger()
    w.act_minimap_size_large.trigger()
    w.minimap_btn.setChecked(False)
    w.chk_grid.setChecked(True)
    w.zoom_window_btn.setChecked(False)
    w.apply_theme("light")
    w._update_api_button_state()
    w.current_model_data = None
    w._update_window_title()


def _saved(window):
    window.save_config()
    cfg = configparser.ConfigParser()
    cfg.read(window._config_path(), encoding="utf-8")
    return cfg


def test_save_config_writes_the_defaults_without_leaving_a_temp_file(window):
    cfg = _saved(window)
    general = cfg["general"]
    assert general["theme"] == window.theme_name
    assert (general["minimap_corner"], general["minimap_size"]) == ("bottom_left", "large")
    assert general["minimap_visible"] == "false" and general["grid_visible"] == "true"
    assert not os.path.exists(window._config_path() + ".tmp")
    assert {"general", "styles", "colors"} <= set(cfg.sections())


def test_save_config_follows_the_ui_state(window):
    window.act_minimap_bottom_right.trigger()
    window.act_minimap_size_small.trigger()
    window.minimap_btn.setChecked(True)
    window.chk_grid.setChecked(False)
    general = _saved(window)["general"]
    assert (general["minimap_corner"], general["minimap_size"]) == ("bottom_right", "small")
    assert general["minimap_visible"] == "true" and general["grid_visible"] == "false"


def test_save_config_does_nothing_while_saving_is_suspended(window):
    window._suspend_config_save = True
    os.remove(window._config_path())
    window.save_config()
    assert not os.path.exists(window._config_path())


class _Process:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.exit_code = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.exit_code = -9


def _key(window, obj):
    return next(k for k, v in window.ribbon.bridge._buttons.items() if v is obj)


# --- cases et echelles de charges ---------------------------------------------

class _Spy:
    """Appels a _mark_loads_dirty et messages du journal."""

    def __init__(self):
        self.dirty, self.logs = [], []


@pytest.fixture
def loads(window, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(window, "_mark_loads_dirty", lambda *kinds: spy.dirty.append(kinds))
    monkeypatch.setattr(window, "log", lambda text, level="info": spy.logs.append(text))
    return spy


@pytest.mark.parametrize("kind", ["punctual", "linear", "planar"])
def test_load_checkbox_shows_or_hides_that_kind_of_loads(window, loads, kind):
    chk = getattr(window, f"chk_{kind}_loads")
    states = []
    for _ in range(2):
        chk.setChecked(not chk.isChecked())
        states.append(chk.isChecked())
        assert getattr(window.viewer, f"_show_{kind}_loads") == chk.isChecked()
    assert loads.dirty == [(kind,), (kind,)]
    assert loads.logs == [mw.tr_log(f"show_{kind}_loads_{'on' if v else 'off'}") for v in states]


@pytest.mark.parametrize("kind", ["punctual", "linear", "planar"])
def test_load_scale_spinbox_sets_the_viewer_scale_with_a_floor(window, loads, kind):
    spin = getattr(window, f"spin_{kind}_load_scale")
    old_min = spin.minimum()
    try:
        spin.setMinimum(0.0)
        spin.setValue(2.5)
        assert getattr(window.viewer, f"{kind}_load_scale") == 2.5
        spin.setValue(0.0)
        assert getattr(window.viewer, f"{kind}_load_scale") == 0.1
    finally:
        spin.setMinimum(old_min)
        spin.setValue(max(1.0, old_min))
    assert loads.dirty[:2] == [(kind,), (kind,)]


# --- titre de la fenetre -----------------------------------------------------

def test_window_title_shows_the_open_file_only_while_a_model_is_loaded(window):
    base = f"{mw.tr_ui('app_title')} - v{mw.APP_VERSION}"
    window.fto_edit.setText(r"C:\dossier\exemple.fto")
    window._update_window_title()
    assert window.windowTitle() == base                       # champ rempli mais aucun modele charge
    window.current_model_data = {"lines": []}
    window._update_window_title()
    assert window.windowTitle() == base + " (exemple.fto)"
    window.fto_edit.setText("")
    window._update_window_title()
    assert window.windowTitle() == base


# --- ruban -------------------------------------------------------------------

def test_ribbon_has_every_tab_in_order_and_hides_the_driven_widgets(window):
    titles = [t["title"] for t in window.ribbon.bridge.model]
    keys = ["ribbon_tab_home", "ribbon_tab_view", "ribbon_tab_selection", "ribbon_tab_tools",
            "ribbon_tab_check", "menu_settings", "menu_help"]
    assert titles == [mw.tr_ui(k) for k in keys]
    assert not window.fit_btn.isVisible() and not window.transparency_slider.isVisible()


def test_a_ribbon_click_drives_the_real_button(window):
    assert not window.zoom_window_btn.isChecked()
    window.ribbon.bridge.trigger(_key(window, window.zoom_window_btn))
    assert window.zoom_window_btn.isChecked()


def test_ribbon_follows_the_theme(window):
    window.apply_theme("light")
    assert window.ribbon.bridge.theme["panel"] == "#dde4ee"
    window.apply_theme("dark")
    assert window.ribbon.bridge.theme["panel"] != "#dde4ee"


# --- etat de l'API -----------------------------------------------------------

def test_api_buttons_when_the_api_is_stopped(window):
    window._update_api_button_state()
    bridge, off_key = window.ribbon.bridge, _key(window, window.api_off_btn)
    assert not window.api_restart_btn.isEnabled()
    assert bridge.checked(off_key, 0) and not bridge.checked(_key(window, window.api_on_btn), 0)


def test_api_buttons_when_the_api_is_running_and_icons_reload(window):
    window.api_server_process = _Process()
    icon_rev = window.ribbon.bridge.iconRev
    window._update_api_button_state()
    bridge = window.ribbon.bridge
    assert window.api_restart_btn.isEnabled()
    assert bridge.checked(_key(window, window.api_on_btn), 0) and not bridge.checked(_key(window, window.api_off_btn), 0)
    assert bridge.iconRev > icon_rev


def test_a_dead_api_process_is_forgotten(window):
    window.api_server_process = _Process(exit_code=1)
    window.api_server_started_by_viewer = True
    window._update_api_button_state()
    assert window.api_server_process is None and window.api_server_started_by_viewer is False


# --- demarrage et redemarrage de l'API --------------------------------------

def test_start_api_with_a_missing_executable_warns_and_does_not_start(window, monkeypatch, tmp_path):
    warned = []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a: warned.append(a))
    window.api_server_exe = str(tmp_path / "nope.exe")
    window.start_api_server()
    assert warned and window.api_server_process is None


def test_start_api_launches_the_executable_and_checks_the_licence(window, monkeypatch, tmp_path):
    exe = tmp_path / "api.exe"
    exe.write_text("")
    launched, licence = [], []
    monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or _Process())
    monkeypatch.setattr(window, "check_licence_after_api_start", lambda: licence.append(1))
    window.api_server_exe = str(exe)
    window.start_api_server()
    assert launched == [[str(exe), "/console"]] and licence == [1]
    assert window.api_server_started_by_viewer and window.api_restart_btn.isEnabled()


def test_restart_api_reports_success_or_timeout(window, monkeypatch, tmp_path):
    exe = tmp_path / "api.exe"
    exe.write_text("")
    window.api_server_exe = str(exe)
    monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: _Process())
    monkeypatch.setattr(mw, "wait_for_api", lambda host: True)
    assert window._restart_api_server() is True
    monkeypatch.setattr(mw, "wait_for_api", lambda host: False)
    assert window._restart_api_server() is False


def test_restart_api_fails_when_the_executable_is_missing_or_cannot_start(window, monkeypatch, tmp_path):
    window.api_server_exe = str(tmp_path / "nope.exe")
    assert window._restart_api_server() is False
    exe = tmp_path / "api.exe"
    exe.write_text("")
    window.api_server_exe = str(exe)

    def boom(cmd, **kw):
        raise OSError("not executable")

    monkeypatch.setattr(mw.subprocess, "Popen", boom)
    assert window._restart_api_server() is False


def test_reset_between_loads_restarts_the_api_only_when_results_are_open(window, monkeypatch):
    restarts = []
    monkeypatch.setattr(window, "_restart_api_server", lambda: restarts.append(1) or True)
    assert window._reset_api_between_model_loads_if_needed() is True and not restarts   # pas de session

    session = mw.ProjectSessionManager("http://x")
    window.project_session = session
    assert window._reset_api_between_model_loads_if_needed() is True and not restarts   # session sans resultats

    session.keep_open = session.has_results = True
    resets = []
    monkeypatch.setattr(session, "reset_api_session", lambda: resets.append(1))
    assert window._reset_api_between_model_loads_if_needed() is True
    assert restarts == [1] and resets == [1] and window.project_session is None


# --- reglages : ces tests reconstruisent les actions, donc a placer en dernier
# (le ruban de la fenetre partagee pointerait ensuite sur les anciennes actions) ---

DIALOG_ACTIONS = {
    "act_line_widths": "open_settings_dialog", "act_png_export": "open_png_export_dialog",
    "act_units": "open_units_dialog", "act_calc_ef": "open_calc_ef_dialog",
    "act_scene_light": "open_scene_light_dialog", "act_clip_margin": "open_clip_margin_dialog",
    "act_grid": "open_grid_dialog", "act_api_server": "open_configuration_dialog",
    "act_api_url": "open_api_url_dialog",
}


def _rebuild_with_recorder(window, monkeypatch, *methods):
    calls = []
    for m in methods:
        monkeypatch.setattr(window, m, lambda *a, _m=m: calls.append((_m,) + a))
    window._build_settings_actions()
    return calls


def test_each_settings_dialog_action_runs_its_dialog(window, monkeypatch):
    calls = _rebuild_with_recorder(window, monkeypatch, *DIALOG_ACTIONS.values())
    for attr in DIALOG_ACTIONS:
        getattr(window, attr).trigger()
    assert [c[0] for c in calls] == list(DIALOG_ACTIONS.values())


def test_radio_actions_apply_their_value_and_are_exclusive(window, monkeypatch):
    calls = _rebuild_with_recorder(window, monkeypatch, "apply_theme", "apply_view_projection",
                                   "apply_minimap_corner", "apply_minimap_size", "apply_language")
    window.act_theme_dark.trigger()
    window.act_theme_light.trigger()
    window.act_view_projection_orthogonal.trigger()
    window.act_minimap_bottom_right.trigger()
    window.act_minimap_size_small.trigger()
    window.act_languages[1].trigger()
    assert calls == [("apply_theme", "dark"), ("apply_theme", "light"),
                     ("apply_view_projection", "orthogonal"), ("apply_minimap_corner", "bottom_right"),
                     ("apply_minimap_size", "small"), ("apply_language", "en")]
    assert window.act_theme_light.isChecked() and not window.act_theme_dark.isChecked()
    assert not window.act_minimap_bottom_left.isChecked() and window.act_minimap_bottom_right.isChecked()


def test_settings_actions_start_with_the_documented_defaults(window):
    window._build_settings_actions()
    assert window.act_minimap_bottom_left.isChecked() and window.act_minimap_size_large.isChecked()
    assert [a.isChecked() for a in window.act_languages] == [code == mw.get_language() for code in mw.LANGUAGES]
    assert [a.text() for a in window.act_languages] == [label for label, _m in mw.LANGUAGES.values()]
