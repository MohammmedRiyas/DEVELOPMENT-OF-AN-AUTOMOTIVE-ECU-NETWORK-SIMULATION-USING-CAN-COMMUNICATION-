"""Central vehicle model. Pure simulation logic - no painting happens here."""
from __future__ import annotations

import math

from PySide6.QtCore import QObject, Signal

LIMITS = {
    "speed_kmh": (0.0, 220.0),
    "rpm": (0.0, 8000.0),
    "engine_temperature": (0.0, 150.0),
    "voltage": (0.0, 16.0),
    "fuel_level": (0.0, 100.0),
    "pollution": (0.0, 100.0),
}
FLAGS = ("seat_belt_fastened", "lane_assist_enabled", "sensors_enabled",
         "eco_mode_enabled", "automatic_mode_enabled")
GEARS = ("P", "R", "N", "D")
IDLE_RPM = 800.0
GEAR_BOUNDS = [0, 20, 40, 65, 95, 130, 1e9]        # km/h at which gear n starts
GEAR_RATIO = {1: 130.0, 2: 75.0, 3: 50.0, 4: 100 / 3, 5: 25.0, 6: 18.5}   # rpm per km/h


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class VehicleState(QObject):
    changed = Signal()
    message = Signal(str)          # short transient text for the LCD

    def __init__(self) -> None:
        super().__init__()
        self.speed_kmh = 72.0
        self.rpm = 3200.0
        self.engine_temperature = 85.0
        self.voltage = 12.4
        self.fuel_level = 75.0
        self.pollution = 12.0
        self.ignition_on = True
        self.seat_belt_fastened = True
        self.sos_active = False
        self.lane_assist_enabled = True
        self.sensors_enabled = True
        self.eco_mode_enabled = True
        self.automatic_mode_enabled = False
        self.gear = "D"
        self.drive_gear = 4
        self.can_state: str | None = None      # None = no CAN link in use, "ok" or "lost"
        self._t = 0.0

    # ------------------------------------------------------------ derived
    def _bounds(self):
        k = 0.85 if self.eco_mode_enabled else 1.0
        return [b * k for b in GEAR_BOUNDS]

    def _update_drive_gear(self) -> None:
        b = self._bounds()
        for g in range(6, 0, -1):
            if self.speed_kmh >= b[g - 1]:
                self.drive_gear = g
                return

    def _rpm_for_speed(self, speed: float) -> float:
        if not self.ignition_on:
            return 0.0
        if self.gear == "D":
            return clamp(IDLE_RPM + speed * GEAR_RATIO[self.drive_gear], IDLE_RPM, 7900)
        if self.gear == "R":
            return clamp(IDLE_RPM + speed * 100, IDLE_RPM, 3500)
        return IDLE_RPM

    def _sync_rpm(self) -> None:
        self._update_drive_gear()
        self.rpm = self._rpm_for_speed(self.speed_kmh)

    # ------------------------------------------------------------ alerts
    def level(self, key: str) -> int:
        """0 normal, 1 warning, 2 critical."""
        if key == "temp":
            t = self.engine_temperature
            return 2 if t > 120 else 1 if t > 105 else 0
        if key == "voltage":
            v = self.voltage
            return 2 if (v < 11.0 or v > 15.5) else 1 if (v < 11.8 or v > 14.8) else 0
        if key == "fuel":
            return 2 if self.fuel_level < 7 else 1 if self.fuel_level < 15 else 0
        if key == "pollution":
            return 2 if self.pollution > 75 else 1 if self.pollution > 50 else 0
        if key == "speed":
            return 2 if self.speed_kmh > 200 else 1 if self.speed_kmh > 160 else 0
        if key == "rpm":
            return 2 if self.rpm > 7500 else 1 if self.rpm > 6500 else 0
        if key == "belt":
            return 1 if (not self.seat_belt_fastened and self.ignition_on and self.speed_kmh > 10) else 0
        if key == "can":
            return 1 if self.can_state == "lost" else 0
        return 0

    def alerts(self) -> list[tuple[str, int, str]]:
        texts = {"temp": "ENGINE TEMP HIGH", "voltage": "BATTERY VOLTAGE", "fuel": "LOW FUEL",
                 "pollution": "HIGH EMISSIONS", "speed": "OVERSPEED", "rpm": "RPM RED ZONE",
                 "belt": "FASTEN SEAT BELT", "can": "CAN LINK LOST"}
        out = []
        for k, txt in texts.items():
            lv = self.level(k)
            if lv:
                out.append((k, lv, txt))
        out.sort(key=lambda a: -a[1])
        return out

    def system_status(self) -> tuple[str, str]:
        if self.sos_active:
            return "SOS ACTIVE", "crit"
        al = self.alerts()
        if any(a[1] == 2 for a in al):
            return "CRITICAL", "crit"
        if al:
            return "WARNING", "warn"
        if not self.ignition_on:
            return "IGNITION OFF", "off"
        return "ALL NORMAL", "ok"

    # ------------------------------------------------------------ commands
    def set_value(self, key: str, value) -> None:
        if key not in LIMITS:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(v):
            return
        lo, hi = LIMITS[key]
        v = clamp(v, lo, hi)
        if key in ("speed_kmh", "rpm") and not self.ignition_on:
            self.message.emit("ENGINE STOPPED")
            self.changed.emit()                  # lets sliders snap back
            return
        if key == "speed_kmh":
            if self.gear == "P":
                v = 0.0
            elif self.gear == "R":
                v = min(v, 30.0)
            self.speed_kmh = v
            self._sync_rpm()
        elif key == "rpm":
            self.rpm = max(v, IDLE_RPM)
        else:
            setattr(self, key, v)
        self.changed.emit()

    def set_ignition(self, on: bool) -> None:
        if on == self.ignition_on:
            return
        if on and self.fuel_level <= 0:
            self.message.emit("NO FUEL")
            return
        self.ignition_on = on
        if on:
            self._sync_rpm()
            self.message.emit("ENGINE START")
        else:
            self.rpm = 0.0
            self.automatic_mode_enabled = False
            self.message.emit("IGNITION OFF")
        self.changed.emit()

    def set_flag(self, key: str, value: bool) -> None:
        if key not in FLAGS:
            return
        value = bool(value)
        if key == "automatic_mode_enabled" and value:
            if not self.ignition_on:
                self.message.emit("START ENGINE FIRST")
                return
            if self.gear != "D":
                self.gear = "D"
                self._sync_rpm()
        setattr(self, key, value)
        if key == "eco_mode_enabled" and self.ignition_on:
            self._sync_rpm()
        names = {"seat_belt_fastened": "BELT", "lane_assist_enabled": "LANE ASSIST",
                 "sensors_enabled": "SENSORS", "eco_mode_enabled": "ECO MODE",
                 "automatic_mode_enabled": "AUTO MODE"}
        if key == "seat_belt_fastened":
            self.message.emit("BELT FASTENED" if value else "BELT OPEN")
        else:
            self.message.emit(f"{names[key]} {'ON' if value else 'OFF'}")
        self.changed.emit()

    def toggle(self, key: str) -> None:
        if key in FLAGS:
            self.set_flag(key, not getattr(self, key))

    def toggle_sos(self) -> None:
        self.sos_active = not self.sos_active
        self.message.emit("SOS ACTIVE" if self.sos_active else "SOS CANCELLED")
        self.changed.emit()

    def set_gear(self, g: str) -> bool:
        if g not in GEARS or g == self.gear:
            return False
        if not self.ignition_on:
            self.message.emit("ENGINE STOPPED")
            return False
        if g in ("P", "R") and self.speed_kmh > 5:
            self.message.emit("STOP TO SHIFT")
            return False
        self.gear = g
        if g != "D":
            self.automatic_mode_enabled = False
        if g == "P":
            self.speed_kmh = 0.0
        elif g == "R":
            self.speed_kmh = min(self.speed_kmh, 30.0)
        self._sync_rpm()
        self.message.emit(f"GEAR {g}")
        self.changed.emit()
        return True

    def shift(self, direction: int) -> None:
        i = GEARS.index(self.gear) + direction
        if 0 <= i < len(GEARS):
            self.set_gear(GEARS[i])

    def acknowledge(self) -> None:
        if self.sos_active:
            self.toggle_sos()

    # ------------------------------------------------------------ simulation
    def _snapshot(self):
        return (round(self.speed_kmh, 2), round(self.rpm, 1), round(self.engine_temperature, 2),
                round(self.voltage, 3), round(self.fuel_level, 3), round(self.pollution, 2),
                self.drive_gear)

    def step(self, dt: float) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self._t += dt
        t = self._t
        before = self._snapshot()
        if self.ignition_on:
            if self.automatic_mode_enabled and self.gear == "D":
                scale = 0.8 if self.eco_mode_enabled else 1.0
                target = clamp((85 + 50 * math.sin(t * 0.11) + 18 * math.sin(t * 0.37 + 1)) * scale, 25, 190)
                diff = target - self.speed_kmh
                self.speed_kmh = clamp(self.speed_kmh + clamp(diff, -22 * dt, 14 * dt), 0, 220)
                self._update_drive_gear()
                rt = self._rpm_for_speed(self.speed_kmh)
                self.rpm += (rt - self.rpm) * (1 - math.exp(-dt * 5))
                tt = 80 + 14 * self.rpm / 8000 + 3 * math.sin(t * 0.2)
                self.engine_temperature += clamp(tt - self.engine_temperature, -0.8 * dt, 0.8 * dt)
                vt = 12.4 + 0.35 * math.sin(t * 0.5)
                self.voltage += (vt - self.voltage) * (1 - math.exp(-dt * 0.8))
                pt = (5 + 25 * self.rpm / 8000 + 5 * self.speed_kmh / 220) * (0.7 if self.eco_mode_enabled else 1.0)
                self.pollution += (pt - self.pollution) * (1 - math.exp(-dt * 0.6))
                self.fuel_level = max(0.0, self.fuel_level - dt * (0.012 + 0.035 * self.rpm / 8000))
                if self.fuel_level <= 0:
                    self.message.emit("OUT OF FUEL")
                    self.set_ignition(False)
            elif self.gear == "N" and self.speed_kmh > 0:
                self.speed_kmh = max(0.0, self.speed_kmh - 3 * dt)
                self._update_drive_gear()
        else:
            self.speed_kmh = max(0.0, self.speed_kmh - 8 * dt)
            self.rpm = max(0.0, self.rpm - 4000 * dt)
            self.engine_temperature += clamp(30 - self.engine_temperature, -0.35 * dt, 0.35 * dt)
            self.pollution = max(0.0, self.pollution - 0.6 * dt)
            self._update_drive_gear()
        if self._snapshot() != before:
            self.changed.emit()


