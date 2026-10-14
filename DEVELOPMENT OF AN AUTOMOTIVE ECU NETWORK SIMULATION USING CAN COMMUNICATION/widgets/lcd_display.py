"""Simulated 16 x 2 character LCD."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen

from .common import MONO, DesignWidget, draw_text

COLS, ROWS = 16, 2


class LcdDisplay(DesignWidget):
    DW, DH = 462.0, 90.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lines = ["AUTONET SYSTEM", "ALL NORMAL"]

    def set_lines(self, l1: str, l2: str) -> None:
        lines = [l1[:COLS].ljust(COLS), l2[:COLS].ljust(COLS)]
        if lines != self.lines:
            self.lines = lines
            self.update()

    def paintEvent(self, e) -> None:
        p = self.begin()
        # dark metallic bezel
        bez = QPainterPath()
        bez.addRoundedRect(QRectF(0.5, 0.5, self.DW - 1, self.DH - 1), 10, 10)
        g = QLinearGradient(0, 0, 0, self.DH)
        g.setColorAt(0, QColor(40, 54, 70))
        g.setColorAt(1, QColor(8, 14, 24))
        p.fillPath(bez, g)
        p.setPen(QPen(QColor(110, 170, 220, 120), 1))
        p.drawPath(bez)
        face = QRectF(9, 8, self.DW - 18, self.DH - 16)
        fp = QPainterPath()
        fp.addRoundedRect(face, 5, 5)
        fg = QLinearGradient(0, face.top(), 0, face.bottom())
        fg.setColorAt(0, QColor(176, 252, 96))
        fg.setColorAt(1, QColor(128, 232, 70))
        p.fillPath(fp, fg)
        cw, ch = face.width() / COLS, face.height() / ROWS
        p.setClipPath(fp)
        for r in range(ROWS):
            for c in range(COLS):
                cell = QRectF(face.left() + c * cw + 2.2, face.top() + r * ch + 4, cw - 4.4, ch - 8)
                p.fillRect(cell, QColor(110, 200, 60, 70))        # unlit LCD cell ghost
        for r in range(ROWS):
            for c, ch_ in enumerate(self.lines[r]):
                if ch_ != " ":
                    draw_text(p, ch_, face.left() + (c + .5) * cw, face.top() + (r + .5) * ch + 1,
                              ch * 0.74, QColor(22, 58, 20), bold=True, families=MONO, w=cw * 2)
        # pixel grid
        p.setPen(QPen(QColor(60, 130, 40, 40), 0.7))
        x = face.left()
        while x < face.right():
            p.drawLine(x, face.top(), x, face.bottom())
            x += 2.6
        y = face.top()
        while y < face.bottom():
            p.drawLine(face.left(), y, face.right(), y)
            y += 2.6
        sheen = QLinearGradient(0, face.top(), 0, face.bottom())
        sheen.setColorAt(0, QColor(255, 255, 255, 40))
        sheen.setColorAt(.5, QColor(255, 255, 255, 0))
        p.fillRect(face, sheen)
