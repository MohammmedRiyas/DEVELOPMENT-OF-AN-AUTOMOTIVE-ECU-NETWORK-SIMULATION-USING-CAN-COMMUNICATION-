/*
  AUTONET CAN node  -  ESP32 + MCP2515
  --------------------------------------------------------------------------
  Flash this same sketch to BOTH boards, changing NODE_ROLE below:

    ROLE_TX : takes the parameters from the PC dashboard (USB serial) and
              puts them on the CAN bus.
    ROLE_RX : reads the CAN bus, decodes + validates the frames and sends the
              result back to the PC dashboard (USB serial) for display.

  Library : "mcp2515" by autowp (Arduino Library Manager) - version 1.2 or newer
  Board   : any ESP32 dev module, Serial = 115200 baud

  Wiring (ESP32 VSPI -> MCP2515 module)
    5V -> VCC   GND -> GND   GPIO5 -> CS   GPIO18 -> SCK
    GPIO23 -> SI (MOSI)      GPIO19 <- SO (MISO)      INT not used
    Between the two modules: CANH-CANH, CANL-CANL, GND-GND, 120 ohm at both ends.

  CAN frames (11-bit id, little endian, 500 kbit/s)
    0x100  DRIVE   spd*10 (u16) | rpm (u16) | gear 0..3 = P R N D | drive gear 1..6
    0x101  ENGINE  temp*10 (u16) | volt*100 (u16) | fuel*2 (u8) | pollution (u8)
    0x102  FLAGS   bit0 ignition, 1 belt, 2 sos, 3 lane assist, 4 sensors, 5 eco, 6 auto
    0x700  TX heartbeat   counter | pc_link_ok
    0x701  RX heartbeat   counter | data_fresh

  Serial protocol (one text line each, 115200 baud)
    PC -> TX : S,spd10,rpm,gear,dgear,temp10,volt100,fuel2,poll,flags
    TX -> PC : {"node":"TX","t":"s", ...status...}      every 500 ms
    RX -> PC : {"node":"RX","t":"d", ...values...}      on every new data set
               {"node":"RX","t":"lcd","l1":"..","l2":".."}  16x2 text, whenever it changes
    both     : {"node":..,"t":"f","dir":"tx|rx","id":256,"n":6,"d":"hex","c":count}   CAN frame monitor
               (at most every 100 ms per id and direction; "c" is the running frame count)
  The RX board always builds the 16x2 LCD text; LCD_MODE below decides whether a real LCD on GPIO shows it.
               {"node":"RX","t":"s", ...status...}      every 500 ms

  SOS buzzer (new)
    Press SOS on the dashboard -> the SOS flag (bit2 of CAN id 0x102) reaches the RX board over the CAN bus.
    Once SOS has been active for SOS_BUZZER_DELAY_MS (3 s) the buzzer on BUZZER_PIN starts beeping.
    It stops at once when SOS is cancelled (OK key / SOS button again) or when the CAN data is lost.
    By default the buzzer is fitted to the RX board (BUZZER_ON_RX); set BUZZER_ON_TX to 1 to fit it to the
    TX board as well. Both status lines carry "bz":1 while the alarm is sounding.

  Buzzer wiring (RX board)
    buzzer module S / + -> GPIO4        buzzer module - -> GND        (module VCC -> 3V3 or 5V as its label says)
    A bare buzzer draws more current than a GPIO should supply: use a buzzer MODULE with its own driver
    transistor, or drive a bare buzzer through an NPN transistor (base resistor ~1k) - never straight from the pin.
*/
#include <SPI.h>
#include <mcp2515.h>

#define ROLE_TX 1
#define ROLE_RX 2
#define NODE_ROLE ROLE_RX            // <<< ROLE_TX for board 1, ROLE_RX for board 2