class DisplayState(VehicleState):
    """What the dashboard SHOWS when a CAN link is used: only values that came back from the RX node.

    It reuses VehicleState's alert / status logic, but it is never simulated - it just holds the last
    values received over CAN, so a dead link can never be mistaken for live data."""

    FIELDS = ("speed_kmh", "rpm", "engine_temperature", "voltage", "fuel_level", "pollution", "gear",
              "drive_gear", "ignition_on", "seat_belt_fastened", "sos_active", "lane_assist_enabled",
              "sensors_enabled", "eco_mode_enabled", "automatic_mode_enabled")

    def __init__(self) -> None:
        super().__init__()
        self.speed_kmh = self.rpm = self.engine_temperature = self.voltage = 0.0
        self.fuel_level = self.pollution = 0.0
        self.ignition_on = self.seat_belt_fastened = self.sos_active = False
        self.lane_assist_enabled = self.sensors_enabled = False
        self.eco_mode_enabled = self.automatic_mode_enabled = False
        self.gear, self.drive_gear = "P", 1
        self.can_state = "lost"

    def apply(self, values: dict) -> None:
        for k in self.FIELDS:
            if k in values:
                setattr(self, k, values[k])
        self.changed.emit()

    def set_link(self, ok: bool) -> None:
        self.can_state = "ok" if ok else "lost"
        self.changed.emit()
