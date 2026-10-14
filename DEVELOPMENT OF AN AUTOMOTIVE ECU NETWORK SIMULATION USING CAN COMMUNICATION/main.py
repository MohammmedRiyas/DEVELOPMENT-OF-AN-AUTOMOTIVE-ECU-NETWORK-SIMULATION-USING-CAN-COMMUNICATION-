"""AUTONET - Intelligent Vehicle System dashboard (PySide6)."""
from __future__ import annotations

import argparse
import sys
import time

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from widgets.common import asset
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from can_link import CanLink, LcdRelay
from vehicle_state import DisplayState, VehicleState
from widgets.adas_view import AdasView
from widgets.common import CYAN, GREEN, ORANGE, RED, WHITE
from widgets.can_feed import CanFeed
from widgets.can_monitor import CanMonitor
from widgets.control_center import ControlCenter
from widgets.gauge import SpeedGauge, TachGauge
from widgets.header_bar import HeaderBar
from widgets.params_panel import ROWS, ParamsPanel
from widgets.telemetry_card import TelemetryCard
from widgets.vehicle_scene import VehicleScene

DESIGN_W, DESIGN_H = 1536.0, 1024.0
LAYOUT = {                     # design-space rectangles (x, y, w, h) measured from the reference
    "header": (0, 0, 1536, 96), "speed": (10, 98, 400, 400), "scene": (413, 96, 710, 400),
    "tach": (1126, 98, 400, 400), "c_volt": (27, 497, 292, 86), "c_temp": (336, 497, 269, 86),
    "c_fuel": (622, 497, 261, 86), "c_poll": (899, 497, 258, 86), "c_stat": (1172, 497, 337, 86),
    "params": (25, 597, 544, 391), "adas": (583, 597, 362, 391), "control": (959, 597, 552, 391),
    "canfeed": (427, 332, 682, 160),          # live CAN id / node panel, overlaid on the lower part of the scene
}
PAGES = 5


