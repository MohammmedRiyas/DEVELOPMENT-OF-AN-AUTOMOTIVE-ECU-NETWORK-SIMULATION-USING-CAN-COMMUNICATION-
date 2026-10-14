"""Shared drawing helpers, palette and base classes.

Every panel is painted in a fixed *design coordinate system* (taken from the
1536x1024 reference) and scaled uniformly to the widget size, so proportions are
preserved on any monitor."""
from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset(*parts: str) -> str:
    return os.path.join(ROOT, "assets", *parts)


# ---------------------------------------------------------------- palette
CYAN = QColor(0, 214, 255)
BLUE = QColor(35, 135, 255)
GREEN = QColor(45, 238, 120)
ORANGE = QColor(255, 150, 40)
RED = QColor(255, 62, 62)
WHITE = QColor(236, 245, 255)
MUTED = QColor(150, 176, 204)
LEVEL_COLOR = {0: None, 1: ORANGE, 2: RED}

FAMILIES = ["Bahnschrift", "Segoe UI", "Inter", "Roboto", "Helvetica Neue", "Arial", "DejaVu Sans"]
MONO = ["Consolas", "Lucida Console", "Courier New", "DejaVu Sans Mono", "monospace"]


def alpha(c: QColor, a: float) -> QColor:
    c2 = QColor(c)
    c2.setAlpha(int(max(0, min(255, a))))
    return c2


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t),
                  int(a.alpha() + (b.alpha() - a.alpha()) * t))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def font(px: float, bold: bool = False, spacing: float = 0.0, families=None, weight=None) -> QFont:
    f = QFont()
    f.setFamilies(families or FAMILIES)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(weight or (QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def draw_text(p: QPainter, s: str, x: float, y: float, px: float, color=WHITE, align: str = "c",
              bold: bool = False, spacing: float = 0.0, families=None, w: float = 500) -> None:
    """Draw text vertically centred on y. align: c / l / r relative to x."""
    p.setFont(font(px, bold, spacing, families))
    p.setPen(color)
    h = px * 2
    if align == "c":
        p.drawText(QRectF(x - w / 2, y - h / 2, w, h), Qt.AlignCenter, s)
    elif align == "l":
        p.drawText(QRectF(x, y - h / 2, w, h), Qt.AlignLeft | Qt.AlignVCenter, s)
    else:
        p.drawText(QRectF(x - w, y - h / 2, w, h), Qt.AlignRight | Qt.AlignVCenter, s)


def stroke_glow(p: QPainter, path: QPainterPath, color: QColor, width: float = 1.4,
                layers=((7, 16), (3.5, 34))) -> None:
    p.setBrush(Qt.NoBrush)
    for extra, a in layers:
        pen = QPen(alpha(color, a), width + extra)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawPath(path)


def glass_panel(p: QPainter, rect: QRectF, radius: float = 14, border: QColor = CYAN,
                fill_a: int = 175, glow: bool = True, top=(16, 40, 72), bottom=(4, 12, 28),
                border_a: int = 210) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0, QColor(*top, fill_a))
    g.setColorAt(1, QColor(*bottom, min(255, fill_a + 45)))
    p.fillPath(path, g)
    sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.5))
    sheen.setColorAt(0, QColor(255, 255, 255, 20))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, sheen)
    if glow:
        stroke_glow(p, path, alpha(border, border_a), 1.2)
    else:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(alpha(border, border_a), 1.2))
        p.drawPath(path)
    return path


class DesignWidget(QWidget):
    """Widget that paints in design coordinates (DW x DH) scaled to its size."""
    DW = 100.0
    DH = 100.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def begin(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                         QPainter.SmoothPixmapTransform)
        p.scale(self.width() / self.DW, self.height() / self.DH)
        return p

    def dpos(self, e) -> QPointF:
        pt = e.position()
        return QPointF(pt.x() * self.DW / max(1, self.width()), pt.y() * self.DH / max(1, self.height()))


class Tween(QObject):
    """Smoothly animates a float and reports every step through a callback."""

    def __init__(self, cb, value: float = 0.0, duration: int = 280, parent=None):
        super().__init__(parent)
        self.value = float(value)
        self.target = float(value)
        self.cb = cb
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(duration)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._step)

    def _step(self, v) -> None:
        self.value = float(v)
        self.cb(self.value)

    def set(self, v: float, immediate: bool = False) -> None:
        v = float(v)
        if v == self.target and not immediate:
            return
        self.target = v
        self.anim.stop()
        if immediate:
            self.value = v
            self.cb(v)
            return
        self.anim.setStartValue(self.value)
        self.anim.setEndValue(v)
        self.anim.start()