// ---- 16x2 LCD on the RX board (text is always sent to the PC as well, for the LCD simulator) ----
#define LCD_NONE      0
#define LCD_I2C       1                 // I2C backpack: SDA GPIO21, SCL GPIO22, library "LiquidCrystal I2C"
#define LCD_PARALLEL  2                 // plain HD44780 4-bit: RS 13, E 12, D4 14, D5 27, D6 26, D7 25
#define LCD_MODE      LCD_NONE          // <<< change when you attach the real display
#define LCD_I2C_ADDR  0x27

#if LCD_MODE == LCD_I2C
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#elif LCD_MODE == LCD_PARALLEL
#include <LiquidCrystal.h>
#endif

// ---- SOS buzzer -----------------------------------------------------------------------------------
// Which board(s) carry the buzzer. Normally only the RX board (the node that receives the SOS over CAN).
#define BUZZER_ON_TX          0                 // 1 = also drive a buzzer from the TX board
#define BUZZER_ON_RX          1                 // 1 = drive a buzzer from the RX board
#define BUZZER_PIN            4                 // free GPIO on both boards (SPI uses 5/18/19/23, LCD uses 12-14/21/22/25-27)
#define BUZZER_PASSIVE        0                 // 0 = ACTIVE buzzer (has its own oscillator, just switch it on/off)
                                                // 1 = PASSIVE buzzer (needs a tone: generated here with the ESP32 LEDC PWM)
#define BUZZER_ACTIVE_LEVEL   HIGH              // active buzzer only: pin level that turns it ON (HIGH, or LOW for low-trigger modules)
#define BUZZER_FREQ_HZ        2700              // passive buzzer only: tone frequency
#define BUZZER_LEDC_CH        0                 // passive buzzer only, arduino-esp32 2.x only: LEDC channel
#define SOS_BUZZER_DELAY_MS   3000              // SOS must stay active this long before the buzzer starts (3 s)
#define BUZZ_ON_MS            400               // beep length while alarming
#define BUZZ_OFF_MS           300               // pause between beeps (0 = one continuous tone)

#define CAN_BITRATE  CAN_500KBPS
#define CAN_CRYSTAL  MCP_8MHZ        // read the crystal on YOUR module: 8.000 -> MCP_8MHZ, 16.000 -> MCP_16MHZ

static const int PIN_SCK = 18, PIN_MISO = 19, PIN_MOSI = 23, PIN_CS = 5;

static const uint32_t ID_DRIVE = 0x100, ID_ENGINE = 0x101, ID_FLAGS = 0x102;
static const uint32_t ID_HB_TX = 0x700, ID_HB_RX = 0x701;

static const uint32_t SEND_MS     = 50;     // data frames (TX)       -> 20 Hz
static const uint32_t HEARTBEAT_MS = 200;
static const uint32_t STATUS_MS   = 500;
static const uint32_t TIMEOUT_MS  = 600;    // peer / data considered lost after this
static const uint32_t PC_TIMEOUT_MS = 1500; // TX: stop sending when the PC goes quiet

MCP2515 mcp(PIN_CS, 4000000);               // 4 MHz SPI: safe for breadboard wires
static bool mcpOk = false;
static uint32_t lastInitTry = 0;

// Process image shared by both roles
struct Image {
  uint16_t spd10 = 0, rpm = 0, temp10 = 0, volt100 = 0;
  uint8_t gear = 0, dgear = 1, fuel2 = 0, poll = 0, flags = 0;
} img;

static uint32_t sentOk = 0, sentFail = 0;
static uint8_t hbCounter = 0;
static uint32_t tHb = 0, tStatus = 0;
static uint32_t lastPeerHb = 0;             // last heartbeat from the other node
static bool everPeer = false;

#if NODE_ROLE == ROLE_TX
#define NODE_NAME "TX"
#else
#define NODE_NAME "RX"
#endif

// 1 when THIS board (the role selected above) has a buzzer fitted, according to BUZZER_ON_TX / BUZZER_ON_RX
#if (NODE_ROLE == ROLE_TX && BUZZER_ON_TX) || (NODE_ROLE == ROLE_RX && BUZZER_ON_RX)
#define BUZZER_ENABLED 1
#else
#define BUZZER_ENABLED 0
#endif

