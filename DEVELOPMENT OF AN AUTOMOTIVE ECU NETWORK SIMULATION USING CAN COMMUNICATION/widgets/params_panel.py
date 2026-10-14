"""Vehicle Parameters (Simulation) panel with six custom glowing sliders."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QRadialGradient

from .common import (CYAN, GREEN, MUTED, ORANGE, WHITE, DesignWidget, alpha, clamp, draw_text,
                     glass_panel)
from .icons import icon_at

#        key                  label               icon      kind     max   decimals
ROWS = [("speed_kmh", "Speed (km/h)", "car", "cyan", 220, 0),
        ("rpm", "RPM", "engine", "cyan", 8000, 0),
        ("engine_temperature", "Temperature (°C)", "thermo", "orange", 150, 0),
        ("voltage", "Voltage (V)", "battery", "cyan", 16, 1),
        ("fuel_level", "Fuel Level (%)", "fuel", "green", 100, 0),
        ("pollution", "Pollution (%)", "leaf", "green", 100, 0)]
ROW_Y = [66, 115, 164, 213, 263, 315]
TRACK_X0, TRACK_X1 = 188.0, 402.0
KINDS = {"cyan": (QColor(0, 150, 255), QColor(40, 225, 255)),
         "orange": (QColor(255, 140, 30), QColor(255, 190, 90)),
         "green": (QColor(30, 205, 90), QColor(120, 250, 130))}


class ParamsPanel(DesignWidget):
    DW, DH = 544.0, 391.0
    valueEdited = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = {r[0]: 0.0 for r in ROWS}
        self.disabled: set[str] = set()
        self.drag: int | None = None
        self.hover: int | None = None

    def set_values(self, values: dict, disabled: set) -> None:
        if values != self.values or disabled != self.disabled:
            self.values = dict(values)
            self.disabled = set(disabled)
            self.update()

    # ---------------------------------------------------------- input
    def _row_at(self, q: QPointF) -> int | None:
        if not (TRACK_X0 - 16 <= q.x() <= TRACK_X1 + 16):
            return None
        for i, y in enumerate(ROW_Y):
            if abs(q.y() - y) < 20 and ROWS[i][0] not in self.disabled:
                return i
        return None

    def _apply(self, i: int, x: float) -> None:
        key, _, _, _, vmax, dec = ROWS[i]
        f = clamp((x - TRACK_X0) / (TRACK_X1 - TRACK_X0), 0, 1)
        v = round(f * vmax, dec) if dec else float(round(f * vmax))
        self.values[key] = v
        self.valueEdited.emit(key, v)
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            q = self.dpos(e)
            i = self._row_at(q)
            if i is not None:
                self.drag = i
                self._apply(i, q.x())

    def mouseMoveEvent(self, e) -> None:
        q = self.dpos(e)
        if self.drag is not None:
            self._apply(self.drag, q.x())
            return
        h = self._row_at(q)
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h is not None else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        self.drag = None

    def leaveEvent(self, e) -> None:
        self.hover = None
        self.update()

    # ---------------------------------------------------------- paint
    def paintEvent(self, e) -> None:
        p = self.begin()
        glass_panel(p, QRectF(1.5, 1.5, self.DW - 3, self.DH - 3), 24, CYAN, 175, border_a=190)
        draw_text(p, "Vehicle  Parameters (Simulation)", 17, 24, 19.5, WHITE, "l", True, 0.4, w=420)
        p.setPen(QColor(120, 180, 230, 70))
        p.drawLine(17, 41, 527, 41)
        for i, (key, label, icon, kind, vmax, dec) in enumerate(ROWS):
            y = ROW_Y[i]
            dis = key in self.disabled
            p.setOpacity(0.38 if dis else 1.0)
            active = self.drag == i or self.hover == i
            icon_at(p, icon, 31, y, 27, GREEN if icon == "leaf" else WHITE, 5.5)
            draw_text(p, label, 62, y + 1, 14.5, WHITE, "l", w=130)
            v = self.values.get(key, 0.0)
            f = clamp(v / vmax, 0, 1)
            c0, c1 = KINDS[kind]
            track = QRectF(TRACK_X0, y - 6, TRACK_X1 - TRACK_X0, 12)
            path = QPainterPath()
            path.addRoundedRect(track, 6, 6)
            p.fillPath(path, QColor(8, 26, 48, 235))
            p.setPen(QColor(110, 170, 230, 70))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            hx = TRACK_X0 + f * (TRACK_X1 - TRACK_X0)
            fillrect = QRectF(TRACK_X0, y - 6, max(12.0, hx - TRACK_X0 + 4), 12)
            g = QLinearGradient(fillrect.left(), 0, fillrect.right(), 0)
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            fp = QPainterPath()
            fp.addRoundedRect(fillrect, 6, 6)
            p.fillPath(fp, alpha(c1, 40))                       # glow under fill
            p.fillPath(fp, g)
            # handle
            r = 11.5 if active else 10.5
            glow = QRadialGradient(QPointF(hx, y), 26)
            glow.setColorAt(0, alpha(c1, 150 if active else 100))
            glow.setColorAt(1, alpha(c1, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(hx, y), 26, 26)
            hg = QRadialGradient(QPointF(hx - 3, y - 3), r * 1.3)
            hg.setColorAt(0, QColor(255, 255, 255))
            hg.setColorAt(.6, QColor(205, 235, 255))
            hg.setColorAt(1, alpha(c1, 255))
            p.setBrush(hg)
            p.setPen(alpha(c1, 230))
            p.drawEllipse(QPointF(hx, y), r, r)
            p.setBrush(c0)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(hx, y), 3.2, 3.2)
            txt = f"{v:.1f}" if dec else f"{int(round(v))}"
            draw_text(p, txt, 452, y + 1, 20, WHITE, "c", True, w=80)
            draw_text(p, str(vmax), 513, y + 1, 14.5, MUTED, "c", w=60)
            p.setOpacity(1.0)
