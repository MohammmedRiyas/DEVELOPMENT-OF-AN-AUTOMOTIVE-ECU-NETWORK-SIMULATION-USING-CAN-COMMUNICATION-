"""Top navigation bar."""
from __future__ import annotations

import math
import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPen

from .common import (CYAN, GREEN, MUTED, ORANGE, RED, WHITE, DesignWidget, alpha, draw_text,
                     glass_panel, font)
from .icons import icon_at


class HeaderBar(DesignWidget):
    DW, DH = 1536.0, 96.0
    settingsClicked = Signal()
    canClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ignition = True
        self.belt = True
        self.sos = False
        self.belt_warn = False
        self.can_text, self.can_level = "SIM", -1
        self._clock = ("", "")
        self.refresh_clock()

    def set_status(self, ignition: bool, belt: bool, sos: bool, belt_warn: bool) -> None:
        if (ignition, belt, sos, belt_warn) != (self.ignition, self.belt, self.sos, self.belt_warn):
            self.ignition, self.belt, self.sos, self.belt_warn = ignition, belt, sos, belt_warn
            self.update()

    def set_can(self, text: str, level: int) -> None:
        if (text, level) != (self.can_text, self.can_level):
            self.can_text, self.can_level = text, level
            self.update()

    def refresh_clock(self) -> None:
        now = datetime.now()
        clock = (now.strftime("%a, %d %b %Y"), now.strftime("%I:%M %p"))
        if clock != self._clock:
            self._clock = clock
            self.update()

    def tick(self) -> None:
        if self.sos or self.belt_warn or self.can_level == 2:
            self.update()

    def mousePressEvent(self, e) -> None:
        q = self.dpos(e)
        if 300 <= q.x() <= 420 and 20 <= q.y() <= 76:
            self.canClicked.emit()
            return
        if math.hypot(q.x() - 1486, q.y() - 48) < 24:
            self.settingsClicked.emit()

    def mouseMoveEvent(self, e) -> None:
        q = self.dpos(e)
        hand = math.hypot(q.x() - 1486, q.y() - 48) < 24 or (300 <= q.x() <= 420 and 20 <= q.y() <= 76)
        self.setCursor(Qt.PointingHandCursor if hand else Qt.ArrowCursor)

    def paintEvent(self, e) -> None:
        p = self.begin()
        blink = 0.5 + 0.5 * math.sin(time.time() * 7)
        # logo
        glass_panel(p, QRectF(10, 14, 412, 70), 18, CYAN, 120, border_a=90)
        draw_text(p, "AUTONET", 54, 36, 37, WHITE, "l", True, 5.0, w=300)
        draw_text(p, "Intelligent Vehicle System", 53, 66, 17, QColor(205, 222, 240), "l", spacing=0.6, w=300)
        # CAN link chip (right end of the logo panel)
        cc = {0: GREEN, 1: ORANGE, 2: RED}.get(self.can_level, MUTED)
        if self.can_level == 2:
            cc = alpha(cc, 150 + 105 * blink)
        p.setPen(QPen(QColor(120, 180, 230, 70), 1))
        p.drawLine(300, 26, 300, 72)
        p.setPen(Qt.NoPen)
        p.setBrush(cc)
        p.drawEllipse(QPointF(316, 36), 4.5, 4.5)
        draw_text(p, "CAN", 328, 36, 14.5, MUTED, "l", True, 1.0, w=70)
        draw_text(p, self.can_text, 311, 59, 16, cc, "l", True, w=104)
        # ignition
        g = GREEN if self.ignition else RED
        glass_panel(p, QRectF(438, 16, 207, 66), 12, g, 150, top=(10, 70, 40) if self.ignition else (70, 20, 24),
                    bottom=(4, 34, 22) if self.ignition else (30, 8, 12))
        p.setPen(Qt.NoPen)
        rg = QRadialGradient(QPointF(471, 44), 22)
        rg.setColorAt(0, alpha(g, 255))
        rg.setColorAt(1, alpha(g.darker(160), 255))
        p.setBrush(rg)
        p.drawEllipse(QPointF(471, 49), 19, 19)
        icon_at(p, "power", 471, 49, 26, QColor(255, 255, 255), 6)
        draw_text(p, "Ignition ON" if self.ignition else "Ignition OFF", 512, 39, 17, WHITE, "l", True, w=140)
        draw_text(p, "Engine Running" if self.ignition else "Engine Stopped", 512, 61, 14.5,
                  QColor(205, 222, 240), "l", w=140)
        # seat belt
        warn = self.belt_warn
        col = CYAN if self.belt else ORANGE
        glass_panel(p, QRectF(682, 16, 190, 66), 12, col, 150, border_a=150 + (90 * blink if warn else 0))
        icon_at(p, "seatbelt", 724, 49, 40, col, 5.5)
        draw_text(p, "Seat Belt", 765, 40, 17, WHITE, "l", True, w=100)
        draw_text(p, "Fastened" if self.belt else "Unfastened", 765, 61, 14.5, col, "l", w=100)
        # sos
        sc = RED if not self.sos else QColor(255, 90, 70)
        glass_panel(p, QRectF(895, 16, 204, 66), 12, RED, 200 if not self.sos else int(150 + 90 * blink),
                    top=(90, 22, 28) if not self.sos else (170, 20, 24), bottom=(40, 8, 12),
                    border_a=200)
        p.setPen(QPen(sc, 2.4))
        p.setBrush(Qt.NoBrush)
        icon_at(p, "sos", 930, 49, 40, sc, 6)
        draw_text(p, "SOS", 974, 40, 17, QColor(255, 120, 90), "l", True, w=100)
        draw_text(p, "ACTIVE" if self.sos else "Standby", 974, 61, 14.5, WHITE, "l", w=100)
        # date / time / settings
        glass_panel(p, QRectF(1116, 14, 410, 70), 18, CYAN, 140, border_a=120)
        icon_at(p, "calendar", 1283, 48, 28, QColor(210, 228, 245), 6)
        draw_text(p, self._clock[0], 1316, 34, 15, WHITE, "l", w=160)
        draw_text(p, self._clock[1], 1316, 60, 20, WHITE, "l", True, w=160)
        p.setPen(QPen(QColor(120, 180, 230, 70), 1))
        p.drawLine(1452, 26, 1452, 72)
        icon_at(p, "gear", 1486, 48, 30, QColor(160, 190, 215), 5.5)
