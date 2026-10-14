"""Top-down ADAS visualisation with radar pulses, lane corridor and four toggles."""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QLinearGradient, QPainterPath, QPen, QPixmap, QPolygonF,
                           QRadialGradient)

from .common import (CYAN, GREEN, MUTED, ORANGE, WHITE, DesignWidget, alpha, asset, draw_text,
                     glass_panel, stroke_glow)
from .icons import icon_at

ROAD_H = 301.0
CTRL = [("lane_assist_enabled", "Lane Assist", "lane", 46.0),
        ("sensors_enabled", "Sensors", "sensors", 138.0),
        ("eco_mode_enabled", "Eco Mode", "leaf", 230.0),
        ("automatic_mode_enabled", "Auto", "auto", 318.0)]
CTRL_Y, CTRL_R = 341.0, 27.0
CAR_C = QPointF(181, 222)


def road_x(y: float, side: float) -> float:
    """x of road edge (side 0..1 across the lanes) at screen y."""
    t = y / ROAD_H
    left = 106 + (8 - 106) * t
    right = 256 + (354 - 256) * t
    return left + (right - left) * side


def draw_car_topdown(p, cx: float, cy: float, w: float = 92, h: float = 124) -> None:
    """Vector top-down sedan (used when assets/car_topdown.png is absent)."""
    p.save()
    p.translate(cx, cy)
    sh = QRadialGradient(0, 10, w * 0.9)
    sh.setColorAt(0, QColor(0, 0, 0, 170))
    sh.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(sh)
    p.drawEllipse(QPointF(0, 10), w * 0.85, h * 0.62)
    p.setBrush(QColor(8, 10, 14))
    for sx in (-1, 1):
        for y in (-h * 0.30, h * 0.30):
            p.drawRoundedRect(QRectF(sx * w * 0.5 - 6 + sx * 2, y - 13, 12, 26), 4, 4)
    b = QPainterPath(QPointF(0, -h / 2))
    b.cubicTo(w * .32, -h / 2, w * .5, -h * .40, w * .5, -h * .2)
    b.cubicTo(w * .54, h * .1, w * .5, h * .38, w * .44, h * .48)
    b.quadTo(w * .40, h / 2, w * .30, h / 2)
    b.lineTo(-w * .30, h / 2)
    b.quadTo(-w * .40, h / 2, -w * .44, h * .48)
    b.cubicTo(-w * .5, h * .38, -w * .54, h * .1, -w * .5, -h * .2)
    b.cubicTo(-w * .5, -h * .40, -w * .32, -h / 2, 0, -h / 2)
    g = QLinearGradient(-w / 2, 0, w / 2, 0)
    g.setColorAt(0, QColor(96, 108, 124))
    g.setColorAt(.3, QColor(214, 222, 232))
    g.setColorAt(.5, QColor(246, 249, 252))
    g.setColorAt(.7, QColor(206, 214, 226))
    g.setColorAt(1, QColor(88, 98, 112))
    p.setBrush(g)
    p.setPen(QPen(QColor(60, 70, 84), 1.2))
    p.drawPath(b)
    cab = QPainterPath(QPointF(-w * .33, -h * .10))
    cab.quadTo(0, -h * .17, w * .33, -h * .10)
    cab.lineTo(w * .38, h * .22)
    cab.quadTo(0, h * .27, -w * .38, h * .22)
    cab.closeSubpath()
    cg = QLinearGradient(-w / 2, -h * .1, w / 2, h * .25)
    cg.setColorAt(0, QColor(8, 16, 30))
    cg.setColorAt(.5, QColor(44, 70, 104))
    cg.setColorAt(1, QColor(6, 12, 24))
    p.setBrush(cg)
    p.setPen(QPen(QColor(20, 30, 46), 1))
    p.drawPath(cab)
    p.setPen(QPen(QColor(255, 255, 255, 60), 1))
    p.drawLine(QPointF(-w * .2, -h * .04), QPointF(w * .1, -h * .08))
    p.setPen(QPen(QColor(150, 160, 175), 1))
    p.drawLine(QPointF(-w * .12, -h * .42), QPointF(-w * .1, -h * .2))
    p.drawLine(QPointF(w * .12, -h * .42), QPointF(w * .1, -h * .2))
    for sx in (-1, 1):
        lg = QPainterPath()
        lg.addRoundedRect(QRectF(sx * w * .30 - 10, h * .44, 20, 5), 2, 2)
        stroke_glow(p, lg, QColor(255, 50, 50), 1, layers=((5, 40),))
        p.fillPath(lg, QColor(255, 70, 70))
        p.setBrush(QColor(210, 218, 228))
        p.setPen(QPen(QColor(60, 70, 84), 1))
        p.drawRoundedRect(QRectF(sx * w * .56 - 5, -h * .14, 10, 8), 3, 3)
    p.restore()


