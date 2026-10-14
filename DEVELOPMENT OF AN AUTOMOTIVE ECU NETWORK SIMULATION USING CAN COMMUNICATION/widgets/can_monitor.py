"""CAN Bus Monitor window: every CAN id seen on the bus, per node, with raw bytes, meaning, count and rate."""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .common import MONO

NAMES = {0x100: "DRIVE", 0x101: "ENGINE", 0x102: "FLAGS", 0x700: "TX HEARTBEAT", 0x701: "RX HEARTBEAT"}
GEARS = "PRND"
FLAG_NAMES = ["IGN", "BELT", "SOS", "LANE", "SENS", "ECO", "AUTO"]
COLS = ["Node", "Dir", "CAN ID", "Name", "DLC", "Data (hex)", "Meaning", "Count", "Rate"]


def meaning(cid: int, b: bytes) -> str:
    try:
        u = lambda i: b[i] | (b[i + 1] << 8)
        if cid == 0x100 and len(b) >= 6:
            return f"{u(0) / 10:.1f} km/h   {u(2)} rpm   gear {GEARS[b[4] & 3]}   drive gear {b[5]}"
        if cid == 0x101 and len(b) >= 6:
            return f"{u(0) / 10:.1f} C   {u(2) / 100:.2f} V   fuel {b[4] / 2:.1f} %   pollution {b[5]} %"
        if cid == 0x102 and len(b) >= 1:
            on = [n for i, n in enumerate(FLAG_NAMES) if b[0] >> i & 1]
            return "ON: " + (" ".join(on) if on else "none")
        if cid in (0x700, 0x701) and len(b) >= 2:
            who = "PC link " + ("ok" if b[1] else "lost") if cid == 0x700 else "data " + ("fresh" if b[1] else "stale")
            return f"counter {b[0]}   {who}"
    except (IndexError, ValueError):
        pass
    return ""


class CanMonitor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AUTONET - CAN Bus Monitor")
        self.resize(1180, 420)
        self.rows: dict[tuple, dict] = {}
        self.setStyleSheet("""
            QWidget { background: #07101e; color: #dbe9f7; font-size: 14px; }
            QLabel#title { font-size: 20px; font-weight: 600; letter-spacing: 1px; }
            QLabel#sub { color: #8fb0cf; }
            QTableWidget { background: #0a1628; gridline-color: #17314f; border: 1px solid #1c4a73; }
            QHeaderView::section { background: #0f2540; color: #8fd8ff; padding: 6px; border: 0;
                                   border-bottom: 1px solid #1c4a73; font-weight: 600; }
        """)
        self.title = QLabel("CAN BUS MONITOR")
        self.title.setObjectName("title")
        self.chip = QLabel("")
        self.chip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.chip)
        self.sub = QLabel("500 kbit/s  |  11-bit identifiers  |  TX node sends the dashboard parameters, "
                          "RX node receives and decodes them")
        self.sub.setObjectName("sub")
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.Stretch)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.sub)
        lay.addWidget(self.table, 1)
        self._mono = QFont()
        self._mono.setFamilies(MONO)
        self._mono.setPixelSize(14)
        t = QTimer(self)
        t.timeout.connect(self._render)
        t.start(200)

    def set_status(self, text: str, level: int) -> None:
        col = {0: "#2dee78", 1: "#ff9628", 2: "#ff3e3e"}.get(level, "#8fb0cf")
        self.chip.setText(f'<span style="color:{col}">&#9679;</span>  <b style="color:{col}">{text}</b>')

    def feed(self, msg: dict) -> None:
        """msg: one {"node","t":"f","dir","id","n","d","c"} line from a board."""
        try:
            key = (msg["node"], msg["dir"], int(msg["id"]))
            data = bytes.fromhex(msg.get("d", ""))
            count = int(msg["c"])
        except (KeyError, ValueError, TypeError):
            return
        now = time.monotonic()
        r = self.rows.setdefault(key, {"hist": deque()})
        r.update(data=data, dlc=int(msg.get("n", len(data))), count=count, seen=now)
        r["hist"].append((now, count))
        while r["hist"] and now - r["hist"][0][0] > 2.0:
            r["hist"].popleft()

    def _render(self) -> None:
        if not self.isVisible():
            return
        now = time.monotonic()
        keys = sorted(self.rows, key=lambda k: (k[2], k[0]))
        self.table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            node, d, cid = k
            r = self.rows[k]
            h = r["hist"]
            rate = (h[-1][1] - h[0][1]) / (h[-1][0] - h[0][0]) if len(h) > 1 and h[-1][0] > h[0][0] else 0.0
            live = now - r["seen"] < 1.0
            if not live:
                rate = 0.0
            vals = [f"{node} node", "sent  >>" if d == "tx" else "<<  received", f"0x{cid:03X}",
                    NAMES.get(cid, "-"), str(r["dlc"]), " ".join(f"{x:02X}" for x in r["data"]),
                    meaning(cid, r["data"]), str(r["count"]), f"{rate:.0f} /s" if live else "stopped"]
            for c, v in enumerate(vals):
                it = self.table.item(i, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.table.setItem(i, c, it)
                it.setText(v)
                if c in (2, 5):
                    it.setFont(self._mono)
                it.setForeground(QColor("#5fe3ff" if d == "tx" else "#7dff9e") if c in (1, 2) else
                                 QColor("#dbe9f7" if live else "#6d7f93"))
        self.table.resizeRowsToContents()