// CAN frame monitor: tells the PC which ids went out / came in (for the "CAN Bus Monitor" window)
struct FrameStat { uint32_t id; uint8_t dir; uint32_t count; uint32_t lastRep; };
static FrameStat frameStats[12];
static uint8_t numFrameStats = 0;
static void reportFrame(uint8_t dir, uint32_t id, const uint8_t *d, uint8_t n) {
  FrameStat *f = nullptr;
  for (uint8_t i = 0; i < numFrameStats; i++) if (frameStats[i].id == id && frameStats[i].dir == dir) { f = &frameStats[i]; break; }
  if (!f) {
    if (numFrameStats >= 12) return;
    f = &frameStats[numFrameStats++];
    f->id = id; f->dir = dir; f->count = 0; f->lastRep = 0;
  }
  f->count++;
  uint32_t now = millis();
  if (f->count > 1 && now - f->lastRep < 100) return;
  f->lastRep = now;
  char hex[17] = "";
  for (uint8_t i = 0; i < n && i < 8; i++) snprintf(hex + 2 * i, 3, "%02X", d[i]);
  Serial.printf("{\"node\":\"%s\",\"t\":\"f\",\"dir\":\"%s\",\"id\":%lu,\"n\":%u,\"d\":\"%s\",\"c\":%lu}\n",
                NODE_NAME, dir ? "rx" : "tx", (unsigned long)id, n, hex, (unsigned long)f->count);
}

// ------------------------------------------------------------------ helpers
static bool initCan() {
  if (mcp.reset() != MCP2515::ERROR_OK) return false;
  if (mcp.setBitrate(CAN_BITRATE, CAN_CRYSTAL) != MCP2515::ERROR_OK) return false;
  if (mcp.setNormalMode() != MCP2515::ERROR_OK) return false;
  return true;
}

static const char *canState() {
  if (!mcpOk) return "INIT_FAIL";
  if (mcp.getErrorFlags() & MCP2515::EFLG_TXBO) return "BUSOFF";
  if (mcp.errorCountTX() >= 128 || mcp.errorCountRX() >= 128) return "ERR";
  return "OK";
}

static bool sendFrame(uint32_t id, const uint8_t *d, uint8_t n) {
  if (!mcpOk) { sentFail++; return false; }
  struct can_frame f;
  f.can_id = id;
  f.can_dlc = n;
  memset(f.data, 0, sizeof(f.data));
  memcpy(f.data, d, n);
  if (mcp.sendMessage(&f) == MCP2515::ERROR_OK) { sentOk++; reportFrame(0, id, d, n); return true; }
  sentFail++;
  return false;
}

static inline uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static inline void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }

static bool peerAlive(uint32_t now) { return everPeer && (now - lastPeerHb) < TIMEOUT_MS; }

// ====================================================================== SOS BUZZER
// State machine, called from roleLoop() on every pass (never blocks, no delay()):
//
//   SOS off ........................ silent, countdown cleared
//   SOS on, less than 3 s .......... silent, counting      (sosSince = moment SOS was first seen)
//   SOS on, 3 s or more ............ ALARM: BUZZ_ON_MS beep / BUZZ_OFF_MS pause, repeating
//   SOS off again (or data lost) ... silent immediately, and the next SOS starts a fresh 3 s countdown
#if BUZZER_ENABLED
static bool sosSeen = false;              // SOS was active on the previous pass
static uint32_t sosSince = 0;             // millis() when the current SOS started
static bool alarming = false;             // the 3 s have elapsed and the alarm is running
static bool beepOn = false;               // alarm is currently in the "beep" half of the pattern
static uint32_t beepT = 0;                // millis() of the last beep / pause change

// Switch the buzzer hardware on or off.
static void buzzerDrive(bool on) {
#if BUZZER_PASSIVE
  // passive buzzer: 50 % duty square wave at BUZZER_FREQ_HZ while "on", 0 % while "off"
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(BUZZER_PIN, on ? 128 : 0);                       // arduino-esp32 3.x: LEDC is addressed by pin
#else
  ledcWrite(BUZZER_LEDC_CH, on ? 128 : 0);                   // arduino-esp32 2.x: LEDC is addressed by channel
#endif
#else
  // active buzzer: plain on/off
  digitalWrite(BUZZER_PIN, on ? BUZZER_ACTIVE_LEVEL : !BUZZER_ACTIVE_LEVEL);
#endif
}

