"""Bottom-right control centre: directional pad, vehicle buttons and LCD."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QRadialGradient

from .common import (CYAN, GREEN, ORANGE, RED, WHITE, DesignWidget, alpha, draw_text, glass_panel,
                     stroke_glow)
from .icons import icon_at
from .lcd_display import LcdDisplay

PAD_C = QPointF(130, 122)
PAD_R_OUT, PAD_R_IN, OK_R = 98.0, 40.0, 36.0
CARDS = {"ign_on": QRectF(256, 16, 122, 104), "ign_off": QRectF(398, 16, 132, 104),
         "belt": QRectF(256, 129, 122, 104), "sos": QRectF(398, 129, 132, 104)}
LCD_RECT = QRectF(49, 275, 462, 90)


class ControlCenter(DesignWidget):
    DW, DH = 552.0, 391.0
    dpad = Signal(str)               # up / down / left / right / ok
    ignitionOn = Signal()
    ignitionOff = Signal()
    beltToggled = Signal()
    sosPressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lcd = LcdDisplay(self)
        self.ignition = True
        self.belt = True
        self.sos = False
        self.hover: str | None = None
        self.down: str | None = None
        self.flash: str | None = None
        self._flash_t = 0.0

    def set_status(self, ignition: bool, belt: bool, sos: bool) -> None:
        if (ignition, belt, sos) != (self.ignition, self.belt, self.sos):
            self.ignition, self.belt, self.sos = ignition, belt, sos
            self.update()

    def press_key(self, name: str) -> None:
        """Visual feedback for keyboard-driven pad presses."""
        self.flash, self._flash_t = name, time.time()
        self.update()

    def tick(self) -> None:
        if self.sos or (self.flash and time.time() - self._flash_t < 0.25) or self.flash:
            if self.flash and time.time() - self._flash_t >= 0.2:
                self.flash = None
            self.update()

    def resizeEvent(self, e) -> None:
        sx, sy = self.width() / self.DW, self.height() / self.DH
        self.lcd.setGeometry(round(LCD_RECT.x() * sx), round(LCD_RECT.y() * sy),
                             round(LCD_RECT.width() * sx), round(LCD_RECT.height() * sy))

    # ---------------------------------------------------------- hit-testing
    def _hit(self, q: QPointF) -> str | None:
        dx, dy = q.x() - PAD_C.x(), q.y() - PAD_C.y()
        r = math.hypot(dx, dy)
        if r <= OK_R:
            return "ok"
        if PAD_R_IN <= r <= PAD_R_OUT:
            ang = math.degrees(math.atan2(dy, dx))
            if -135 <= ang < -45:
                return "up"
            if -45 <= ang < 45:
                return "right"
            if 45 <= ang < 135:
                return "down"
            return "left"
        for k, rect in CARDS.items():
            if rect.contains(q):
                return k
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
            {"up": lambda: self.dpad.emit("up"), "down": lambda: self.dpad.emit("down"),
             "left": lambda: self.dpad.emit("left"), "right": lambda: self.dpad.emit("right"),
             "ok": lambda: self.dpad.emit("ok"), "ign_on": self.ignitionOn.emit,
             "ign_off": self.ignitionOff.emit, "belt": self.beltToggled.emit,
             "sos": self.sosPressed.emit}[k]()
        self.down = None
        self.update()

    def leaveEvent(self, e) -> None:
        self.hover = None
        self.update()

    # ---------------------------------------------------------- paint
    def _state(self, key):
        return self.down == key or self.flash == key, self.hover == key

    def paintEvent(self, e) -> None:
        p = self.begin()
        glass_panel(p, QRectF(1.5, 1.5, self.DW - 3, self.DH - 3), 24, CYAN, 170, border_a=190)
        self._pad(p)
        self._cards(p)
        glass_panel(p, QRectF(14, 241, 524, 138), 14, CYAN, 120, border_a=110)
        draw_text(p, "LCD Display (16 × 2)", 40, 258, 16.5, WHITE, "l", w=260)

    def _pad(self, p) -> None:
        c = PAD_C
        # backing disc
        disc = QRadialGradient(c, PAD_R_OUT + 12)
        disc.setColorAt(0.8, QColor(10, 26, 46, 240))
        disc.setColorAt(1, QColor(0, 80, 140, 40))
        p.setPen(QPen(QColor(0, 214, 255, 70), 1.2))
        p.setBrush(disc)
        p.drawEllipse(c, PAD_R_OUT + 8, PAD_R_OUT + 8)
        for name, mid in (("up", -90), ("right", 0), ("down", 90), ("left", 180)):
            pressed, hover = self._state(name)
            a0, a1 = mid - 43, mid + 43
            path = QPainterPath()
            ro, ri = PAD_R_OUT, PAD_R_IN
            path.arcMoveTo(QRectF(c.x() - ro, c.y() - ro, 2 * ro, 2 * ro), -a0)
            path.arcTo(QRectF(c.x() - ro, c.y() - ro, 2 * ro, 2 * ro), -a0, -(a1 - a0))
            path.arcTo(QRectF(c.x() - ri, c.y() - ri, 2 * ri, 2 * ri), -a1, (a1 - a0))
            path.closeSubpath()
            g = QRadialGradient(c, ro)
            if pressed:
                g.setColorAt(0.4, QColor(0, 120, 170))
                g.setColorAt(1, QColor(0, 70, 110))
            else:
                g.setColorAt(0.4, QColor(50, 76, 98) if hover else QColor(34, 52, 72))
                g.setColorAt(1, QColor(14, 24, 38))
            p.fillPath(path, g)
            stroke_glow(p, path, alpha(CYAN, 255 if (hover or pressed) else 140), 1.3 if hover else 1.0,
                        layers=((5, 20),) if (hover or pressed) else ())
            mx = c.x() + 69 * math.cos(math.radians(mid))
            my = c.y() + 69 * math.sin(math.radians(mid))
            icon_at(p, name, mx, my, 22, WHITE if not pressed else QColor(255, 255, 255), 8)
        pressed, hover = self._state("ok")
        og = QRadialGradient(QPointF(c.x() - 8, c.y() - 10), OK_R * 1.5)
        og.setColorAt(0, QColor(0, 120, 170) if pressed else (QColor(56, 82, 106) if hover else QColor(40, 60, 82)))
        og.setColorAt(1, QColor(8, 16, 28))
        p.setBrush(og)
        p.setPen(QPen(alpha(CYAN, 255 if hover or pressed else 200), 1.8))
        p.drawEllipse(c, OK_R, OK_R)
        draw_text(p, "OK", c.x(), c.y() + 1, 25, WHITE, bold=True, w=70)

    def _round_btn(self, p, rect, key, col, active, icon=None, text=None, label="", sub="", sub_col=None):
        pressed, hover = self._state(key)
        glass_panel(p, rect, 12, col if (active or hover) else CYAN, 140,
                    border_a=200 if hover else 90)
        cx = rect.center().x()
        cy = rect.top() + (44 if key in ("ign_on", "ign_off") else 34)
        glow = QRadialGradient(QPointF(cx, cy), 46)
        glow.setColorAt(0.45, alpha(col, 110 if active else 30))
        glow.setColorAt(1, alpha(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), 46, 46)
        r = 31 if icon == "power" else 27
        fill = QRadialGradient(QPointF(cx - 5, cy - 8), r * 1.6)
        fill.setColorAt(0, alpha(col, 120 if active else 45) if not pressed else alpha(col, 190))
        fill.setColorAt(1, QColor(6, 16, 28))
        p.setBrush(fill)
        p.setPen(QPen(alpha(col, 255 if active else 150), 2.6 if active else 1.8))
        rr = r - (2 if pressed else 0)
        p.drawEllipse(QPointF(cx, cy), rr, rr)
        if icon:
            icon_at(p, icon, cx, cy, 34 if icon == "power" else 40, alpha(col, 255 if active else 190), 6)
        if text:
            draw_text(p, text, cx, cy + 1, 20, alpha(col.lighter(130), 255), bold=True, w=60)
        return cx, rect.top()

    def paint_label(self, p, cx, y, label, sub, sub_col):
        draw_text(p, label, cx, y, 14.5, WHITE, w=130)
        if sub:
            draw_text(p, sub, cx, y + 18, 13.5, sub_col, w=130)

    def _cards(self, p) -> None:
        blink = 0.5 + 0.5 * math.sin(time.time() * 7)
        r = CARDS["ign_on"]
        self._round_btn(p, r, "ign_on", GREEN, self.ignition, icon="power")
        self.paint_label(p, r.center().x(), r.top() + 88, "Ignition ON", "", WHITE)
        r = CARDS["ign_off"]
        self._round_btn(p, r, "ign_off", RED, not self.ignition, icon="power")
        self.paint_label(p, r.center().x(), r.top() + 88, "Ignition OFF", "", WHITE)
        r = CARDS["belt"]
        bc = CYAN if self.belt else ORANGE
        self._round_btn(p, r, "belt", GREEN if self.belt else ORANGE, self.belt, icon="seatbelt")
        self.paint_label(p, r.center().x(), r.top() + 78, "Seat Belt",
                         "Fastened" if self.belt else "Unfastened", CYAN if self.belt else ORANGE)
        r = CARDS["sos"]
        col = RED if not self.sos else QColor(255, 90, 70)
        self._round_btn(p, r, "sos", col, self.sos or True, text="SOS")
        if self.sos:
            p.setPen(QPen(QColor(255, 60, 60, int(60 + 190 * blink)), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 12, 12)
        self.paint_label(p, r.center().x(), r.top() + 78, "SOS",
                         "Cancel Alert" if self.sos else "Send Alert", QColor(255, 90, 80))
