"""Custom-painted circular speedometer and tachometer."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QLinearGradient, QPainterPath,
                           QPen, QRadialGradient)

from .common import (BLUE, CYAN, GREEN, MUTED, ORANGE, RED, WHITE, DesignWidget, Tween, alpha,
                     clamp, draw_text, glass_panel, mix, stroke_glow)
from .icons import icon_at

START, SWEEP = 135.0, 270.0           # screen angle (clockwise from east) of the 0 mark, sweep


def _a(f: float) -> float:
    return math.radians(START + SWEEP * f)


def _pt(cx, cy, r, f) -> QPointF:
    a = _a(f)
    return QPointF(cx + r * math.cos(a), cy + r * math.sin(a))


class GaugeBase(DesignWidget):
    DW, DH = 400.0, 400.0
    CX, CY = 200.0, 182.0
    R_BEZEL, R_FACE, R_ARC, R_TICK, R_LABEL = 178.0, 165.0, 150.0, 138.0, 107.0
    VMAX, MAJOR, MINOR = 1.0, 1.0, 0.5
    LABEL_PX = 19

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.level = 0
        self._tw = Tween(self._on_value, 0.0, 320, self)

    def _on_value(self, v: float) -> None:
        self.value = v
        self.update()

    def set_target(self, v: float) -> None:
        self._tw.set(v)

    def set_level(self, lv: int) -> None:
        if lv != self.level:
            self.level = lv
            self.update()

    def frac(self) -> float:
        return clamp(self.value / self.VMAX, 0.0, 1.0)

    def label(self, v: float) -> str:
        return str(int(round(v)))

    def tick_color(self, v: float) -> QColor:
        return WHITE

    # ----------------------------------------------------------- drawing
    def arc(self, p, r, f0, f1) -> None:
        rect = QRectF(self.CX - r, self.CY - r, 2 * r, 2 * r)
        p.drawArc(rect, int(-(START + SWEEP * f0) * 16), int(-SWEEP * (f1 - f0) * 16))

    def draw_bezel(self, p) -> None:
        c = QPointF(self.CX, self.CY)
        sh = QRadialGradient(c, self.R_BEZEL + 26)
        sh.setColorAt(0.84, QColor(0, 150, 255, 40))
        sh.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sh))
        p.drawEllipse(c, self.R_BEZEL + 26, self.R_BEZEL + 26)
        metal = QConicalGradient(c, 30)
        for pos, col in ((0, (38, 56, 80)), (.2, (12, 22, 38)), (.4, (70, 96, 124)), (.6, (14, 24, 40)),
                         (.8, (58, 80, 106)), (1, (38, 56, 80))):
            metal.setColorAt(pos, QColor(*col))
        p.setBrush(QBrush(metal))
        p.drawEllipse(c, self.R_BEZEL, self.R_BEZEL)
        for r, a in ((self.R_BEZEL - .5, 190), (self.R_FACE + 7, 120)):
            path = QPainterPath()
            path.addEllipse(c, r, r)
            stroke_glow(p, path, alpha(CYAN, a), 1.3, layers=((6, 14), (3, 30)))
        face = QRadialGradient(QPointF(self.CX - 20, self.CY - 30), self.R_FACE * 1.25)
        face.setColorAt(0, QColor(14, 40, 72))
        face.setColorAt(.65, QColor(6, 20, 42))
        face.setColorAt(1, QColor(2, 8, 18))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(face))
        p.drawEllipse(c, self.R_FACE, self.R_FACE)
        # glass reflection on the upper part of the face
        circle = QPainterPath()
        circle.addEllipse(c, self.R_FACE - 2, self.R_FACE - 2)
        top = QPainterPath()
        top.addEllipse(QPointF(self.CX - 10, self.CY - self.R_FACE * 0.95), self.R_FACE * 1.0, self.R_FACE * 0.8)
        g = QLinearGradient(self.CX, self.CY - self.R_FACE, self.CX, self.CY)
        g.setColorAt(0, QColor(255, 255, 255, 26))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(circle.intersected(top), g)
        p.setPen(QPen(QColor(120, 190, 255, 24), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, 92, 92)

    def draw_scale(self, p) -> None:
        n = int(round(self.VMAX / self.MINOR))
        for i in range(n + 1):
            v = i * self.MINOR
            major = abs(v / self.MAJOR - round(v / self.MAJOR)) < 1e-6
            col = self.tick_color(v)
            r_in = self.R_TICK - (12 if major else 5)
            pen = QPen(alpha(col, 235 if major else 120), 2.6 if major else 1.3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            f = v / self.VMAX
            p.drawLine(_pt(self.CX, self.CY, self.R_TICK + 2, f), _pt(self.CX, self.CY, r_in, f))
            if major:
                q = _pt(self.CX, self.CY, self.R_LABEL, f)
                draw_text(p, self.label(v), q.x(), q.y(), self.LABEL_PX, alpha(col, 235), w=60)

    def draw_zones(self, p) -> None:
        pass

    def draw_progress(self, p) -> None:
        f = self.frac()
        R = self.R_ARC
        pen = QPen(QColor(120, 170, 220, 95), 2.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        self.arc(p, R, 0, 1)
        self.draw_zones(p)
        if f <= 0.003:
            return
        base = (CYAN, ORANGE, RED)[self.level]
        deep = (QColor(20, 105, 255), QColor(190, 80, 20), QColor(150, 25, 30))[self.level]
        for w, a in ((28, 20), (19, 34)):
            pen = QPen(alpha(base, a), w)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            self.arc(p, R, 0, f)
        n = max(2, int(f * 90))
        for i in range(n):
            t = (i + 1) / n
            col = mix(deep, base, t)
            col = mix(col, WHITE, max(0.0, (t - 0.88) / 0.12) * 0.75)
            p.setPen(QPen(col, 10.5, Qt.SolidLine, Qt.FlatCap))
            self.arc(p, R, f * i / n, min(1.0, f * (i + 1) / n + 0.002))
        # glowing needle tip
        a, b = _pt(self.CX, self.CY, R - 16, f), _pt(self.CX, self.CY, R + 12, f)
        path = QPainterPath(a)
        path.lineTo(b)
        stroke_glow(p, path, WHITE, 2.8, layers=((6, 30), (3, 70)))

    def draw_center(self, p) -> None:
        pass

    def draw_extra(self, p) -> None:
        pass

    def paintEvent(self, e) -> None:
        p = self.begin()
        self.draw_bezel(p)
        self.draw_scale(p)
        self.draw_progress(p)
        self.draw_center(p)
        self.draw_extra(p)


class SpeedGauge(GaugeBase):
    VMAX, MAJOR, MINOR = 220.0, 20.0, 10.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gear = "D"
        self.fuel = 75.0
        self._fuel_tw = Tween(self._on_fuel, 75.0, 400, self)

    def _on_fuel(self, v):
        self.fuel = v
        self.update()

    def set_gear(self, g: str) -> None:
        if g != self.gear:
            self.gear = g
            self.update()

    def set_fuel(self, v: float) -> None:
        self._fuel_tw.set(v)

    def draw_center(self, p) -> None:
        draw_text(p, str(int(round(self.value))), self.CX, 156, 84, WHITE, bold=True, w=240)
        draw_text(p, "km/h", self.CX, 212, 27, QColor(205, 222, 240), w=200)
        box = QRectF(self.CX - 40, 250, 80, 46)
        glass_panel(p, box, 10, CYAN, 150, top=(12, 46, 80), bottom=(5, 20, 40))
        draw_text(p, self.gear, self.CX, 273, 32, WHITE, bold=True, w=70)

    def draw_extra(self, p) -> None:
        cx, cy, R = 200.0, 512.0, 184.0
        lvl_col = GREEN if False else (RED if self.fuel < 7 else ORANGE if self.fuel < 15 else CYAN)
        left, span = 142.0, -104.0                      # Qt angles: left end, clockwise sweep
        rect = QRectF(cx - R, cy - R, 2 * R, 2 * R)
        pen = QPen(QColor(4, 14, 30, 215), 26, Qt.SolidLine, Qt.FlatCap)
        p.setPen(pen)
        p.drawArc(rect, int(left * 16), int(span * 16))
        outer = QRectF(cx - R - 14, cy - R - 14, 2 * R + 28, 2 * R + 28)
        path = QPainterPath()
        path.arcMoveTo(outer, left)
        path.arcTo(outer, left, span)
        stroke_glow(p, path, alpha(CYAN, 150), 1.2, layers=((5, 12), (2.5, 26)))
        inner = QRectF(cx - R + 14, cy - R + 14, 2 * R - 28, 2 * R - 28)
        path = QPainterPath()
        path.arcMoveTo(inner, left)
        path.arcTo(inner, left, span)
        p.setPen(QPen(alpha(CYAN, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        fr = clamp(self.fuel / 100.0, 0, 1)
        p.setPen(QPen(QColor(30, 60, 90, 120), 7, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(rect, int(left * 16), int(span * 16))
        if fr > 0.002:
            for w, a in ((16, 36),):
                pen = QPen(alpha(lvl_col, a), w)
                p.setPen(pen)
                p.drawArc(rect, int(left * 16), int(span * fr * 16))
            pen = QPen(lvl_col, 7, Qt.SolidLine, Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(left * 16), int(span * fr * 16))
        for i in range(0, 11):
            ang = math.radians(left + span * i / 10)
            r1, r2 = R + 10, R + (15 if i % 5 == 0 else 13)
            p.setPen(QPen(alpha(WHITE, 190 if i % 5 == 0 else 100), 1.3))
            p.drawLine(QPointF(cx + r1 * math.cos(ang), cy - r1 * math.sin(ang)),
                       QPointF(cx + r2 * math.cos(ang), cy - r2 * math.sin(ang)))
        draw_text(p, "E", 92, 366, 18, QColor(205, 222, 240), w=30)
        draw_text(p, "F", 292, 364, 18, QColor(205, 222, 240), w=30)
        icon_at(p, "fuel", 172, 358, 30, WHITE, 6)
        draw_text(p, f"{int(round(self.fuel))} %", 192, 357, 21, WHITE, align="l", bold=True, w=90)


class TachGauge(GaugeBase):
    VMAX, MAJOR, MINOR = 8.0, 1.0, 0.25
    LABEL_PX = 21
    RED_START = 6.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.temp = 85.0
        self._temp_tw = Tween(self._on_temp, 85.0, 400, self)

    def _on_temp(self, v):
        self.temp = v
        self.update()

    def set_rpm(self, rpm: float) -> None:
        self.set_target(rpm / 1000.0)

    def set_temp(self, t: float) -> None:
        self._temp_tw.set(t)

    def label(self, v: float) -> str:
        return str(int(round(v)))

    def tick_color(self, v: float) -> QColor:
        return mix(WHITE, ORANGE, 1.0) if v >= self.RED_START else WHITE

    def draw_zones(self, p) -> None:
        f0 = self.RED_START / self.VMAX
        n = 24
        for w, a in ((22, 14),):
            p.setPen(QPen(QColor(255, 90, 40, a), w))
            self.arc(p, self.R_ARC, f0, 1)
        for i in range(n):
            t = i / (n - 1)
            p.setPen(QPen(mix(QColor(255, 150, 40), QColor(255, 50, 30), t), 10.5, Qt.SolidLine, Qt.FlatCap))
            self.arc(p, self.R_ARC, f0 + (1 - f0) * i / n, f0 + (1 - f0) * (i + 1) / n + 0.002)

    def draw_center(self, p) -> None:
        draw_text(p, str(int(round(self.value * 1000 / 10.0) * 10)), self.CX, 164, 62, WHITE, bold=True, w=260)
        draw_text(p, "RPM", self.CX, 217, 26, QColor(205, 222, 240), w=200)
        draw_text(p, "x1000", self.CX, 256, 16, MUTED, w=200)

    def draw_extra(self, p) -> None:
        glass_panel(p, QRectF(88, 322, 268, 64), 30, CYAN, 190, top=(8, 24, 46), bottom=(3, 10, 22))
        t = clamp((self.temp - 40) / 80.0, 0, 1)
        icon_at(p, "thermo", 112, 354, 26, WHITE, 6)
        draw_text(p, "C", 140, 368, 16, WHITE, w=30)
        draw_text(p, "H", 330, 368, 16, WHITE, w=30)
        bar = QRectF(148, 337, 168, 12)
        path = QPainterPath()
        path.addRoundedRect(bar, 6, 6)
        p.fillPath(path, QColor(10, 30, 56))
        g = QLinearGradient(bar.left(), 0, bar.right(), 0)
        g.setColorAt(0, QColor(0, 200, 255))
        g.setColorAt(.5, QColor(60, 235, 170))
        g.setColorAt(.8, ORANGE)
        g.setColorAt(1, RED)
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(bar.left(), bar.top(), max(8, bar.width() * t), bar.height()), 6, 6)
        p.fillPath(fill, g)
        draw_text(p, f"{int(round(self.temp))} °C", 232, 369, 19, WHITE, bold=True, w=100)
