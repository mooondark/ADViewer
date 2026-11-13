# -*- coding: utf-8 -*-
"""Pont du ruban (ribbon.RibbonBridge) : boutons, radios, cases, sliders, rechargement des icones."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QPushButton, QSlider

from ribbon import RibbonBridge

_app = QApplication.instance() or QApplication([])


def _build():
    parent = QPushButton()  # parent des actions : evite leur destruction pendant le test
    plain = QPushButton("plain")
    toggle = QPushButton("toggle")
    toggle.setCheckable(True)
    api = QPushButton("api")
    slider = QSlider()
    slider.setRange(0, 100)
    slider.setValue(30)
    box = QAction("box", parent, checkable=True)
    group = QActionGroup(parent)
    group.setExclusive(True)
    left = QAction("left", parent, checkable=True)
    right = QAction("right", parent, checkable=True)
    group.addAction(left)
    group.addAction(right)
    left.setChecked(True)
    spec = [("tab", [("group", [
        ("Plain", plain), ("Toggle", toggle), ("Api", api), ("Slider", slider),
        ("Box", box, "check"), ("", [("Left", left), ("Right", right)], "radios"),
    ])])]
    bridge = RibbonBridge(spec)
    keys = {id(o): k for k, o in bridge._buttons.items()}
    return bridge, {n: keys[id(o)] for n, o in
                    dict(plain=plain, toggle=toggle, api=api, slider=slider, box=box, left=left, right=right).items()}, parent


def test_model_describes_every_item_kind():
    bridge, keys, _p = _build()
    items = bridge.model[0]["groups"][0]["items"]
    assert [bool(i.get("slider")) for i in items] == [False, False, False, True, False, False]
    assert items[3]["min"] == 0 and items[3]["max"] == 100
    assert items[4]["check"] is True
    assert [o["label"] for o in items[5]["radios"]] == ["Left", "Right"]
    assert items[5]["w"] > 36


def test_trigger_toggles_a_checkable_button_and_a_checkable_action():
    bridge, keys, _p = _build()
    assert bridge.checked(keys["toggle"], 0) is False
    bridge.trigger(keys["toggle"])
    assert bridge.checked(keys["toggle"], 0) is True
    bridge.trigger(keys["box"])
    assert bridge.checked(keys["box"], 0) is True


def test_radios_are_exclusive_and_a_checked_radio_stays_checked():
    bridge, keys, _p = _build()
    bridge.trigger(keys["right"])
    assert bridge.checked(keys["right"], 0) and not bridge.checked(keys["left"], 0)
    bridge.trigger(keys["right"])
    assert bridge.checked(keys["right"], 0)


def test_state_active_property_counts_as_checked_for_plain_buttons():
    bridge, keys, _p = _build()
    assert bridge.checked(keys["api"], 0) is False
    bridge._buttons[keys["api"]].setProperty("stateActive", True)
    assert bridge.checked(keys["api"], 0) is True


def test_slider_value_goes_through_the_bridge():
    bridge, keys, _p = _build()
    assert bridge.value(keys["slider"], 0) == 30
    bridge.setValue(keys["slider"], 60)
    assert bridge._buttons[keys["slider"]].value() == 60


def test_enabled_follows_the_widget():
    bridge, keys, _p = _build()
    bridge._buttons[keys["plain"]].setEnabled(False)
    assert bridge.enabled(keys["plain"], 0) is False


def test_slider_drag_does_not_reload_icons_but_a_toggle_does():
    bridge, keys, _p = _build()
    rev, icon_rev = bridge.rev, bridge.iconRev
    bridge.setValue(keys["slider"], 61)
    assert bridge.rev > rev and bridge.iconRev == icon_rev
    rev, icon_rev = bridge.rev, bridge.iconRev
    bridge.trigger(keys["toggle"])
    assert bridge.rev > rev and bridge.iconRev > icon_rev
    icon_rev = bridge.iconRev
    bridge.set_colors("#fff", "#000", "#555", "#2f6fdb", "#ccc")
    assert bridge.iconRev > icon_rev