class Dashboard(QWidget):
    """state = what the user sets (sliders, buttons, simulation).
    view  = what is displayed. Without CAN it is the same object as state; with CAN it is a
            DisplayState that only ever holds values received back over the CAN bus."""

    def __init__(self, state: VehicleState, can: CanLink | None = None) -> None:
        super().__init__()
        self.state = state
        self.can = can
        self.view = DisplayState() if can else state
        self.setAutoFillBackground(False)
        self.header = HeaderBar(self)
        self.speed = SpeedGauge(self)
        self.scene = VehicleScene(self)
        self.canfeed = CanFeed(self)            # created after the scene so it is drawn on top of it
        self.canfeed.setVisible(False)          # hidden until the user clicks the CAN chip in the header
        self.tach = TachGauge(self)
        self.c_volt = TelemetryCard(292, 86, "Voltage", "battery", GREEN, QColor(40, 200, 255),
                                    title_color=GREEN, text_x=122)
        self.c_temp = TelemetryCard(269, 86, "Engine Temp", "thermo", ORANGE, ORANGE)
        self.c_fuel = TelemetryCard(261, 86, "Fuel Level", "fuel", CYAN, QColor(40, 200, 255))
        self.c_poll = TelemetryCard(258, 86, "Pollution", "leaf", GREEN, GREEN)
        self.c_stat = TelemetryCard(337, 86, "System Status", "shield", GREEN, GREEN, text_x=120, icon_x=73)
        self.cards = [self.c_volt, self.c_temp, self.c_fuel, self.c_poll, self.c_stat]
        for c in self.cards:
            c.setParent(self)
        self.params = ParamsPanel(self)
        self.adas = AdasView(self)
        self.control = ControlCenter(self)
        self.widgets = {"header": self.header, "speed": self.speed, "scene": self.scene, "canfeed": self.canfeed,
                        "tach": self.tach,
                        "c_volt": self.c_volt, "c_temp": self.c_temp, "c_fuel": self.c_fuel,
                        "c_poll": self.c_poll, "c_stat": self.c_stat, "params": self.params,
                        "adas": self.adas, "control": self.control}
        self.lcd_page = 0
        self.lcd_msg = ("", 0.0)
        self._ambient_src = QPixmap(asset("scene_bg.png"))
        self._ambient = QPixmap()
        self._wire()
        self.refresh(initial=True)

    # ---------------------------------------------------------- wiring
    def _wire(self) -> None:
        s = self.state
        s.changed.connect(self.refresh)
        if self.can:
            s.changed.connect(lambda: self.can.push_state(s))
            self.can.push_state(s)
            self.can.dataReceived.connect(self.view.apply)
            self.can.statusChanged.connect(self.on_can_status)
            self.can.frameReceived.connect(self.canfeed.feed)           # CAN id / node messages -> panel
            self.can.statusChanged.connect(lambda: self.canfeed.set_status(*self.can.status()))
            self.canfeed.set_status(*self.can.status())
            self.view.changed.connect(self.refresh)
        s.message.connect(lambda m: setattr(self, "lcd_msg", (m, time.time() + 2.0)))
        self.params.valueEdited.connect(s.set_value)
        self.adas.toggled.connect(s.toggle)
        c = self.control
        c.ignitionOn.connect(lambda: s.set_ignition(True))
        c.ignitionOff.connect(lambda: s.set_ignition(False))
        c.beltToggled.connect(lambda: s.toggle("seat_belt_fastened"))
        c.sosPressed.connect(s.toggle_sos)
        c.dpad.connect(self.dpad)

    def dpad(self, name: str) -> None:
        s = self.state
        if name == "up":
            s.shift(+1)
        elif name == "down":
            s.shift(-1)
        elif name == "left":
            self.lcd_page = (self.lcd_page - 1) % PAGES
        elif name == "right":
            self.lcd_page = (self.lcd_page + 1) % PAGES
        elif name == "ok":
            self.lcd_page = 0
            s.acknowledge()
        self.update_lcd()

    def toggle_canfeed(self) -> None:
        """Click on the header CAN chip: show / hide the live CAN stats panel (CAN id, node, data, rate)."""
        if self.can:
            self.canfeed.setVisible(not self.canfeed.isVisible())

    def on_can_status(self) -> None:
        self.view.set_link(self.can.ok())          # emits changed -> refresh

    def can_chip(self) -> tuple[str, int]:
        return self.can.status() if self.can else ("SIM", -1)

    # ---------------------------------------------------------- state -> UI
    def refresh(self, initial: bool = False) -> None:
        s = self.state          # inputs: sliders, buttons
        v = self.view           # outputs: everything that is displayed
        self.speed.set_target(v.speed_kmh)
        self.speed.set_level(v.level("speed"))
        self.speed.set_gear(v.gear)
        self.speed.set_fuel(v.fuel_level)
        self.tach.set_rpm(v.rpm)
        self.tach.set_level(v.level("rpm"))
        self.tach.set_temp(v.engine_temperature)
        self.c_volt.set_content(f"{v.voltage:.1f} V", v.level("voltage"))
        self.c_temp.set_content(f"{v.engine_temperature:.0f} °C", v.level("temp"))
        self.c_fuel.set_content(f"{v.fuel_level:.0f} %", v.level("fuel"))
        pl = v.level("pollution")
        self.c_poll.set_content(f"{v.pollution:.0f} %", pl, "OK" if pl == 0 else ("HIGH" if pl == 1 else "BAD"),
                                WHITE if pl == 0 else (ORANGE if pl == 1 else RED))
        text, kind = v.system_status()
        col = {"ok": GREEN, "warn": ORANGE, "crit": RED, "off": QColor(150, 176, 204)}[kind]
        self.c_stat.value_color = col
        self.c_stat.icon_color = col
        self.c_stat.set_content(text, {"ok": 0, "off": 0, "warn": 1, "crit": 2}[kind])
        self.header.set_status(v.ignition_on, v.seat_belt_fastened, v.sos_active, v.level("belt") > 0)
        self.control.set_status(v.ignition_on, v.seat_belt_fastened, v.sos_active)
        disabled = set() if s.ignition_on else {"speed_kmh", "rpm"}
        if s.gear == "P":
            disabled.add("speed_kmh")
        self.params.set_values({r[0]: getattr(s, r[0]) for r in ROWS}, disabled)
        al = v.alerts()
        self.scene.set_state(v.speed_kmh, v.ignition_on, v.sos_active, (al[0][1], al[0][2]) if al else None)
        self.adas.set_state({k: getattr(v, k) for k in ("lane_assist_enabled", "sensors_enabled",
                            "eco_mode_enabled", "automatic_mode_enabled")}, v.speed_kmh, v.ignition_on)
        self.header.set_can(*self.can_chip())
        self.update_lcd()

    def update_lcd(self) -> None:
        s = self.view
        msg, until = self.lcd_msg
        if s.sos_active:
            lines = ("!! SOS ACTIVE !!", "HELP REQUESTED") if int(time.time() * 2) % 2 == 0 else ("!! SOS ACTIVE !!", "PRESS OK: CANCEL")
        elif msg and time.time() < until:
            lines = ("AUTONET SYSTEM", msg)
        elif self.lcd_page == 1:
            lines = (f"SPD {s.speed_kmh:5.0f} KM/H", f"RPM {s.rpm:5.0f}  G:{s.gear}")
        elif self.lcd_page == 2:
            lines = (f"TEMP {s.engine_temperature:5.0f} C", f"BATT {s.voltage:5.1f} V")
        elif self.lcd_page == 3:
            lines = (f"FUEL {s.fuel_level:5.0f} %", f"POLL {s.pollution:5.0f} %")
        elif self.lcd_page == 4:
            if self.can:
                d = self.can.detail()
                txt = self.can.status()[0]
                lines = (txt if txt.startswith("CAN") else f"CAN {txt}", f"RX{d['rx'] % 100000:>5} E{d['tec']}/{d['rec']}")
            else:
                lines = ("CAN", "SIMULATION")
        else:
            al = s.alerts()
            if al:
                lines = ("WARNING" if al[0][1] == 1 else "CRITICAL", al[0][2])
            elif not s.ignition_on:
                lines = ("AUTONET SYSTEM", "IGNITION OFF")
            else:
                lines = ("AUTONET SYSTEM", "ALL NORMAL")
        self.control.lcd.set_lines(*lines)

    # ---------------------------------------------------------- animation tick
    def tick(self, dt: float) -> None:
        self.state.step(dt)
        self.header.refresh_clock()
        self.header.tick()
        self.scene.advance(dt)
        self.adas.advance(dt)
        self.control.tick()
        self.canfeed.tick()
        for c in self.cards:
            c.tick()
        if self.view.sos_active or self.lcd_msg[0]:
            self.update_lcd()

    # ---------------------------------------------------------- layout / background
    def _scale(self):
        s = min(self.width() / DESIGN_W, self.height() / DESIGN_H)
        return s, (self.width() - DESIGN_W * s) / 2, (self.height() - DESIGN_H * s) / 2

    def _build_ambient(self) -> None:
        """Blurred, darkened copy of the scene photo that glows behind the gauges."""
        if self._ambient_src.isNull():
            return
        s, ox, oy = self._scale()
        w, h = max(1, round(DESIGN_W * s)), max(1, round(400 * s))
        small = self._ambient_src.scaled(28, 16, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        big = small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = QPixmap(w, h)
        out.fill(Qt.transparent)
        q = QPainter(out)
        q.setOpacity(0.55)
        q.drawPixmap(0, 0, big)
        q.setOpacity(1.0)
        q.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        for a, b, r in (((0, 0), (0, h * .25), (0, 0, w, h * .25)), ((0, h), (0, h * .7), (0, h * .7, w, h * .3))):
            g = QLinearGradient(a[0], a[1], b[0], b[1])
            g.setColorAt(0, QColor(0, 0, 0, 255))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            q.fillRect(QRectF(*r), g)
        q.end()
        self._ambient = out

    def resizeEvent(self, e) -> None:
        self._build_ambient()
        s, ox, oy = self._scale()
        for k, (x, y, w, h) in LAYOUT.items():
            self.widgets[k].setGeometry(round(ox + x * s), round(oy + y * s), round(w * s), round(h * s))

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(2, 6, 14))
        s, ox, oy = self._scale()
        p.translate(ox, oy)
        p.scale(s, s)
        bg = QLinearGradient(0, 0, 0, DESIGN_H)
        bg.setColorAt(0, QColor(5, 14, 30))
        bg.setColorAt(1, QColor(2, 7, 16))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, DESIGN_W, DESIGN_H), 30, 30)
        if not self._ambient.isNull():
            p.save()
            p.resetTransform()
            p.drawPixmap(round(ox), round(oy + 96 * s), self._ambient)
            p.restore()
        for cx, cy in ((210, 290), (1330, 290)):
            g = QRadialGradient(cx, cy, 380)
            g.setColorAt(0, QColor(0, 90, 170, 55))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(g)
            p.drawRect(QRectF(0, 0, DESIGN_W, DESIGN_H))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 214, 255, 120), 1.6))
        p.drawRoundedRect(QRectF(3, 3, DESIGN_W - 6, DESIGN_H - 6), 28, 28)


