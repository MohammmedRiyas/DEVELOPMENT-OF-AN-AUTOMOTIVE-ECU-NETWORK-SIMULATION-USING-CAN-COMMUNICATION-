# AUTONET - Intelligent Vehicle System (PySide6)

Single-window, offline automotive dashboard recreated from the reference image.
All gauges, panels, icons and controls are custom `QPainter` vector drawings; the only raster
asset is the night-driving scene photo.

## Install and run (Windows 10 / 11)

```bat
cd autonet
py -3.10 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Needs Python 3.10+ (64-bit). After `pip install` no internet connection is required.

Options: `python main.py --size 1366x768` | `--fullscreen` | `--screenshot out.png`
`--sim` (no hardware, gauges follow the sliders directly) | `--tx-port COM5 --rx-port COM6` (otherwise the two ESP32 are auto-detected)
Keys: arrow keys / Enter = D-pad, F11 = fullscreen (also the settings icon), Esc = leave fullscreen.

## Using it
* **Sliders** (Vehicle Parameters) drive the shared state; every gauge, card, LCD line and warning follows instantly.
  Speed/RPM sliders are locked while the ignition is off (or in P).
* **Speed** also recomputes RPM and the automatic gear (RPM follows speed, gear and ignition). Moving the RPM slider overrides RPM until speed changes.
* **Ignition OFF** really stops the engine: RPM -> 0, the car coasts to a stop, temperature cools, auto mode is cancelled.
* **D-pad**: Up/Down = shift gear P-R-N-D (P/R refused above 5 km/h), Left/Right = LCD pages, OK = home page / cancel SOS.
* **Auto** = simulated drive cycle (speed, RPM, temperature, voltage, fuel, emissions drift gently).
  **Eco** shifts earlier and lowers emissions. **Lane Assist / Sensors** toggle the corridor and radar.
* **Warnings** (card border + badge, scene banner, LCD): temp >105/120 C, voltage <11.8 or >14.8 V,
  fuel <15/7 %, pollution >50/75 %, speed >160/200, RPM >6500/7500, belt open while moving. SOS flashes red everywhere.

## Project layout
```
main.py              window, layout (design-space rectangles), timers, state -> UI wiring
vehicle_state.py     simulation + validation (no painting)
widgets/             common, icons, gauge, telemetry_card, header_bar, vehicle_scene,
                     adas_view, params_panel, control_center, lcd_display,
                     can_feed (live CAN id / node panel), can_monitor (separate monitor window)
assets/scene_bg.png  centre night-drive photo      (replace with any image; "cover"-scaled)
assets/car_topdown.png  OPTIONAL: if present it replaces the vector top-down car in the ADAS view
assets/reference.png the original design reference
```
Every widget paints in the 1536x1024 design space and is scaled uniformly, so proportions are kept
(letter-boxed) at 1366x768, 1920x1080 and any other size.

## Asset notes
`scene_bg.png` is cropped from the supplied reference render (the area between the two gauges).
It still contains the "AUTONET Smart Mobility / Sustainable Future" road signs. For a higher-resolution
background, drop your own image over `assets/scene_bg.png` (about 1.77:1 aspect works best).


## CAN hardware (2 x ESP32 + 2 x MCP2515)

```
sliders / buttons -> PC -USB-> ESP32 "TX" + MCP2515 ==CAN 500k== MCP2515 + ESP32 "RX" -USB-> PC -> gauges / LCD
```
* **TX board** receives the parameters from the dashboard and sends them as CAN frames (20 Hz).
* **RX board** reads the frames, validates the ranges, and returns them; **every gauge, card, LCD line and
  warning shows only what came back through the CAN bus.** The sliders are the only inputs.
* The header chip (next to the logo) and LCD page 5 (D-pad left/right) show the real link state:
  `CAN OK`, `NO LINK`, `NO DATA`, `BUS ERR`, `BUS OFF`, `MCP FAIL`, `NO TX`, `NO RX`, `NO RESP`, `NO NODES`.
  A lost link also raises a "CAN LINK LOST" warning.

### Flash the firmware
Arduino IDE, library **mcp2515** by autowp (1.2+). Open `firmware/autonet_can/autonet_can.ino`:
board 1 -> `#define NODE_ROLE ROLE_TX`, board 2 -> `ROLE_RX`. Set `CAN_CRYSTAL` to the crystal printed on
your MCP2515 module (`MCP_8MHZ` or `MCP_16MHZ`).

### Wiring (each ESP32 to its MCP2515)
| MCP2515 | ESP32 |
|---|---|
| VCC | 5V (VIN) |
| GND | GND |
| CS | GPIO5 |
| SCK | GPIO18 |
| SI (MOSI) | GPIO23 |
| SO (MISO) | GPIO19 |
| INT | not used |