// Configure the pin. Called once from setup(); the buzzer starts silent.
static void buzzerBegin() {
#if BUZZER_PASSIVE
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(BUZZER_PIN, BUZZER_FREQ_HZ, 8);                 // 8-bit PWM, 128 = 50 % duty
#else
  ledcSetup(BUZZER_LEDC_CH, BUZZER_FREQ_HZ, 8);
  ledcAttachPin(BUZZER_PIN, BUZZER_LEDC_CH);
#endif
#else
  pinMode(BUZZER_PIN, OUTPUT);
#endif
  buzzerDrive(false);
}

// sos = "an SOS request is active RIGHT NOW and the data it came from is trustworthy".
static void buzzerUpdate(uint32_t now, bool sos) {
  if (!sos) {                                                // cancelled / link lost -> silence immediately
    sosSeen = false;
    if (alarming) { alarming = false; beepOn = false; buzzerDrive(false); }
    return;
  }
  if (!sosSeen) { sosSeen = true; sosSince = now; }          // SOS just started: begin the 3 s countdown
  if (!alarming) {
    if (now - sosSince < SOS_BUZZER_DELAY_MS) return;        // still inside the 3 s delay: stay quiet
    alarming = true;                                         // delay over: first beep right now
    beepOn = true;
    beepT = now;
    buzzerDrive(true);
    return;
  }
#if BUZZ_OFF_MS > 0
  if (now - beepT >= (beepOn ? (uint32_t)BUZZ_ON_MS : (uint32_t)BUZZ_OFF_MS)) {   // time to flip beep <-> pause
    beepOn = !beepOn;
    beepT = now;
    buzzerDrive(beepOn);
  }
#endif                                                       // BUZZ_OFF_MS == 0: continuous tone, nothing to toggle
}

static bool buzzerAlarming() { return alarming; }
#else
static bool buzzerAlarming() { return false; }               // no buzzer on this board
#endif

// ====================================================================== TX
#if NODE_ROLE == ROLE_TX
static uint32_t tSend = 0;
static uint32_t lastPcMs = 0;
static bool havePc = false;
static uint32_t badLines = 0;
static char lineBuf[120];
static size_t lineLen = 0;

static void parseLine(char *s) {
  unsigned v[9];
  if (sscanf(s, "S,%u,%u,%u,%u,%u,%u,%u,%u,%u", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7], &v[8]) != 9 ||
      v[0] > 2200 || v[1] > 8000 || v[2] > 3 || v[3] < 1 || v[3] > 6 || v[4] > 1500 ||
      v[5] > 1600 || v[6] > 200 || v[7] > 100 || v[8] > 0x7F) {
    badLines++;
    return;
  }
  img.spd10 = v[0]; img.rpm = v[1]; img.gear = v[2]; img.dgear = v[3];
  img.temp10 = v[4]; img.volt100 = v[5]; img.fuel2 = v[6]; img.poll = v[7]; img.flags = v[8];
  lastPcMs = millis();
  havePc = true;
}

static void readPc() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen) { lineBuf[lineLen] = 0; parseLine(lineBuf); lineLen = 0; }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;                       // overlong line: drop it
    }
  }
}

static void sendData() {
  uint8_t b[6];
  put16(b, img.spd10); put16(b + 2, img.rpm); b[4] = img.gear; b[5] = img.dgear;
  sendFrame(ID_DRIVE, b, 6);
  put16(b, img.temp10); put16(b + 2, img.volt100); b[4] = img.fuel2; b[5] = img.poll;
  sendFrame(ID_ENGINE, b, 6);
  b[0] = img.flags;
  sendFrame(ID_FLAGS, b, 1);
}

