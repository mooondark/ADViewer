# -*- coding: utf-8 -*-
"""Ombre portee sur les menus et info-bulles. Les coins arrondis et la marge
(place de l'ombre) viennent de la feuille de style (QMenu, QToolTip).
L'ombre est peinte a la main : QGraphicsDropShadowEffect fait echouer
UpdateLayeredWindowIndirect sur une fenetre translucide quand une partie seulement est repeinte."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QMenu

# marge (px) = marge QSS de QMenu / QToolTip ; l'ombre se peint dedans
MENU_MARGIN = 10
TIP_MARGIN = 6
RADIUS = 8
SHADOW_ALPHA = 80  # opacite cumulee au pied de l'objet


def _is_popup(obj):
    return isinstance(obj, QMenu) or obj.metaObject().className() == "QTipLabel"


class PopupShadowFilter(QObject):
    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Polish and _is_popup(obj):
            obj.setWindowFlag(Qt.FramelessWindowHint, True)
            obj.setWindowFlag(Qt.NoDropShadowWindowHint, True)
            obj.setAttribute(Qt.WA_TranslucentBackground, True)
        elif kind == QEvent.Paint and _is_popup(obj):
            painter = QPainter(obj)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            margin = MENU_MARGIN if isinstance(obj, QMenu) else TIP_MARGIN
            painter.setBrush(QColor(0, 0, 0, SHADOW_ALPHA // margin))
            body = obj.rect().adjusted(margin, margin, -margin, -margin).translated(0, 2)
            for k in range(margin - 1, 0, -1):  # de l'exterieur vers l'interieur
                painter.drawRoundedRect(body.adjusted(-k, -k, k, k), RADIUS + k, RADIUS + k)
            painter.end()
        return False
