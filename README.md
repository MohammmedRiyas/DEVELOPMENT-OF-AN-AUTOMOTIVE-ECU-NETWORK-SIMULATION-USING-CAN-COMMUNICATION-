AUTONET — Automotive ECU Network Simulation Using CAN Communication
AUTONET is a Python-based automotive dashboard that demonstrates vehicle-state simulation and communication between two ESP32 nodes over a CAN bus. The hardware setup uses an MCP2515 CAN controller on each node. The RX node sends the received vehicle values back to the PC, and the dashboard displays those returned values.
Features
Vehicle dashboard built with Python and PySide6
Vehicle parameters: speed, RPM, gear, engine temperature, battery voltage, fuel level and pollution
Ignition, seat-belt, SOS, lane-assist, sensors, Eco Mode and Auto Mode controls
Simulation mode for running without CAN hardware
Hardware mode using two ESP32 boards and two MCP2515 modules
Live CAN frame monitor, heartbeat/status checks and communication fault indicators
16×2 LCD text support and SOS buzzer logic on the RX node
> **Note:** This is a simulation and learning project. The displayed vehicle parameters are simulated values, not measurements from a real vehicle.
---
1. Project requirements
Software
Windows 10/11
Python 3.10 or newer, 64-bit
Arduino IDE for flashing ESP32 firmware
Python packages listed in `requirements.txt`
Hardware mode
2 × ESP32 boards
2 × MCP2515 CAN controller modules
CAN transceiver circuitry supported by your modules
CANH/CANL wiring and a common ground
120 Ω termination at each physical end of the CAN bus
Optional: 16×2 LCD and buzzer connected to the RX node as configured in the firmware
The Python dashboard can be tested without the hardware by using simulation mode.
---
2. Download or clone the repository
If the project is on GitHub, clone it and enter the project folder:
```bash
git clone https://github.com/MohammmedRiyas/DEVELOPMENT-OF-AN-AUTOMOTIVE-ECU-NETWORK-SIMULATION-USING-CAN-COMMUNICATION-
cd <YOUR_PROJECT_FOLDER>
```
Alternatively, download the repository as a ZIP and extract it. Run the commands from the folder containing `main.py` and `requirements.txt`.
---
3. Set up Python
Open PowerShell or Command Prompt in the project folder.
Create a virtual environment:
```powershell
py -3.10 -m venv .venv
```
Activate it in PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```
If you use Command Prompt instead:
```bat
.venv\Scripts\activate.bat
```
Install the dependencies:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
The project uses PySide6. The `PySide6-Addons` package provides the Qt SerialPort module used by the CAN-link code.
---
4. Start the dashboard
Option A — Simulation mode (no ESP32 hardware)
```bash
python main.py --sim
```
In simulation mode, dashboard controls update the simulated vehicle state directly.
Option B — Start in a chosen window size
```bash
python main.py --size 1366x768
```
Option C — Full-screen dashboard
```bash
python main.py --fullscreen
```
Press F11 to toggle full screen and Esc to leave full screen.
Dashboard controls
Vehicle parameter sliders: Change speed, RPM, temperature, voltage, fuel and pollution.
Ignition ON/OFF: Start or stop the simulated engine.
D-pad / arrow keys: Up and Down change gear; Left and Right change LCD pages; Enter/OK returns to the home LCD page and cancels an active SOS.
F2: Open or close the separate CAN monitor window when CAN hardware is enabled.
CAN status chip: Click to show or hide the live CAN-message panel when using hardware.
---
5. ESP32 firmware setup
The project README identifies the firmware at:
```text
firmware/autonet_can/autonet_can.ino
```
Open that sketch in the Arduino IDE.
Flash the TX node
Connect the first ESP32 to your PC using USB.
Open `firmware/autonet_can/autonet_can.ino`.
Set the node role to transmitter:
```cpp
   #define NODE_ROLE ROLE_TX
   ```
Confirm that the CAN crystal setting matches the crystal fitted to your MCP2515 module. The project supports the configured `MCP_8MHZ` or `MCP_16MHZ` option.
Select the correct ESP32 board and COM port in Arduino IDE.
Compile and upload the sketch.
Flash the RX node
Connect the second ESP32 to your PC.
Open the same sketch.
Set the node role to receiver:
```cpp
   #define NODE_ROLE ROLE_RX
   ```
Check the MCP2515 crystal setting again.
Select the second ESP32's board and COM port, then compile and upload.
Important: The TX and RX boards must have different roles. If both announce the same role, the dashboard cannot use them as a TX/RX pair.
The project uses the autowp MCP2515 Arduino library, version 1.2 or newer, according to the existing project documentation. Install it through Arduino IDE's Library Manager if it is not already installed.
---
6. MCP2515-to-ESP32 wiring
The project's documented SPI wiring for each ESP32/MCP2515 pair is:
MCP2515 module pin	ESP32 pin
VCC	5V / VIN, as documented for the module
GND	GND
CS	GPIO 5
SCK	GPIO 18
SI / MOSI	GPIO 23
SO / MISO	GPIO 19
INT	Not used by this firmware setup
Repeat the wiring for both the TX and RX nodes.
Connect the two CAN modules
TX-side CAN connection	RX-side CAN connection
CANH	CANH
CANL	CANL
GND	GND
Set the CAN bus bitrate to 500 kbit/s, as expected by the project.
Fit a 120 Ω terminator at each physical end of the bus.
With power disconnected, a correctly terminated bus will typically measure approximately 60 Ω between CANH and CANL.
Check your exact module's voltage requirements before powering it.
Logic-level caution: the project's hardware notes warn that the MCP2515 module's SO/MISO signal may be 5 V. ESP32 GPIOs are not 5 V tolerant; use a suitable level shifter or divider on MISO where required.
Do not rely on wire colors alone; follow the pin labels printed on your specific boards.
---
7. Connect the PC dashboard to the two nodes
The dashboard communicates with the ESP32 boards through USB serial at 115200 baud. Close Arduino Serial Monitor or any other application that is already using either COM port.
Automatic port detection
With both ESP32 boards connected and running their firmware, start:
```bash
python main.py
```
The application scans serial ports and identifies nodes from their announced `TX` and `RX` roles.
Specify COM ports explicitly
If automatic detection does not work, pass the ports for both nodes:
```bash
python main.py --tx-port COM5 --rx-port COM6
```
Replace `COM5` and `COM6` with the actual ports shown in Windows Device Manager. The command-line options are named by node role, not by USB connection order.
What happens to the data?
Dashboard controls update the vehicle state.
The PC sends a serial data line to the TX ESP32.
The TX node transmits vehicle information in CAN frames.
The RX node receives and validates the frames.
The RX node returns decoded vehicle values to the PC over USB serial.
The dashboard displays the values received back through CAN.
The main data CAN IDs documented by the project are:
CAN ID	Purpose
`0x100`	Drive data: speed, RPM and gear information
`0x101`	Engine/telemetry data: temperature, voltage, fuel and pollution
`0x102`	Vehicle flags
`0x700`	TX heartbeat
`0x701`	RX heartbeat
The dashboard status may show states such as `CAN OK`, `NO LINK`, `NO DATA`, `BUS ERR`, `BUS OFF`, `MCP FAIL`, `NO TX` or `NO RX`.
---
8. LCD simulator (optional)
The project supports forwarding RX-node LCD text to a virtual serial port for an LCD simulator.
Install and configure a virtual COM-port pair with a tool such as com0com.
Configure the LCD simulator to listen on one end of the pair.
Start the dashboard with the other end, for example:
```bash
   python main.py --lcd-port COM20
   ```
Optional documented arguments:
```bash
python main.py --lcd-port COM20 --lcd-baud 9600
python main.py --lcd-port COM20 --lcd-baud 9600 --lcd-plain
```
Use the actual virtual COM-port names on your PC. The normal output sends a form-feed character before the two LCD lines; `--lcd-plain` disables that clear character.
For a physical LCD, the project documentation describes firmware options for I²C or parallel LCD wiring. Follow the firmware's `LCD_MODE` and pin definitions before wiring a real display; do not assume a pinout from the dashboard image.
---
9. SOS buzzer and status indicators
The project firmware documentation describes an SOS buzzer on the RX node:
Default buzzer pin: GPIO 4
The buzzer starts after SOS has remained active for 3 seconds
Default beep timing: 400 ms ON / 300 ms OFF
The buzzer stops when SOS is cancelled or CAN data is lost
Use a buzzer module with its own driver, or drive a bare buzzer through a suitable transistor driver. Do not power a bare buzzer directly from an ESP32 GPIO. Verify the firmware's buzzer polarity and module voltage before connecting it.
The dashboard also displays SOS and vehicle warnings. These are project demonstration features, not a certified automotive safety system.
---
10. Troubleshooting
Dashboard says `NO NODES`, `NO TX` or `NO RX`
Check that both ESP32 boards are connected by USB.
Confirm that each board has the correct TX/RX firmware role.
Check the COM-port names in Device Manager.
Close Arduino Serial Monitor and other serial applications.
Try explicit `--tx-port` and `--rx-port` arguments.
Dashboard says `MCP FAIL`, `BUS OFF`, `NO LINK` or `NO DATA`
Confirm that both MCP2515 modules are powered correctly.
Check CS, SCK, MOSI and MISO wiring.
Ensure both nodes use the same CAN bitrate and compatible MCP2515 crystal settings.
Check CANH-to-CANH, CANL-to-CANL and common-ground connections.
Verify the two 120 Ω end terminators.
Check that the RX node is returning valid data and heartbeats.
`QtSerialPort` import error
Activate the project's virtual environment and install the requirements again:
```bash
python -m pip install -r requirements.txt
```
If needed:
```bash
python -m pip install PySide6-Addons
```
Make sure you are running the same Python interpreter into which the packages were installed.
Dashboard starts but values do not change in hardware mode
In hardware mode, the dashboard display is based on values returned by the RX node. Check the complete TX → CAN bus → RX → USB serial path rather than checking only the slider controls.
---
11. Project structure
```text
AUTONET/
├── main.py
├── can_link.py
├── vehicle_state.py
├── requirements.txt
├── firmware/
│   └── autonet_can/
│       └── autonet_can.ino
├── widgets/
│   ├── adas_view.py
│   ├── can_feed.py
│   ├── can_monitor.py
│   ├── control_center.py
│   ├── gauge.py
│   ├── header_bar.py
│   ├── params_panel.py
│   ├── telemetry_card.py
│   └── vehicle_scene.py
└── assets/
    └── scene_bg.png
```
This is a guide to the main files described by the project. Your local repository may contain additional widgets, assets or support files.
---
12. Quick start
Simulation only:
```bash
python -m pip install -r requirements.txt
python main.py --sim
```
With two ESP32 CAN nodes:
Flash one ESP32 as `ROLE_TX` and the other as `ROLE_RX`.
Wire each ESP32 to its MCP2515 module.
Connect CANH, CANL and common GND; check termination.
Connect both ESP32 boards to the PC over USB.
Start the dashboard:
```bash
   python main.py --tx-port COM5 --rx-port COM6
   ```
Change a vehicle parameter and confirm that the CAN monitor and dashboard show the transmitted and returned data.