static void handleFrame(const struct can_frame &f, uint32_t now) {
  if (f.can_id == ID_HB_RX) { lastPeerHb = now; everPeer = true; }
}

static void sendHeartbeat(uint32_t now) {
  uint8_t b[2] = { hbCounter++, (uint8_t)((havePc && now - lastPcMs < PC_TIMEOUT_MS) ? 1 : 0) };
  sendFrame(ID_HB_TX, b, 2);
}

static void printStatus(uint32_t now) {
  bool pc = havePc && (now - lastPcMs < PC_TIMEOUT_MS);
  Serial.printf("{\"node\":\"TX\",\"t\":\"s\",\"can\":\"%s\",\"peer\":%d,\"pc\":%d,\"sent\":%lu,\"fail\":%lu,"
                "\"bad\":%lu,\"tec\":%u,\"rec\":%u,\"bz\":%d}\n",
                canState(), peerAlive(now) ? 1 : 0, pc ? 1 : 0, (unsigned long)sentOk, (unsigned long)sentFail,
                (unsigned long)badLines, mcpOk ? mcp.errorCountTX() : 0, mcpOk ? mcp.errorCountRX() : 0,
                buzzerAlarming() ? 1 : 0);
}

static void roleLoop(uint32_t now) {
  readPc();
#if BUZZER_ENABLED
  // TX board: the SOS flag comes straight from the PC (only trusted while the PC is still talking to us)
  buzzerUpdate(now, havePc && (now - lastPcMs < PC_TIMEOUT_MS) && (img.flags & 4));
#endif
  if (now - tSend >= SEND_MS) {
    tSend = now;
    if (havePc && now - lastPcMs < PC_TIMEOUT_MS) sendData();
  }
  if (now - tHb >= HEARTBEAT_MS) { tHb = now; sendHeartbeat(now); }
  if (now - tStatus >= STATUS_MS) { tStatus = now; printStatus(now); }
}

// ====================================================================== RX
#elif NODE_ROLE == ROLE_RX
static uint32_t rxFrames = 0, badFrames = 0;
static uint8_t haveMask = 0;               // bit0 drive, bit1 engine, bit2 flags
static uint32_t lastDataMs = 0, lastPrintMs = 0;
static bool dirty = false;

static void handleFrame(const struct can_frame &f, uint32_t now) {
  rxFrames++;
  bool ok = true;
  switch (f.can_id) {
    case ID_DRIVE: {
      if (f.can_dlc < 6) { ok = false; break; }
      uint16_t spd = u16(f.data), rpm = u16(f.data + 2);
      if (spd > 2200 || rpm > 8000 || f.data[4] > 3 || f.data[5] < 1 || f.data[5] > 6) { ok = false; break; }
      img.spd10 = spd; img.rpm = rpm; img.gear = f.data[4]; img.dgear = f.data[5];
      haveMask |= 1; break;
    }
    case ID_ENGINE: {
      if (f.can_dlc < 6) { ok = false; break; }
      uint16_t t = u16(f.data), v = u16(f.data + 2);
      if (t > 1500 || v > 1600 || f.data[4] > 200 || f.data[5] > 100) { ok = false; break; }
      img.temp10 = t; img.volt100 = v; img.fuel2 = f.data[4]; img.poll = f.data[5];
      haveMask |= 2; break;
    }
    case ID_FLAGS: {
      if (f.can_dlc < 1 || f.data[0] > 0x7F) { ok = false; break; }
      img.flags = f.data[0];
      haveMask |= 4; break;
    }
    case ID_HB_TX:
      lastPeerHb = now; everPeer = true;
      return;
    default:
      return;                               // not ours
  }
  if (!ok) { badFrames++; return; }
  lastDataMs = now;
  lastPeerHb = now; everPeer = true;        // data frames also prove the link is alive
  dirty = true;
}

static bool dataFresh(uint32_t now) { return haveMask == 7 && (now - lastDataMs) < TIMEOUT_MS; }