class MainWindow(QMainWindow):
    KEYS = {Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right",
            Qt.Key_Return: "ok", Qt.Key_Enter: "ok"}

    def __init__(self, can: CanLink | None = None) -> None:
        super().__init__()
        self.setWindowTitle("AUTONET - Intelligent Vehicle System")
        self.state = VehicleState()
        self.can = can
        self.dash = Dashboard(self.state, can)
        self.setCentralWidget(self.dash)
        self.setMinimumSize(1000, 680)
        self.dash.header.settingsClicked.connect(self.toggle_fullscreen)
        self.monitor = CanMonitor()
        if can:
            can.frameReceived.connect(self.monitor.feed)
            can.statusChanged.connect(lambda: self.monitor.set_status(*can.status()))
            self.monitor.set_status(*can.status())
            self.dash.header.canClicked.connect(self.dash.toggle_canfeed)   # CAN chip -> stats panel (F2 = monitor window)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)                      # ~30 FPS

    def _tick(self) -> None:
        dt = self.clock.restart() / 1000.0
        self.dash.tick(dt)

    def toggle_monitor(self) -> None:
        if self.monitor.isVisible():
            self.monitor.hide()
        else:
            self.monitor.show()
            self.monitor.raise_()

    def closeEvent(self, e) -> None:
        self.monitor.close()
        super().closeEvent(e)

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def keyPressEvent(self, e) -> None:
        k = e.key()
        if k in self.KEYS:
            self.dash.control.press_key(self.KEYS[k])
            self.dash.dpad(self.KEYS[k])
        elif k == Qt.Key_F2:
            self.toggle_monitor()
        elif k == Qt.Key_F11:
            self.toggle_fullscreen()
        elif k == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
        else:
            super().keyPressEvent(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="", help="window size WxH, e.g. 1366x768")
    ap.add_argument("--screenshot", default="", help="save a PNG and exit")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--sim", action="store_true", help="no ESP32 / CAN: gauges follow the sliders directly")
    ap.add_argument("--tx-port", default="", help="serial port of the TX ESP32 (default: auto-detect)")
    ap.add_argument("--rx-port", default="", help="serial port of the RX ESP32 (default: auto-detect)")
    ap.add_argument("--lcd-port", default="", help="COM port to send the RX board's 16x2 LCD text to (LCD simulator)")
    ap.add_argument("--lcd-baud", type=int, default=9600)
    ap.add_argument("--lcd-plain", action="store_true", help="do not send a form-feed (clear) before each update")
    ap.add_argument("--monitor", action="store_true", help="open the CAN Bus Monitor window at start")
    ap.add_argument("--list-ports", action="store_true", help="print the serial ports found and exit")
    args = ap.parse_args()
    if args.list_ports:
        from can_link import list_ports
        list_ports()
        return 0
    app = QApplication(sys.argv)
    can = None if args.sim else CanLink(args.tx_port, args.rx_port)
    win = MainWindow(can)
    if can:
        app.aboutToQuit.connect(can.shutdown)
        if args.lcd_port:
            relay = LcdRelay(args.lcd_port, args.lcd_baud, not args.lcd_plain, app)
            can.lcdReceived.connect(relay.send)
            app.aboutToQuit.connect(relay.close)
    if args.size:
        w, h = (int(v) for v in args.size.lower().split("x"))
    else:
        avail = app.primaryScreen().availableGeometry()
        f = min(1.0, avail.width() * 0.96 / DESIGN_W, avail.height() * 0.94 / DESIGN_H)
        w, h = int(DESIGN_W * f), int(DESIGN_H * f)
    win.resize(w, h)
    win.showFullScreen() if args.fullscreen else win.show()
    if args.monitor and can:
        win.toggle_monitor()
    if args.screenshot:
        def shot():
            win.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(1200, shot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