class AdasView(DesignWidget):
    DW, DH = 362.0, 391.0
    toggled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.flags = {k: False for k, *_ in CTRL}
        self.speed = 72.0
        self.ignition = True
        self.hover: str | None = None
        self.down: str | None = None
        self.phase = 0.0
        self.pulse = 0.0
        self.t = 0.0
        self._car_pix = None
        path = asset("car_topdown.png")
        if os.path.exists(path):
            self._car_pix = QPixmap(path)

    def set_state(self, flags: dict, speed: float, ignition: bool) -> None:
        self.flags, self.speed, self.ignition = dict(flags), speed, ignition
        self.update()

    def advance(self, dt: float) -> None:
        self.t += dt
        self.phase = (self.phase + dt * (0.12 + self.speed / 220 * 1.1)) % 1.0 if self.ignition else self.phase
        self.pulse = (self.pulse + dt * 0.55) % 1.0
        self.update()

    def detect(self) -> tuple[bool, bool]:
        if not (self.flags.get("sensors_enabled") and self.ignition and self.speed > 20):
            return False, False
        return math.sin(self.t * 0.45) > 0.78, math.sin(self.t * 0.31 + 2) > 0.82

    # ---------------------------------------------------------- input
    def _hit(self, q: QPointF) -> str | None:
        for key, _, _, cx in CTRL:
            if math.hypot(q.x() - cx, q.y() - CTRL_Y) <= CTRL_R + 3:
                return key
        return None

    def mouseMoveEvent(self, e) -> None:
        h = self._hit(self.dpos(e))
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.down = self._hit(self.dpos(e))
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        k = self._hit(self.dpos(e))
        if k and k == self.down:
            self.toggled.emit(k)
        self.down = None
        self.update()

    def leaveEvent(self, e) -> None:
        self.hover = None
        self.update()

    # ---------------------------------------------------------- paint
    def paintEvent(self, e) -> None:
        p = self.begin()
        panel = glass_panel(p, QRectF(1.5, 1.5, self.DW - 3, self.DH - 3), 22, CYAN, 120, border_a=130)
        p.save()
        p.setClipPath(panel)
        self._road(p)
        self._corridor(p)
        self._radar(p)
        if self._car_pix and not self._car_pix.isNull():
            r = QRectF(CAR_C.x() - 50, CAR_C.y() - 64, 100, 128)
            p.drawPixmap(r, self._car_pix, QRectF(self._car_pix.rect()))
        else:
            draw_car_topdown(p, CAR_C.x(), CAR_C.y())
        self._side_sensors(p)
        # control strip
        strip = QLinearGradient(0, ROAD_H, 0, self.DH)
        strip.setColorAt(0, QColor(4, 12, 26, 250))
        strip.setColorAt(1, QColor(6, 18, 34, 255))
        p.fillRect(QRectF(0, ROAD_H, self.DW, self.DH - ROAD_H), strip)
        p.setPen(QPen(QColor(0, 214, 255, 90), 1))
        p.drawLine(0, ROAD_H, self.DW, ROAD_H)
        p.restore()
        self._controls(p)

    def _road(self, p) -> None:
        road = QPolygonF([QPointF(road_x(0, 0), 0), QPointF(road_x(0, 1), 0),
                          QPointF(road_x(ROAD_H, 1), ROAD_H), QPointF(road_x(ROAD_H, 0), ROAD_H)])
        bg = QLinearGradient(0, 0, 0, ROAD_H)
        bg.setColorAt(0, QColor(8, 18, 34, 255))
        bg.setColorAt(1, QColor(14, 30, 52, 255))
        p.fillRect(QRectF(0, 0, self.DW, ROAD_H), QColor(3, 9, 20))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawPolygon(road)
        sheen = QRadialGradient(QPointF(181, 230), 200)
        sheen.setColorAt(0, QColor(30, 110, 170, 60))
        sheen.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(sheen)
        p.drawPolygon(road)
        # glowing outer lane boundaries
        for side in (0, 1):
            path = QPainterPath(QPointF(road_x(0, side), 0))
            path.lineTo(road_x(ROAD_H, side), ROAD_H)
            stroke_glow(p, path, QColor(0, 214, 255), 2.2, layers=((9, 14), (4.5, 36)))
        # dashed inner lane markings that scroll with speed
        n = 7
        for side in (1 / 3, 2 / 3):
            for k in range(n):
                u0 = ((k + self.phase) / n)
                u1 = u0 + 0.5 / n
                if u1 > 1:
                    continue
                y0, y1 = u0 ** 1.5 * ROAD_H, u1 ** 1.5 * ROAD_H
                col = QColor(210, 235, 255, int(40 + 190 * u0))
                p.setPen(QPen(col, 1.2 + 3.2 * u0, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(road_x(y0, side), y0), QPointF(road_x(y1, side), y1))

    def _corridor(self, p) -> None:
        if not self.flags.get("lane_assist_enabled"):
            return
        poly = QPolygonF([QPointF(135, CAR_C.y() - 14), QPointF(227, CAR_C.y() - 14),
                          QPointF(207, 0), QPointF(155, 0)])
        g = QLinearGradient(0, CAR_C.y(), 0, 0)
        g.setColorAt(0, QColor(40, 255, 140, 120))
        g.setColorAt(1, QColor(40, 255, 140, 8))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPolygon(poly)
        for k in range(5):
            u = ((k + self.phase) / 5.0)
            y = CAR_C.y() - 20 - u * (CAR_C.y() - 20)
            half = 46 - 24 * u
            a = int(230 * (1 - u) ** 1.2)
            path = QPainterPath(QPointF(181 - half, y + 9))
            path.quadTo(181, y - 13, 181 + half, y + 9)
            stroke_glow(p, path, QColor(60, 255, 150, a), 2.6, layers=((6, 14), (3, 30)))
        for xl in (135, 227):
            p.setPen(QPen(QColor(60, 255, 150, 150), 1.4))
            p.drawLine(QPointF(xl, CAR_C.y() - 14), QPointF(155 if xl == 135 else 207, 0))

    def _radar(self, p) -> None:
        if not self.flags.get("sensors_enabled") or not self.ignition:
            return
        c = CAR_C
        for r, a in ((56, 95), (76, 70), (98, 48)):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 214, 255, a), 1.4))
            p.drawEllipse(c, r, r * 0.72)
        r = 48 + self.pulse * 62
        p.setPen(QPen(QColor(0, 230, 255, int(170 * (1 - self.pulse))), 2.2))
        p.drawEllipse(c, r, r * 0.72)

    def _side_sensors(self, p) -> None:
        left, right = self.detect()
        on = self.flags.get("sensors_enabled") and self.ignition
        for cx, hit in ((23, left), (339, right)):
            col = ORANGE if hit else (CYAN if on else QColor(110, 130, 150))
            glass_panel(p, QRectF(cx - 21, 47, 42, 42), 21, col, 190 if hit else 160)
            icon_at(p, "car", cx, 68, 24, alpha(col, 240), 6)
            bar = QRectF(cx - 2 + (-13 if cx < 100 else 13), 102, 4, 56)
            path = QPainterPath()
            path.addRoundedRect(bar, 2, 2)
            p.fillPath(path, alpha(col, 110 if on else 50))

    def _controls(self, p) -> None:
        for key, label, icon, cx in CTRL:
            on = self.flags.get(key, False)
            col = GREEN if key == "eco_mode_enabled" else CYAN
            hov, dn = self.hover == key, self.down == key
            c = QPointF(cx, CTRL_Y)
            glow = QRadialGradient(c, CTRL_R + 20)
            glow.setColorAt(0.5, alpha(col, 90 if on else (40 if hov else 0)))
            glow.setColorAt(1, alpha(col, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(c, CTRL_R + 20, CTRL_R + 20)
            fill = QRadialGradient(QPointF(cx - 6, CTRL_Y - 8), CTRL_R * 1.6)
            fill.setColorAt(0, QColor(30, 70, 100) if on or dn else QColor(22, 44, 66))
            fill.setColorAt(1, QColor(6, 16, 30))
            p.setBrush(fill)
            p.setPen(QPen(alpha(col, 255) if on else (alpha(CYAN, 190) if hov else QColor(150, 190, 220, 170)),
                          2.2 if on else 1.6))
            p.drawEllipse(c, CTRL_R - (1.5 if dn else 0), CTRL_R - (1.5 if dn else 0))
            icon_col = col if on else QColor(205, 222, 240)
            icon_at(p, icon, cx, CTRL_Y, 27, icon_col, 6)
            draw_text(p, label, cx, 375, 13.5, col if on else WHITE, w=100)
