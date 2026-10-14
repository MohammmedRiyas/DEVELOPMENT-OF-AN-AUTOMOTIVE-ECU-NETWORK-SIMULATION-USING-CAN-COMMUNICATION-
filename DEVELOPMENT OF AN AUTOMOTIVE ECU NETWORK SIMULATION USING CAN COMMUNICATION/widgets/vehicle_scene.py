"""Central night-driving scene (local photographic background + live overlays)."""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap

from .common import (CYAN, ORANGE, RED, WHITE, DesignWidget, alpha, asset, draw_text, glass_panel)
from .icons import icon_at

VP = QPointF(353, 204)       # road vanishing point inside the scene image


class VehicleScene(DesignWidget):
    DW, DH = 710.0, 400.0

    def __init__(self, parent=None):
        super().__init__(parent)
        path = asset("scene_bg.png")
        self._src = QPixmap(path) if os.path.exists(path) else QPixmap()
        self._scaled = QPixmap()
        self._off = (0, 0)
        self.speed = 72.0
        self.ignition = True
        self.sos = False
        self.alert = None            # (level, text)
        self._phase = 0.0

    def set_state(self, speed, ignition, sos, alert) -> None:
        self.speed, self.ignition, self.sos, self.alert = speed, ignition, sos, alert

    def advance(self, dt: float) -> None:
        self._phase = (self._phase + dt * (0.15 + self.speed / 220.0 * 0.9)) % 1.0 if self.ignition else self._phase
        self.update()

    def resizeEvent(self, e) -> None:
        if self._src.isNull():
            return
        scaled = self._src.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        out = QPixmap(self.size())
        out.fill(Qt.transparent)
        q = QPainter(out)
        q.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        w, h = self.width(), self.height()
        fw, fh = w * 0.09, h * 0.06
        for (a, b, rect) in (((0, 0), (fw, 0), (0, 0, fw, h)), ((w, 0), (w - fw, 0), (w - fw, 0, fw, h)),
                             ((0, 0), (0, fh), (0, 0, w, fh)), ((0, h), (0, h - fh), (0, h - fh, w, fh))):
            g = QLinearGradient(a[0], a[1], b[0], b[1])
            g.setColorAt(0, QColor(0, 0, 0, 255))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            q.fillRect(QRectF(*rect), g)
        q.end()
        self._scaled = out
        self._off = (0, 0)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        if self._scaled.isNull():
            p.fillRect(self.rect(), QColor(6, 14, 30))
            p.setPen(WHITE)
            p.drawText(self.rect(), Qt.AlignCenter, "assets/scene_bg.png missing")
        else:
            p.drawPixmap(self._off[0], self._off[1], self._scaled)
        p.scale(self.width() / self.DW, self.height() / self.DH)
        self._streaks(p)
        if not self.ignition:
            p.fillRect(QRectF(0, 0, self.DW, self.DH), QColor(2, 6, 14, 120))
            # top-left corner: the bottom of the scene is covered by the CAN message panel (widgets/can_feed.py)
            glass_panel(p, QRectF(16, 6, 130, 26), 8, QColor(150, 170, 190), 190)
            draw_text(p, "ENGINE OFF", 81, 19, 12, QColor(190, 205, 220), bold=True, spacing=1.2, w=124)
        blink = 0.5 + 0.5 * math.sin(time.time() * 7)
        if self.sos:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 40, 40, int(90 + 140 * blink)), 7))
            p.drawRoundedRect(QRectF(3, 3, self.DW - 6, self.DH - 6), 10, 10)
            glass_panel(p, QRectF(self.DW / 2 - 200, 34, 400, 38), 10, RED, int(150 + 80 * blink),
                        top=(120, 14, 20), bottom=(60, 6, 10))
            icon_at(p, "warn", self.DW / 2 - 176, 53, 22, WHITE, 7)
            draw_text(p, "SOS ACTIVE - EMERGENCY ALERT SENT", self.DW / 2 + 12, 53, 15, WHITE, bold=True,
                      spacing=1, w=360)
        elif self.alert:
            lv, txt = self.alert
            col = RED if lv == 2 else ORANGE
            # top-centre (the bottom of the scene is covered by the CAN message panel)
            glass_panel(p, QRectF(self.DW / 2 - 130, 36, 260, 34), 10, col,
                        int(150 + 60 * blink), top=(70, 30, 8) if lv == 1 else (90, 16, 20), bottom=(30, 12, 6))
            icon_at(p, "warn", self.DW / 2 - 106, 53, 20, col, 7)
            draw_text(p, txt, self.DW / 2 + 10, 53, 14, WHITE, bold=True, spacing=1, w=210)

    def _streaks(self, p) -> None:
        if not self.ignition or self.speed < 3:
            return
        k = min(1.0, self.speed / 160.0)
        cols = (QColor(120, 200, 255), QColor(255, 255, 255), QColor(255, 70, 70), QColor(80, 160, 255))
        for i in range(14):
            ang = math.radians(20 + i * (140 / 13) + (i % 3) * 2)
            if abs(math.degrees(ang) - 90) < 14:
                continue
            u = (self._phase + (i * 0.37) % 1.0) % 1.0
            u0, u1 = u ** 2.1, min(1.0, (u + 0.07 + 0.05 * k) ** 2.1)
            L = 520
            a = QPointF(VP.x() + math.cos(ang) * L * u0, VP.y() + math.sin(ang) * L * u0)
            b = QPointF(VP.x() + math.cos(ang) * L * u1, VP.y() + math.sin(ang) * L * u1)
            col = cols[i % 4]
            p.setPen(QPen(alpha(col, 70 * k * u + 6), 0.8 + 2.4 * u))
            p.drawLine(a, b)
