"""Vector icons drawn with QPainter in a 100x100 unit box (resolution independent)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .common import alpha


def _poly(p, pts):
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    p.drawPath(path)


def _power(p, c):
    p.drawArc(QRectF(20, 22, 60, 60), 120 * 16, 300 * 16)
    p.drawLine(50, 10, 50, 50)


def _seatbelt(p, c):
    p.drawEllipse(QPointF(48, 18), 9, 9)
    path = QPainterPath(QPointF(26, 92))
    path.lineTo(26, 52)
    path.quadTo(26, 36, 44, 36)
    path.lineTo(54, 36)
    path.quadTo(68, 38, 70, 52)
    path.lineTo(70, 64)
    p.drawPath(path)
    p.drawLine(18, 92, 82, 92)
    pen = QPen(p.pen())
    pen.setWidthF(9)
    p.setPen(pen)
    p.drawLine(34, 38, 68, 76)


def _sos(p, c):
    p.drawEllipse(QPointF(50, 50), 40, 40)
    p.drawLine(50, 30, 50, 70)
    p.drawLine(30, 50, 70, 50)


def _calendar(p, c):
    p.drawRoundedRect(QRectF(14, 22, 72, 64), 9, 9)
    p.drawLine(14, 42, 86, 42)
    p.drawLine(33, 12, 33, 30)
    p.drawLine(67, 12, 67, 30)
    p.setBrush(c)
    for x in (32, 50, 68):
        for y in (56, 72):
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)


def _gear(p, c):
    p.save()
    p.translate(50, 50)
    for _ in range(8):
        p.drawLine(0, -30, 0, -43)
        p.rotate(45)
    p.restore()
    p.drawEllipse(QPointF(50, 50), 28, 28)
    p.drawEllipse(QPointF(50, 50), 11, 11)


def _battery(p, c):
    p.drawRoundedRect(QRectF(8, 28, 76, 50), 7, 7)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(84, 44, 8, 18), 3, 3)
    p.setBrush(Qt.NoBrush)
    p.drawLine(24, 53, 42, 53)
    p.drawLine(33, 44, 33, 62)
    p.drawLine(58, 53, 72, 53)
    p.drawLine(26, 20, 26, 28)
    p.drawLine(66, 20, 66, 28)


def _thermo(p, c):
    p.drawRoundedRect(QRectF(41, 6, 18, 62), 9, 9)
    p.setBrush(c)
    p.drawEllipse(QPointF(50, 77), 15, 15)
    p.setBrush(Qt.NoBrush)
    pen = QPen(p.pen())
    pen.setWidthF(8)
    p.setPen(pen)
    p.drawLine(50, 34, 50, 74)
    pen.setWidthF(4.5)
    p.setPen(pen)
    for y in (16, 30, 44):
        p.drawLine(68, y, 78, y)


def _fuel(p, c):
    p.drawRoundedRect(QRectF(14, 10, 42, 78), 6, 6)
    p.drawRoundedRect(QRectF(23, 20, 24, 22), 3, 3)
    p.drawLine(8, 90, 62, 90)
    path = QPainterPath(QPointF(56, 32))
    path.lineTo(70, 32)
    path.quadTo(82, 34, 82, 48)
    path.lineTo(82, 70)
    path.quadTo(82, 78, 90, 76)
    path.lineTo(90, 44)
    path.lineTo(80, 28)
    p.drawPath(path)


def _leaf(p, c):
    path = QPainterPath(QPointF(16, 84))
    path.cubicTo(4, 34, 44, 8, 90, 10)
    path.cubicTo(92, 56, 62, 90, 16, 84)
    p.setBrush(alpha(c, 70))
    p.drawPath(path)
    p.setBrush(Qt.NoBrush)
    p.drawLine(16, 84, 64, 36)
    p.drawLine(40, 60, 40, 44)
    p.drawLine(52, 48, 66, 48)


def _shield(p, c):
    path = QPainterPath(QPointF(50, 6))
    path.lineTo(86, 20)
    path.lineTo(86, 48)
    path.cubicTo(86, 72, 68, 86, 50, 94)
    path.cubicTo(32, 86, 14, 72, 14, 48)
    path.lineTo(14, 20)
    path.closeSubpath()
    p.setBrush(alpha(c, 55))
    p.drawPath(path)
    p.setBrush(Qt.NoBrush)
    _poly(p, [(32, 50), (45, 63), (69, 36)])


def _car(p, c):
    _poly(p, [(24, 42), (33, 20), (67, 20), (76, 42)])
    p.drawRoundedRect(QRectF(10, 42, 80, 34), 11, 11)
    p.drawLine(18, 76, 18, 88)
    p.drawLine(82, 76, 82, 88)
    p.setBrush(c)
    p.drawEllipse(QPointF(28, 58), 4, 4)
    p.drawEllipse(QPointF(72, 58), 4, 4)
    p.setBrush(Qt.NoBrush)


def _engine(p, c):
    p.drawRoundedRect(QRectF(26, 34, 42, 36), 5, 5)
    _poly(p, [(34, 34), (34, 24), (60, 24), (60, 34)])
    _poly(p, [(26, 46), (14, 46), (14, 62), (26, 62)])
    _poly(p, [(68, 44), (78, 44), (78, 36), (88, 36), (88, 70), (78, 70), (78, 62), (68, 62)])
    p.drawLine(40, 50, 54, 50)
    p.drawLine(40, 58, 54, 58)


def _lane(p, c):
    p.drawLine(36, 8, 8, 92)
    p.drawLine(64, 8, 92, 92)
    for a, b in ((14, 30), (42, 58), (70, 88)):
        p.drawLine(50, a, 50, b)


def _sensors(p, c):
    path = QPainterPath(QPointF(18, 22))
    path.lineTo(18, 78)
    path.lineTo(58, 50)
    path.closeSubpath()
    p.drawPath(path)
    p.drawArc(QRectF(28, 24, 50, 52), -55 * 16, 110 * 16)
    p.drawArc(QRectF(18, 8, 74, 84), -50 * 16, 100 * 16)


def _auto(p, c):
    p.drawArc(QRectF(12, 12, 76, 76), 40 * 16, 280 * 16)
    _poly(p, [(86, 22), (80, 38), (64, 30)])
    p.save()
    p.setFont(QFont("Arial", 1, QFont.Bold))
    f = p.font()
    f.setPixelSize(40)
    f.setBold(True)
    p.setFont(f)
    p.setPen(c)
    p.drawText(QRectF(20, 22, 60, 56), Qt.AlignCenter, "A")
    p.restore()


def _warn(p, c):
    path = QPainterPath(QPointF(50, 10))
    path.lineTo(92, 86)
    path.lineTo(8, 86)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(50, 38, 50, 62)
    p.drawPoint(QPointF(50, 74))


def _chev(dx, dy):
    def f(p, c):
        pts = {(0, -1): [(18, 66), (50, 34), (82, 66)], (0, 1): [(18, 34), (50, 66), (82, 34)],
               (-1, 0): [(66, 18), (34, 50), (66, 82)], (1, 0): [(34, 18), (66, 50), (34, 82)]}[(dx, dy)]
        _poly(p, pts)
    return f


ICONS = {"power": _power, "seatbelt": _seatbelt, "sos": _sos, "calendar": _calendar, "gear": _gear,
         "battery": _battery, "thermo": _thermo, "fuel": _fuel, "leaf": _leaf, "shield": _shield,
         "car": _car, "engine": _engine, "lane": _lane, "sensors": _sensors, "auto": _auto,
         "warn": _warn, "up": _chev(0, -1), "down": _chev(0, 1), "left": _chev(-1, 0),
         "right": _chev(1, 0)}


def draw_icon(p: QPainter, name: str, rect: QRectF, color: QColor, width: float = 6.5) -> None:
    p.save()
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / 100.0, rect.height() / 100.0)
    pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    ICONS[name](p, color)
    p.restore()


def icon_at(p: QPainter, name: str, cx: float, cy: float, size: float, color: QColor,
            width: float = 6.5) -> None:
    draw_icon(p, name, QRectF(cx - size / 2, cy - size / 2, size, size), color, width)