static void sendHeartbeat(uint32_t now) {
  uint8_t b[2] = { hbCounter++, (uint8_t)(dataFresh(now) ? 1 : 0) };
  sendFrame(ID_HB_RX, b, 2);
}

static void printData() {
  Serial.printf("{\"node\":\"RX\",\"t\":\"d\",\"s\":%u,\"r\":%u,\"g\":%u,\"dg\":%u,\"tp\":%u,\"v\":%u,"
                "\"f\":%u,\"p\":%u,\"fl\":%u}\n",
                img.spd10, img.rpm, img.gear, img.dgear, img.temp10, img.volt100, img.fuel2, img.poll, img.flags);
}

static void printStatus(uint32_t now) {
  Serial.printf("{\"node\":\"RX\",\"t\":\"s\",\"can\":\"%s\",\"link\":%d,\"fresh\":%d,\"rx\":%lu,\"bad\":%lu,"
                "\"age\":%lu,\"tec\":%u,\"rec\":%u,\"bz\":%d}\n",
                canState(), peerAlive(now) ? 1 : 0, dataFresh(now) ? 1 : 0, (unsigned long)rxFrames,
                (unsigned long)badFrames, everPeer ? (unsigned long)(now - lastPeerHb) : 99999UL,
                mcpOk ? mcp.errorCountTX() : 0, mcpOk ? mcp.errorCountRX() : 0, buzzerAlarming() ? 1 : 0);
}

// ---------------------------------------------------------------- 16x2 LCD
#if LCD_MODE == LCD_I2C
static LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 16, 2);
#elif LCD_MODE == LCD_PARALLEL
static LiquidCrystal lcd(13, 12, 14, 27, 26, 25);
#endif

static char lcdOld1[17] = "", lcdOld2[17] = "";
static uint32_t tLcd = 0;

static void lcdBegin() {
#if LCD_MODE == LCD_I2C
  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
#elif LCD_MODE == LCD_PARALLEL
  lcd.begin(16, 2);
#endif
}

// same thresholds as the dashboard: returns 0 none, 1 warning, 2 critical and the alert text
static uint8_t topAlert(const char **txt) {
  uint8_t best = 0;
  const char *bt = "";
  auto test = [&](uint8_t lv, const char *t) { if (lv > best) { best = lv; bt = t; } };
  uint16_t spd = img.spd10 / 10, fuel = img.fuel2 / 2;
  test(img.temp10 > 1200 ? 2 : img.temp10 > 1050 ? 1 : 0, "ENGINE TEMP HIGH");
  test((img.volt100 < 1100 || img.volt100 > 1550) ? 2 : (img.volt100 < 1180 || img.volt100 > 1480) ? 1 : 0, "BATTERY VOLTAGE");
  test(img.fuel2 < 14 ? 2 : img.fuel2 < 30 ? 1 : 0, "LOW FUEL");
  test(img.poll > 75 ? 2 : img.poll > 50 ? 1 : 0, "HIGH EMISSIONS");
  test(spd > 200 ? 2 : spd > 160 ? 1 : 0, "OVERSPEED");
  test(img.rpm > 7500 ? 2 : img.rpm > 6500 ? 1 : 0, "RPM RED ZONE");
  test(((img.flags & 1) && !(img.flags & 2) && spd > 10) ? 1 : 0, "FASTEN SEAT BELT");
  (void)fuel;
  *txt = bt;
  return best;
}

