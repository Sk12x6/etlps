// ═══════════════════════════════════════════════════
//  ESP32 #2 — JUNCTION CONTROLLER
//  Runs 4-phase FSM + emergency preemption + override
//  MAC: 78:1C:3C:B7:D8:84
// ═══════════════════════════════════════════════════

#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>

// ── PINS ─────────────────────────────────────────
#define N_RED 27
#define N_YEL 14
#define N_GRN 13

#define E_RED 32
#define E_YEL 18
#define E_GRN 19

#define S_RED 26
#define S_YEL 25
#define S_GRN 33

#define W_RED 23
#define W_YEL 22
#define W_GRN 21

const uint8_t PIN[4][3] = {
  {N_RED,N_YEL,N_GRN},  // NORTH [0]
  {E_RED,E_YEL,E_GRN},  // EAST  [1]
  {S_RED,S_YEL,S_GRN},  // SOUTH [2]
  {W_RED,W_YEL,W_GRN},  // WEST  [3]
};
#define R 0
#define Y 1
#define G 2

// ── TIMING ───────────────────────────────────────
#define GREEN_MS   5000
#define YELLOW_MS  2000
#define ALLRED_MS  1500
#define TIMEOUT_MS 10000

// ── STATES ───────────────────────────────────────
enum State {
  NS_GREEN, NS_YELLOW,
  EW_GREEN, EW_YELLOW,
  SAFE_TRANSITION,
  ALLRED_BUFFER,
  EMERGENCY_HOLD,
  OVERRIDE_HOLD
};

// ── PACKETS ──────────────────────────────────────
typedef struct {
  char     id[10];
  bool     active;
  uint8_t  direction;
  uint32_t timestamp;
} EmergencyPacket;

typedef struct {
  char command[12];
} OverridePacket;

// ── GLOBALS ──────────────────────────────────────
State    state      = NS_GREEN;
State    savedState = NS_GREEN;
uint32_t stateTimer = 0;

volatile bool    eFlag = false;
volatile uint8_t eDir  = 0;
uint32_t         eTs   = 0;
bool             resuming = false;

// ── LIGHT HELPERS ────────────────────────────────
void setLight(uint8_t dir, uint8_t color) {
  digitalWrite(PIN[dir][0], LOW);
  digitalWrite(PIN[dir][1], LOW);
  digitalWrite(PIN[dir][2], LOW);
  digitalWrite(PIN[dir][color], HIGH);
}
void allRed()        { for(int d=0;d<4;d++) setLight(d,R); }
void applyNSGreen()  { setLight(0,G);setLight(2,G);setLight(1,R);setLight(3,R); }
void applyNSYellow() { setLight(0,Y);setLight(2,Y);setLight(1,R);setLight(3,R); }
void applyEWGreen()  { setLight(1,G);setLight(3,G);setLight(0,R);setLight(2,R); }
void applyEWYellow() { setLight(1,Y);setLight(3,Y);setLight(0,R);setLight(2,R); }
void applyEmergency(uint8_t dir) { allRed(); setLight(dir,G); }

void goTo(State next) { state=next; stateTimer=millis(); }

void resumeNormal() {
  eFlag = false;
  goTo(NS_GREEN);
  applyNSGreen();
  Serial.println("[FSM] Normal cycle resumed");
}

