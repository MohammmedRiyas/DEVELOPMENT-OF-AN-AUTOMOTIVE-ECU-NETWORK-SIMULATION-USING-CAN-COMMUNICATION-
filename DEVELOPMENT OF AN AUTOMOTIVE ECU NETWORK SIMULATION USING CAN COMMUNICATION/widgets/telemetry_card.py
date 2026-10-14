"""Reusable telemetry card."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFontMetricsF

from .common import (GREEN, MUTED, ORANGE, RED, WHITE, CYAN, DesignWidget, alpha, draw_text,
                     glass_panel, font)
from .icons import icon_at

LEVEL_BORDER = {0: CYAN, 1: ORANGE, 2: RED}


class TelemetryCard(DesignWidget):
    def __init__(self, w, h, title, icon, icon_color, value_color, title_color=WHITE,
                 text_x=112.0, icon_x=58.0, parent=None):
        super().__init__(parent)
        self.DW, self.DH = float(w), float(h)
        self.title, self.icon = title, icon
        self.icon_color, self.value_color, self.title_color = icon_color, value_color, title_color
        self.text_x, self.icon_x = text_x, icon_x
        self.value_text = ""
        self.badge = ""
        self.badge_color = GREEN
        self.level = 0

    def set_content(self, value: str, level: int = 0, badge: str = "", badge_color=GREEN) -> None:
        if (value, level, badge) != (self.value_text, self.level, self.badge):
            self.value_text, self.level, self.badge, self.badge_color = value, level, badge, badge_color
            self.update()

    def tick(self) -> None:
        if self.level == 2:
            self.update()

    def paintEvent(self, e) -> None:
        p = self.begin()
        pulse = 0.5 + 0.5 * math.sin(time.time() * 6) if self.level == 2 else 1.0
        border = LEVEL_BORDER[self.level]
        glass_panel(p, QRectF(1.5, 1.5, self.DW - 3, self.DH - 3), 16, border,
                    190, border_a=120 + 120 * pulse if self.level else 200)
        # soft inner glow near the bottom edge
        icon_col = RED if self.level == 2 else self.icon_color
        icon_at(p, self.icon, self.icon_x, self.DH / 2, 44, icon_col, 6)
        draw_text(p, self.title, self.text_x, 26, 16.5, self.title_color, "l", w=200)
        val_col = RED if self.level == 2 else self.value_color
        px = 30.0
        avail = self.DW - self.text_x - 16 - (46 if self.badge else 0)
        while px > 16 and QFontMetricsF(font(px, True, 1.0)).horizontalAdvance(self.value_text) > avail:
            px -= 1
        draw_text(p, self.value_text, self.text_x + 2, 58, px, val_col, "l", True, 1.0, w=300)
        if self.badge:
            draw_text(p, self.badge, self.DW - 24, 56, 13, self.badge_color, "r", True, w=90)
