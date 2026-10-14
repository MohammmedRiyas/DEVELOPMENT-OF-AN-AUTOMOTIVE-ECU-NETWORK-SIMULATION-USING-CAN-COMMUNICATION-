"""CAN link to the two ESP32 nodes (USB serial).

PC dashboard  --USB-->  ESP32 "TX" + MCP2515  ==CAN bus==  MCP2515 + ESP32 "RX"  --USB-->  PC dashboard

* Parameters (sliders, buttons) are sent to the TX node, which puts them on the CAN bus.
* The RX node decodes/validates the CAN frames and returns them; the dashboard shows THOSE values.
* Both nodes report their CAN controller state, so the link status is real, not assumed.

The ports can be given explicitly (--tx-port / --rx-port) or are found automatically: every
ESP32 announces its role ("TX" / "RX") in its status lines.
"""
from __future__ import annotations

import json
import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal
try:
    from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
except ImportError:
    raise SystemExit("QtSerialPort is missing in this Python. Run:  pip install PySide6-Addons\n"
                     "(or use the interpreter that has the full PySide6 installed)")

from vehicle_state import GEARS, clamp

BAUD = 115200
KNOWN_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}   # CP210x, CH340, FTDI, Espressif USB
SEND_MS = 50                                      # PC -> TX update rate (20 Hz max)
KEEPALIVE_MS = 250                                # resend even if nothing changed
NODE_STALE_S = 1.5                                # node status older than this = node not answering
DATA_STALE_S = 0.8                                # no data line from RX for this long = lost
PROBE_S = 4.0                                     # give an unknown port this long to announce itself
STARTUP_S = 4.0                                   # "connecting" grace period

# status levels used by the UI
OK, WARN, ERR, OFF = 0, 1, 2, -1


def encode(s) -> str:
    """VehicleState -> one serial line for the TX node."""
    flags = (int(s.ignition_on) | int(s.seat_belt_fastened) << 1 | int(s.sos_active) << 2 |
             int(s.lane_assist_enabled) << 3 | int(s.sensors_enabled) << 4 |
             int(s.eco_mode_enabled) << 5 | int(s.automatic_mode_enabled) << 6)
    v = (round(clamp(s.speed_kmh, 0, 220) * 10), round(clamp(s.rpm, 0, 8000)), GEARS.index(s.gear),
         int(clamp(s.drive_gear, 1, 6)), round(clamp(s.engine_temperature, 0, 150) * 10),
         round(clamp(s.voltage, 0, 16) * 100), round(clamp(s.fuel_level, 0, 100) * 2),
         round(clamp(s.pollution, 0, 100)), flags)
    return "S,%d,%d,%d,%d,%d,%d,%d,%d,%d\n" % v


def decode(d: dict) -> dict:
    """RX node data line -> physical values."""
    fl = int(d["fl"])
    return {"speed_kmh": d["s"] / 10.0, "rpm": float(d["r"]), "gear": GEARS[int(d["g"]) & 3],
            "drive_gear": int(d["dg"]), "engine_temperature": d["tp"] / 10.0, "voltage": d["v"] / 100.0,
            "fuel_level": d["f"] / 2.0, "pollution": float(d["p"]),
            "ignition_on": bool(fl & 1), "seat_belt_fastened": bool(fl & 2), "sos_active": bool(fl & 4),
            "lane_assist_enabled": bool(fl & 8), "sensors_enabled": bool(fl & 16),
            "eco_mode_enabled": bool(fl & 32), "automatic_mode_enabled": bool(fl & 64)}


class _Conn(QObject):
    """One serial port that delivers complete text lines."""
    lineReceived = Signal(object, str)
    failed = Signal(object)

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.role: str | None = None
        self.keep = False
        self.opened = time.monotonic()
        self.buf = bytearray()
        self.sp = QSerialPort(name, self)
        self.sp.setBaudRate(BAUD)
        self.sp.readyRead.connect(self._read)
        self.sp.errorOccurred.connect(self._error)

    def open(self) -> bool:
        if not self.sp.open(QSerialPort.ReadWrite):
            return False
        # keep DTR/RTS released so the ESP32 is not held in reset / download mode
        self.sp.setDataTerminalReady(False)
        self.sp.setRequestToSend(False)
        self.opened = time.monotonic()
        return True

    def close(self) -> None:
        self.sp.blockSignals(True)
        if self.sp.isOpen():
            self.sp.close()

    def write(self, text: str) -> None:
        if self.sp.isOpen():
            self.sp.write(text.encode("ascii"))

    def _read(self) -> None:
        self.buf += bytes(self.sp.readAll())
        if len(self.buf) > 8192:                      # no newline for ages: junk, drop it
            self.buf.clear()
        while b"\n" in self.buf:
            raw, _, rest = self.buf.partition(b"\n")
            self.buf = bytearray(rest)
            line = raw.decode("ascii", "ignore").strip()
            if line:
                self.lineReceived.emit(self, line)

    def _error(self, err) -> None:
        if err in (QSerialPort.ResourceError, QSerialPort.DeviceNotFoundError,
                   QSerialPort.PermissionError, QSerialPort.NotOpenError):
            self.failed.emit(self)