// ── ESP-NOW CALLBACK ─────────────────────────────
void onReceive(const uint8_t* mac, const uint8_t* data, int len) {

  if (len == sizeof(EmergencyPacket)) {
    EmergencyPacket pkt;
    memcpy(&pkt, data, sizeof(pkt));
    if (pkt.active) {
      eFlag = true;
      eDir  = pkt.direction;
      eTs   = millis();
      if (state == OVERRIDE_HOLD) {
        savedState = NS_GREEN;
        goTo(ALLRED_BUFFER);
        allRed();
        resuming = false;
      }
      Serial.printf("[EMERGENCY] dir=%d\n", pkt.direction);
    } else {
      eFlag = false;
      Serial.println("[EMERGENCY] cleared");
    }
  }

  else if (len == sizeof(OverridePacket)) {
    OverridePacket pkt;
    memcpy(&pkt, data, sizeof(pkt));
    String cmd = String(pkt.command);
    Serial.printf("[OVERRIDE] %s\n", pkt.command);

    if (cmd == "NORMAL") {
      resumeNormal();
    } else {
      eFlag = false;
      allRed();
      if      (cmd == "NORTH") setLight(0,G);
      else if (cmd == "EAST")  setLight(1,G);
      else if (cmd == "SOUTH") setLight(2,G);
      else if (cmd == "WEST")  setLight(3,G);
      goTo(OVERRIDE_HOLD);
    }
  }
}

// ── SETUP ────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  for(int d=0;d<4;d++)
    for(int c=0;c<3;c++)
      pinMode(PIN[d][c], OUTPUT);

  allRed();
  delay(1000);

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  esp_now_init();
  esp_now_register_recv_cb(onReceive);

  goTo(NS_GREEN);
  applyNSGreen();
  Serial.println("[BOOT] Junction ready");
}

// ── MAIN LOOP ────────────────────────────────────
void loop() {
  uint32_t now = millis();

  if (eFlag && (now - eTs > TIMEOUT_MS)) {
    eFlag = false;
    Serial.println("[TIMEOUT] Emergency cleared");
  }

  switch(state) {

    case NS_GREEN:
      if (eFlag) {
        savedState = NS_GREEN;
        goTo(SAFE_TRANSITION);
        applyNSYellow();
      } else if (now - stateTimer > GREEN_MS) {
        goTo(NS_YELLOW);
        applyNSYellow();
      }
      break;

    case NS_YELLOW:
      if (now - stateTimer > YELLOW_MS) {
        if (eFlag) { savedState=EW_GREEN; goTo(ALLRED_BUFFER); allRed(); }
        else       { goTo(EW_GREEN); applyEWGreen(); }
      }
      break;

    case EW_GREEN:
      if (eFlag) {
        savedState = EW_GREEN;
        goTo(SAFE_TRANSITION);
        applyEWYellow();
      } else if (now - stateTimer > GREEN_MS) {
        goTo(EW_YELLOW);
        applyEWYellow();
      }
      break;

    case EW_YELLOW:
      if (now - stateTimer > YELLOW_MS) {
        if (eFlag) { savedState=NS_GREEN; goTo(ALLRED_BUFFER); allRed(); }
        else       { goTo(NS_GREEN); applyNSGreen(); }
      }
      break;

    case SAFE_TRANSITION:
      if (now - stateTimer > YELLOW_MS) {
        resuming = false;
        goTo(ALLRED_BUFFER);
        allRed();
      }
      break;

    case ALLRED_BUFFER:
      if (now - stateTimer > ALLRED_MS) {
        if (resuming) {
          resuming = false;
          switch(savedState) {
            case NS_GREEN: goTo(NS_GREEN); applyNSGreen(); break;
            case EW_GREEN: goTo(EW_GREEN); applyEWGreen(); break;
            default:       goTo(NS_GREEN); applyNSGreen(); break;
          }
          Serial.println("[FSM] Resumed after emergency");
        } else {
          goTo(EMERGENCY_HOLD);
          applyEmergency(eDir);
          Serial.printf("[FSM] EMERGENCY_HOLD dir=%d\n", eDir);
        }
      }
      break;

    case EMERGENCY_HOLD:
      if (!eFlag) {
        resuming = true;
        goTo(ALLRED_BUFFER);
        allRed();
        Serial.println("[FSM] Emergency over");
      }
      break;

    case OVERRIDE_HOLD:
      // Waits here until NORMAL command or emergency arrives
      break;
  }
}
