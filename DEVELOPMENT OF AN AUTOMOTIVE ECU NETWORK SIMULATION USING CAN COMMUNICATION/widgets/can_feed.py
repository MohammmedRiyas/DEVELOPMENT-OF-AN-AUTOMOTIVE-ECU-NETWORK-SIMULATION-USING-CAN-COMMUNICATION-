"""Live CAN message panel shown INSIDE the main dashboard (over the lower part of the centre scene).

It answers three questions at a glance, without opening the separate CAN Bus Monitor window:

    * CAN ID   - which identifier is on the bus (0x100, 0x101, 0x102, 0x700, 0x701)
    * Node     - which board sent it and which board received it (TX node -> RX node)
    * Data     - the raw bytes of the last frame, and how fast the frame is repeating

Data source: the very same {"node","t":"f","dir","id","n","d","c"} frame reports that the ESP32 boards
already send for the CAN Bus Monitor (see CanLink.frameReceived). Nothing new is needed in the firmware.

One row per CAN id. The dot at the start of a row tells the truth about the bus:
    green  = the RX node really received this frame within the last second (it travelled over the wires)
    orange = only the TX node reports sending it, nothing came out at the RX node
    grey   = nothing seen recently
"""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPen

from .can_monitor import NAMES
from .common import (CYAN, GREEN, MONO, MUTED, ORANGE, RED, WHITE, DesignWidget, alpha, draw_text,
                     font, glass_panel)

# ---- the node identities of this bus -------------------------------------------------------------
# Each board announces itself with a heartbeat frame, so the heartbeat id doubles as the NODE ID.
NODE_IDS = {"TX": 0x700, "RX": 0x701}

# (CAN id, sender node, receiver node) - one display row per id, in this order
ROWS = (
    (0x100, "TX", "RX"),
    (0x101, "TX", "RX"),
    (0x102, "TX", "RX"),
    (0x700, "TX", "RX"),
    (0x701, "RX", "TX"),
)

LIVE_S = 1.0          # a frame older than this counts as "stopped"
RATE_WINDOW_S = 2.0   # frames/second is measured over this sliding window
REPAINT_S = 0.2       # the panel is repainted at 5 Hz (frames arrive faster than anyone can read)

# ---- design-space layout (panel is 682 x 160 design units) ---------------------------------------
Y_TITLE = 15.0        # title row centre
Y_CAPTION = 35.0      # column captions centre
Y_ROW0 = 55.0         # first data row centre
ROW_H = 18.0          # distance between data rows (5 rows -> last one at y = 127)
Y_FOOT = 150.0        # footer (node ids) centre
X_DOT, X_ID, X_NAME, X_NODE, X_DATA, X_RATE = 24.0, 38.0, 104.0, 236.0, 330.0, 666.0