class CanLink(QObject):
    dataReceived = Signal(dict)          # decoded values that came back through the CAN bus
    frameReceived = Signal(dict)         # one CAN frame report from either node (for the bus monitor)
    lcdReceived = Signal(str, str)       # the 16x2 text the RX board built for its LCD
    statusChanged = Signal()

    def __init__(self, tx_port: str = "", rx_port: str = "", parent=None) -> None:
        super().__init__(parent)
        self.explicit = {"TX": tx_port, "RX": rx_port}
        self.nodes: dict[str, _Conn] = {}              # role -> connection
        self.probe: dict[str, _Conn] = {}              # port name -> connection waiting for a role
        self.skip: dict[str, float] = {}               # port name -> ignore until
        self.stat: dict[str, dict] = {"TX": {}, "RX": {}}
        self.stat_t = {"TX": 0.0, "RX": 0.0}
        self.data_t = 0.0
        self.rx_frames = 0
        self.t0 = time.monotonic()
        self._pending = ""
        self._last_sent = ""
        self._last_sent_t = 0.0
        self._last_status = None
        self._tx = QTimer(self)
        self._tx.timeout.connect(self._push)
        self._tx.start(SEND_MS)
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._scan)
        self._scan_timer.start(1500)
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check)
        self._watch.start(150)
        self._scan()

    # ------------------------------------------------------------- ports
    def _scan(self) -> None:
        now = time.monotonic()
        for name, c in list(self.probe.items()):       # unknown device that never spoke
            if now - c.opened > PROBE_S and not c.keep:
                self._drop(c, skip=15.0)
        for name in {n for n in self.explicit.values() if n}:
            if name not in self.probe and all(c.name != name for c in self.nodes.values()):
                c = _Conn(name, self)
                c.keep = True                          # given by the user: never give up on it
                if c.open():
                    self._attach(c)
                    self.probe[name] = c               # its role is learned from what it announces
                else:
                    print(f"[can] cannot open {name}: {c.sp.errorString()} (close Serial Monitor / other programs)",
                          file=sys.stderr, flush=True)
                    c.deleteLater()
        if not (self.explicit["TX"] and self.explicit["RX"]):
            taken = {c.name for c in self.nodes.values()} | set(self.probe) | set(self.explicit.values())
            infos = QSerialPortInfo.availablePorts()
            known = [i for i in infos if i.hasVendorIdentifier() and i.vendorIdentifier() in KNOWN_VIDS]
            # unknown USB-serial chip: try every port that has a USB vendor id (skips Bluetooth etc.)
            cands = known or [i for i in infos if i.hasVendorIdentifier()]
            for info in cands:
                name = info.portName()
                if name in taken or self.skip.get(name, 0) > now:
                    continue
                c = _Conn(name, self)
                if c.open():
                    self._attach(c)
                    self.probe[name] = c
                else:
                    print(f"[can] cannot open {name}: {c.sp.errorString()} (close Serial Monitor / other programs)",
                          file=sys.stderr, flush=True)
                    c.deleteLater()
                    self.skip[name] = now + 5.0

    def _attach(self, c: _Conn) -> None:
        c.lineReceived.connect(self._on_line)
        c.failed.connect(self._drop)
        if c.role:
            self.nodes[c.role] = c
        self.statusChanged.emit()

    def _drop(self, c: _Conn, skip: float = 3.0) -> None:
        for role, n in list(self.nodes.items()):
            if n is c:
                del self.nodes[role]
                self.stat[role] = {}
                self.stat_t[role] = 0.0
        self.probe.pop(c.name, None)
        self.skip[c.name] = time.monotonic() + skip
        c.close()
        c.deleteLater()
        self.statusChanged.emit()

    # ------------------------------------------------------------- receive
    def _on_line(self, c: _Conn, line: str) -> None:
        if not line.startswith("{"):
            return                                      # boot-loader noise etc.
        try:
            d = json.loads(line)
        except ValueError:
            return
        role = d.get("node")
        if role not in ("TX", "RX"):
            return
        if c.role is None:                               # probing: this port just announced itself
            other = self.nodes.get(role)
            if other is not None and other is not c:
                self._drop(c, skip=30.0)                 # two boards flashed with the same role
                return
            c.role = role
            self.probe.pop(c.name, None)
            self.nodes[role] = c
        elif c.role != role:
            return
        now = time.monotonic()
        if d.get("t") == "s":
            self.stat[role] = d
            self.stat_t[role] = now
        elif d.get("t") == "f":
            self.frameReceived.emit(d)
        elif d.get("t") == "lcd" and role == "RX":
            self.lcdReceived.emit(str(d.get("l1", ""))[:16], str(d.get("l2", ""))[:16])
        elif d.get("t") == "d" and role == "RX":
            try:
                vals = decode(d)
            except (KeyError, ValueError, TypeError, IndexError):
                return
            self.data_t = now
            self.rx_frames += 1
            self.dataReceived.emit(vals)

    # ------------------------------------------------------------- transmit
    def push_state(self, state) -> None:
        self._pending = encode(state)

    def _push(self) -> None:
        tx = self.nodes.get("TX")
        if tx is None or not self._pending:
            return
        now = time.monotonic()
        if self._pending != self._last_sent or now - self._last_sent_t > KEEPALIVE_MS / 1000:
            tx.write(self._pending)
            self._last_sent = self._pending
            self._last_sent_t = now

    # ------------------------------------------------------------- status
    def status(self) -> tuple[str, int]:
        """Short text for the header chip + level (OK / WARN / ERR)."""
        now = time.monotonic()
        tx, rx = self.nodes.get("TX"), self.nodes.get("RX")
        silent = [c for c in self.probe.values() if c.keep]
        if silent and (tx is None or rx is None):      # a port is open but its board has not answered yet
            return ("WAIT", WARN) if now - min(c.opened for c in silent) < STARTUP_S else ("NO RESP", ERR)
        if tx is None and rx is None:
            return ("SEARCH", WARN) if now - self.t0 < STARTUP_S else ("NO NODES", ERR)
        if tx is None:
            return "NO TX", ERR
        if rx is None:
            return "NO RX", ERR
        st = {r: (self.stat[r] if now - self.stat_t[r] < NODE_STALE_S else None) for r in ("TX", "RX")}
        if st["TX"] is None or st["RX"] is None:
            return ("WAIT", WARN) if now - max(tx.opened, rx.opened) < STARTUP_S else ("NO RESP", ERR)
        states = (st["TX"].get("can"), st["RX"].get("can"))
        if "INIT_FAIL" in states:
            return "MCP FAIL", ERR
        if "BUSOFF" in states:
            return "BUS OFF", ERR
        if not (st["TX"].get("peer") and st["RX"].get("link")):
            return "NO LINK", ERR
        if "ERR" in states:
            return "BUS ERR", ERR
        if not (st["RX"].get("fresh") and now - self.data_t < DATA_STALE_S):
            return "NO DATA", WARN
        return "CAN OK", OK

    def ok(self) -> bool:
        return self.status()[1] == OK

    def detail(self) -> dict:
        """Counters for the LCD page."""
        tx, rx = self.stat["TX"], self.stat["RX"]
        return {"rx": int(rx.get("rx", 0)), "bad": int(rx.get("bad", 0)) + int(tx.get("bad", 0)),
                "tec": max(int(tx.get("tec", 0)), int(rx.get("tec", 0))),
                "rec": max(int(tx.get("rec", 0)), int(rx.get("rec", 0))),
                "fail": int(tx.get("fail", 0))}

    def _check(self) -> None:
        cur = self.status()
        if cur != self._last_status:
            self._last_status = cur
            self.statusChanged.emit()

    def shutdown(self) -> None:
        for c in list(self.nodes.values()) + list(self.probe.values()):
            c.close()


def list_ports() -> None:
    for i in QSerialPortInfo.availablePorts():
        vid = f"{i.vendorIdentifier():04X}" if i.hasVendorIdentifier() else "----"
        print(f"{i.portName():10} VID {vid}  {i.description()}")


class LcdRelay(QObject):
    """Forwards the RX board's 16x2 LCD text to a COM port (e.g. one end of a virtual COM pair that an
    LCD simulator listens on). Format per update:  [form-feed]  line1 CR LF  line2 CR LF"""

    def __init__(self, port: str, baud: int = 9600, clear: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.clear = clear
        self.sp = QSerialPort(port, self)
        self.sp.setBaudRate(baud)
        self.ok = self.sp.open(QSerialPort.WriteOnly)
        if not self.ok:
            print(f"[lcd] cannot open {port}: {self.sp.errorString()}", file=sys.stderr, flush=True)

    def send(self, l1: str, l2: str) -> None:
        if self.ok:
            self.sp.write((("\f" if self.clear else "") + f"{l1:<16}\r\n{l2:<16}\r\n").encode("ascii", "replace"))

    def close(self) -> None:
        if self.sp.isOpen():
            self.sp.close()
