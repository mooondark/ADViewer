# -*- coding: utf-8 -*-
"""Ruban QML (QQuickWidget) qui pilote des QAbstractButton, QSlider et QAction existants."""

import os

from PySide6.QtCore import QEvent, QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QAction, QColor
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QSlider


class _IconProvider(QQuickImageProvider):
    def __init__(self, buttons):
        super().__init__(QQuickImageProvider.Pixmap)
        self._buttons = buttons

    def requestPixmap(self, id, size, requestedSize):
        # id = "<item>?<rev>" ; le rev force le rechargement apres un changement de theme
        return self._buttons[id.split("?")[0]].icon().pixmap(48, 48)


class RibbonBridge(QObject):
    changed = Signal()

    def __init__(self, spec, parent=None):
        """spec = [(titre_onglet, [(titre_groupe, [(libelle, bouton), ...]), ...]), ...]"""
        super().__init__(parent)
        self._buttons = {}
        self._rev = 0
        self._theme = {}
        self._model = []
        for t_title, groups in spec:
            g_model = []
            for g_title, items in groups:
                i_model = []
                for label, btn, *kind in items:
                    key = f"b{len(self._buttons)}"
                    self._buttons[key] = btn
                    if isinstance(btn, QAction):
                        btn.changed.connect(self.refresh)
                        i_model.append({"id": key, "label": label, "check": bool(kind)})
                        continue
                    btn.installEventFilter(self)
                    if isinstance(btn, QSlider):
                        btn.valueChanged.connect(self.refresh)
                        i_model.append({"id": key, "label": label, "slider": True,
                                        "min": btn.minimum(), "max": btn.maximum()})
                        continue
                    if btn.isCheckable():
                        btn.toggled.connect(self.refresh)
                    i_model.append({"id": key, "label": label})
                g_model.append({"title": g_title, "items": i_model})
            self._model.append({"title": t_title, "groups": g_model})

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.EnabledChange, QEvent.ToolTipChange):
            self.refresh()
        return False

    @Slot()
    def refresh(self, *_):
        self._rev += 1
        self.changed.emit()

    def set_colors(self, panel, fg, dim, accent, border):
        a = QColor(accent)
        self._theme = {
            "panel": panel, "fg": fg, "dim": dim, "accent": accent, "border": border,
            "active": QColor(a.red(), a.green(), a.blue(), 70).name(QColor.HexArgb),
            "hover": QColor(a.red(), a.green(), a.blue(), 35).name(QColor.HexArgb),
        }
        self.refresh()

    model = Property("QVariantList", lambda s: s._model, constant=True)
    rev = Property(int, lambda s: s._rev, notify=changed)
    theme = Property("QVariantMap", lambda s: s._theme, notify=changed)

    @Slot(str, int, result=bool)
    def checked(self, key, rev):
        btn = self._buttons[key]
        return btn.isChecked() or bool(btn.property("stateActive"))

    @Slot(str, int, result=bool)
    def enabled(self, key, rev):
        return self._buttons[key].isEnabled()

    @Slot(str, int, result=str)
    def tip(self, key, rev):
        return self._buttons[key].toolTip()

    @Slot(str, int, result=int)
    def value(self, key, rev):
        return self._buttons[key].value()

    @Slot(str, int)
    def setValue(self, key, v):
        self._buttons[key].setValue(v)

    @Slot(str)
    def trigger(self, key):
        btn = self._buttons[key]
        btn.trigger() if isinstance(btn, QAction) else btn.click()


def make_ribbon(spec, colors, parent=None, height=130):
    widget = QQuickWidget(parent)
    bridge = RibbonBridge(spec, widget)
    bridge.set_colors(*colors)  # avant setSource : le QML lit theme des le chargement
    widget.engine().addImageProvider("ribbon", _IconProvider(bridge._buttons))
    widget.rootContext().setContextProperty("bridge", bridge)
    widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
    widget.setFixedHeight(height)
    widget.setSource(QUrl.fromLocalFile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ribbon.qml")))
    widget.bridge = bridge
    return widget