class CanFeed(DesignWidget):
    DW, DH = 682.0, 160.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # key (node, dir, id) -> {"data": bytes, "count": int, "seen": float, "hist": deque}
        self.rows: dict[tuple, dict] = {}
        self.status = ("SEARCH", 1)          # same text / level as the header CAN chip
        self._last_paint = 0.0
        # the panel is a read-only overlay: let mouse clicks fall through to the scene underneath
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    # ------------------------------------------------------------------ input
    def set_status(self, text: str, level: int) -> None:
        """Link state (CAN OK / NO LINK ...) - shown at the right of the title row."""
        if (text, level) != self.status:
            self.status = (text, level)
            self.update()

    def feed(self, msg: dict) -> None:
        """msg = one frame report line from a board: {"node","t":"f","dir","id","n","d","c"}."""
        try:
            key = (str(msg["node"]), str(msg["dir"]), int(msg["id"]))
            data = bytes.fromhex(msg.get("d", ""))
            count = int(msg["c"])
        except (KeyError, ValueError, TypeError):
            return                                   # malformed line: ignore, never crash the UI
        now = time.monotonic()
        r = self.rows.setdefault(key, {"hist": deque()})
        r.update(data=data, count=count, seen=now)
        hist = r["hist"]
        hist.append((now, count))
        while hist and now - hist[0][0] > RATE_WINDOW_S:
            hist.popleft()

    def tick(self) -> None:
        """Called from the dashboard animation timer; repaints a few times per second."""
        now = time.monotonic()
        if self.isVisible() and now - self._last_paint >= REPAINT_S:
            self._last_paint = now
            self.update()

    # ------------------------------------------------------------------ helpers
    def _side(self, node: str, direction: str, cid: int):
        """Row record for one node/direction/id if it was seen recently, else None."""
        r = self.rows.get((node, direction, cid))
        if r and time.monotonic() - r["seen"] < LIVE_S:
            return r
        return None

    @staticmethod
    def _rate(r: dict) -> float:
        h = r["hist"]
        if len(h) > 1 and h[-1][0] > h[0][0]:
            return (h[-1][1] - h[0][1]) / (h[-1][0] - h[0][0])
        return 0.0

    # ------------------------------------------------------------------ paint
    def paintEvent(self, e) -> None:
        p = self.begin()
        glass_panel(p, QRectF(1.5, 1.5, self.DW - 3, self.DH - 3), 14, CYAN, 150, border_a=150)

        # ---- title row ----
        draw_text(p, "CAN BUS MESSAGES", 16, Y_TITLE, 14, WHITE, "l", True, 1.2, w=240)
        text, level = self.status
        col = {0: GREEN, 1: ORANGE, 2: RED}.get(level, MUTED)
        draw_text(p, text, self.DW - 16, Y_TITLE, 13.5, col, "r", True, w=120)
        tw = QFontMetricsF(font(13.5, True)).horizontalAdvance(text)       # real text width -> dot sits left of it
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(self.DW - 16 - tw - 9, Y_TITLE), 4, 4)

        # ---- column captions ----
        cap = alpha(MUTED, 230)
        draw_text(p, "CAN ID", X_ID, Y_CAPTION, 11, cap, "l", True, 0.8, w=60)
        draw_text(p, "MESSAGE", X_NAME, Y_CAPTION, 11, cap, "l", True, 0.8, w=110)
        draw_text(p, "NODE", X_NODE, Y_CAPTION, 11, cap, "l", True, 0.8, w=80)
        draw_text(p, "DATA (hex)", X_DATA, Y_CAPTION, 11, cap, "l", True, 0.8, w=200)
        draw_text(p, "RATE", X_RATE, Y_CAPTION, 11, cap, "r", True, 0.8, w=60)
        p.setPen(QPen(alpha(CYAN, 70), 1))
        p.drawLine(QPointF(12, Y_CAPTION + 11), QPointF(self.DW - 12, Y_CAPTION + 11))

        # ---- one row per CAN id ----
        for i, (cid, src, dst) in enumerate(ROWS):
            y = Y_ROW0 + i * ROW_H
            rx = self._side(dst, "rx", cid)           # seen at the receiving node  = proof it crossed the bus
            tx = self._side(src, "tx", cid)           # seen leaving the sending node
            shown = rx or tx                          # prefer the received copy
            if rx:
                dot, txt_col = GREEN, WHITE
            elif tx:
                dot, txt_col = ORANGE, WHITE
            else:
                dot, txt_col = QColor(110, 128, 148), alpha(MUTED, 190)
            p.setPen(Qt.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QPointF(X_DOT, y), 3.8, 3.8)
            draw_text(p, f"0x{cid:03X}", X_ID, y, 14, CYAN if shown else alpha(CYAN, 110), "l", True,
                      families=MONO, w=64)
            draw_text(p, NAMES.get(cid, "-"), X_NAME, y, 13, txt_col, "l", w=128)
            draw_text(p, f"{src} \u2192 {dst}", X_NODE, y, 13, txt_col, "l", True, w=86)
            if shown:
                draw_text(p, " ".join(f"{b:02X}" for b in shown["data"]), X_DATA, y, 13, txt_col, "l",
                          families=MONO, w=250)
                draw_text(p, f"{self._rate(shown):.0f}/s", X_RATE, y, 13, txt_col, "r", w=60)
            else:
                draw_text(p, "no frame", X_DATA, y, 13, txt_col, "l", w=250)
                draw_text(p, "-", X_RATE, y, 13, txt_col, "r", w=60)

        # ---- footer: the node identities ----
        p.setPen(QPen(alpha(CYAN, 55), 1))
        p.drawLine(QPointF(12, Y_FOOT - 12), QPointF(self.DW - 12, Y_FOOT - 12))
        draw_text(p, "NODE ID", 16, Y_FOOT, 11.5, cap, "l", True, 0.8, w=70)
        draw_text(p, f"TX node = 0x{NODE_IDS['TX']:03X}", 92, Y_FOOT, 13, WHITE, "l", True,
                  families=MONO, w=190)
        draw_text(p, f"RX node = 0x{NODE_IDS['RX']:03X}", 290, Y_FOOT, 13, WHITE, "l", True,
                  families=MONO, w=190)
        draw_text(p, "500 kbit/s", self.DW - 16, Y_FOOT, 12, MUTED, "r", w=120)