Between the modules: CANH-CANH, CANL-CANL, GND-GND, and a 120 ohm terminator at both ends (the module's
120R jumper; with power off you should measure about 60 ohm between CANH and CANL).
The module's SO line is 5 V logic - a small divider or level shifter on MISO is safer for the ESP32.

### CAN frames
`0x100` speed*10, rpm, gear, drive gear | `0x101` temp*10, volt*100, fuel*2, pollution | `0x102` flag bits |
`0x700` TX heartbeat | `0x701` RX heartbeat.

### 16x2 LCD on the RX board
The RX ESP32 builds the LCD text itself (alerts first, otherwise pages rotating every 2.5 s: system / speed+rpm /
temp+battery / fuel+pollution / CAN status) and sends it to the PC as `{"node":"RX","t":"lcd","l1":..,"l2":..}`.

* **LCD simulator over a COM port (now):** create a virtual COM pair (e.g. com0com: COM20 <-> COM21), let the
  simulator listen on COM21 and start the dashboard with `py main.py --lcd-port COM20`
  (`--lcd-baud 9600`, `--lcd-plain` = no form-feed clear before each update).
  Each update is: `FF` + line1 + `CR LF` + line2 + `CR LF`.
* **Real LCD on GPIO (later):** in `autonet_can.ino` set `LCD_MODE` to `LCD_I2C` (SDA 21, SCL 22, library
  "LiquidCrystal I2C", address `LCD_I2C_ADDR`) or `LCD_PARALLEL` (HD44780 4-bit: RS 13, E 12, D4 14, D5 27, D6 26, D7 25).

### CAN Bus Monitor (for demonstrations)
Click the **CAN chip** next to the logo, press **F2**, or start with `--monitor`. The window lists every CAN id on
the bus: which node sent it, which node received it, the raw data bytes, what they mean (speed, rpm, temperature...),
frame count and frames per second. The TX rows and RX rows show the same id and bytes: that is the proof the data
travelled over the CAN wires. Move a slider and the bytes change on both sides.

### Live CAN messages inside the dashboard
**Click the CAN chip** in the header (next to the logo, e.g. `CAN OK`) to show or hide a **CAN BUS MESSAGES** panel on the lower
part of the centre scene (needs the CAN hardware, not `--sim`; the separate monitor window stays on F2 / `--monitor`)
(`widgets/can_feed.py`), so the CAN id and node id are visible without opening the monitor window:

| Column | Meaning |
|---|---|
| CAN ID | identifier on the bus: `0x100` DRIVE, `0x101` ENGINE, `0x102` FLAGS, `0x700` TX HEARTBEAT, `0x701` RX HEARTBEAT |
| NODE | sender -> receiver, e.g. `TX -> RX` |
| DATA | raw bytes of the last frame (hex) and how many times per second it repeats |
| dot | green = the RX node really received it, orange = only the TX node reports sending it, grey = nothing seen |

The footer lists the **node ids**: each board announces itself with a heartbeat frame, so `TX node = 0x700`,
`RX node = 0x701`. The panel uses the same frame reports as the CAN Bus Monitor (F2); no firmware change is needed for it.
While it is shown, the "ENGINE OFF" tag and the warning banner of the scene sit at the top of the scene instead of the bottom.

### SOS buzzer (ESP32)
Press **SOS** on the dashboard (or the SOS button): the SOS flag travels over CAN (bit2 of id `0x102`) to the RX board.
When SOS has been active for **3 seconds** the buzzer starts beeping (400 ms on / 300 ms off). It stops immediately when
SOS is cancelled (OK key or the SOS button again) or when the CAN data is lost; the next SOS starts a new 3 s countdown.

| Buzzer module | ESP32 (RX board) |
|---|---|
| S / + (signal) | GPIO4 |
| - | GND |
| VCC (if the module has one) | 3V3 or 5V as printed on the module |

Use a buzzer **module** (it has its own driver transistor) or drive a bare buzzer through an NPN transistor; do not power a
bare buzzer directly from the GPIO. Settings are at the top of `autonet_can.ino`: `BUZZER_PIN`, `BUZZER_PASSIVE`
(1 for a passive buzzer, which needs a tone), `BUZZER_ACTIVE_LEVEL` (LOW for low-trigger modules), `SOS_BUZZER_DELAY_MS`,
`BUZZ_ON_MS` / `BUZZ_OFF_MS` (`BUZZ_OFF_MS 0` = continuous tone) and `BUZZER_ON_TX` / `BUZZER_ON_RX` (which board has the
buzzer; default RX). Re-flash the RX board after changing them. Both status lines now carry `"bz":1` while the alarm sounds.