static void buildLcd(uint32_t now, char *l1, char *l2) {
  if (!peerAlive(now) || !dataFresh(now)) {
    snprintf(l1, 17, "%s", haveMask == 7 || everPeer ? "CAN LINK LOST" : "AUTONET SYSTEM");
    snprintf(l2, 17, "%s", everPeer ? "CHECK BUS" : "WAITING FOR CAN");
    return;
  }
  if (img.flags & 4) {
    snprintf(l1, 17, "!! SOS ACTIVE !!");
    snprintf(l2, 17, "HELP REQUESTED");
    return;
  }
  const char *at = "";
  uint8_t lv = topAlert(&at);
  if (lv) {
    snprintf(l1, 17, "%s", lv == 2 ? "CRITICAL" : "WARNING");
    snprintf(l2, 17, "%s", at);
    return;
  }
  static const char GEARS[] = {'P', 'R', 'N', 'D'};
  switch ((now / 2500) % 5) {                    // pages rotate every 2.5 s
    case 0:
      snprintf(l1, 17, "AUTONET SYSTEM");
      snprintf(l2, 17, "%s", (img.flags & 1) ? "ALL NORMAL" : "IGNITION OFF");
      break;
    case 1:
      snprintf(l1, 17, "SPD %5u KM/H", img.spd10 / 10);
      snprintf(l2, 17, "RPM %5u  G:%c", img.rpm, GEARS[img.gear & 3]);
      break;
    case 2:
      snprintf(l1, 17, "TEMP %5u C", img.temp10 / 10);
      snprintf(l2, 17, "BATT %2u.%u V", img.volt100 / 100, (img.volt100 % 100) / 10);
      break;
    case 3:
      snprintf(l1, 17, "FUEL %5u %%", img.fuel2 / 2);
      snprintf(l2, 17, "POLL %5u %%", img.poll);
      break;
    default:
      snprintf(l1, 17, "CAN OK");
      snprintf(l2, 17, "RX%5lu E%u/%u", (unsigned long)(rxFrames % 100000UL), mcp.errorCountTX(), mcp.errorCountRX());
  }
}

static void lcdUpdate(uint32_t now) {
  char l1[17], l2[17];
  buildLcd(now, l1, l2);
  if (strcmp(l1, lcdOld1) == 0 && strcmp(l2, lcdOld2) == 0) return;
  strcpy(lcdOld1, l1);
  strcpy(lcdOld2, l2);
  Serial.printf("{\"node\":\"RX\",\"t\":\"lcd\",\"l1\":\"%s\",\"l2\":\"%s\"}\n", l1, l2);
#if LCD_MODE != LCD_NONE
  char b[17];
  snprintf(b, 17, "%-16s", l1);
  lcd.setCursor(0, 0); lcd.print(b);
  snprintf(b, 17, "%-16s", l2);
  lcd.setCursor(0, 1); lcd.print(b);
#endif
}

static void roleLoop(uint32_t now) {
#if BUZZER_ENABLED
  // RX board: the SOS flag (bit2 of 0x102) must have come over the CAN bus, and the data must be fresh
  buzzerUpdate(now, peerAlive(now) && dataFresh(now) && (img.flags & 4));
#endif
  if (dirty && haveMask == 7 && now - lastPrintMs >= SEND_MS) {
    lastPrintMs = now;
    dirty = false;
    printData();
  }
  if (now - tLcd >= 200) { tLcd = now; lcdUpdate(now); }
  if (now - tHb >= HEARTBEAT_MS) { tHb = now; sendHeartbeat(now); }
  if (now - tStatus >= STATUS_MS) { tStatus = now; printStatus(now); }
}
#else
#error "Set NODE_ROLE to ROLE_TX or ROLE_RX"
#endif

// ================================================================== common
void setup() {
  Serial.begin(115200);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);
#if NODE_ROLE == ROLE_RX
  lcdBegin();
#endif
#if BUZZER_ENABLED
  buzzerBegin();                             // buzzer pin configured and silent
#endif
  mcpOk = initCan();
  lastInitTry = millis();
}

void loop() {
  uint32_t now = millis();

  if (!mcpOk) {                              // keep trying if the MCP2515 was not found
    if (now - lastInitTry >= 2000) { lastInitTry = now; mcpOk = initCan(); }
  } else {
    struct can_frame f;
    while (mcp.readMessage(&f) == MCP2515::ERROR_OK) {
      reportFrame(1, f.can_id, f.data, f.can_dlc);
      handleFrame(f, now);
    }
    if (mcp.getErrorFlags() & (MCP2515::EFLG_RX0OVR | MCP2515::EFLG_RX1OVR)) mcp.clearRXnOVRFlags();
  }

  roleLoop(now);
}
