// ═══════════════════════════════════════════════════
//  ESP32-C3 — VEHICLE NODE
//  MAC: AC:A7:04:BC:CC:80
//
//  Press BOOT button to cycle through directions:
//  OFF → NORTH → EAST → SOUTH → WEST → OFF
//
//  Each press activates that direction's emergency.
//  Broadcasts ESP-NOW beacon every 200ms while active.
// ═══════════════════════════════════════════════════

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#define BOOT_BTN 9   // GPIO9 on ESP32-C3

typedef struct {
  char     id[10];
  bool     active;
  uint8_t  direction;   // 0=NORTH 1=EAST 2=SOUTH 3=WEST
  uint32_t timestamp;
} EmergencyPacket;

EmergencyPacket pkt;
uint8_t broadcastMAC[] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
const char* dirNames[] = {"NORTH","EAST","SOUTH","WEST"};

int8_t        currentDir   = -1;  // -1 = off
bool          lastBtn      = HIGH;
unsigned long lastDebounce = 0;
unsigned long lastSend     = 0;

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_BTN, INPUT_PULLUP);

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(4, WIFI_SECOND_CHAN_NONE);
  esp_now_init();

  esp_now_peer_info_t peer;
  memset(&peer, 0, sizeof(peer));
  memcpy(peer.peer_addr, broadcastMAC, 6);
  peer.channel = 4;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  strcpy(pkt.id, "AMBU_01");

  Serial.println("Vehicle ready.");
  Serial.println("Press BOOT: OFF → NORTH → EAST → SOUTH → WEST → OFF");
}

void loop() {
  bool btnState = digitalRead(BOOT_BTN);

  if (btnState == LOW && lastBtn == HIGH) {
    if (millis() - lastDebounce > 200) {
      lastDebounce = millis();
      currentDir++;
      if (currentDir > 3) currentDir = -1;

      if (currentDir == -1) {
        pkt.active    = false;
        pkt.timestamp = millis();
        esp_now_send(broadcastMAC, (uint8_t*)&pkt, sizeof(pkt));
        Serial.println("SIREN OFF");
      } else {
        Serial.printf("SIREN ON → %s\n", dirNames[currentDir]);
      }
    }
  }
  lastBtn = btnState;

  if (currentDir >= 0 && millis() - lastSend > 200) {
    pkt.active    = true;
    pkt.direction = (uint8_t)currentDir;
    pkt.timestamp = millis();
    esp_now_send(broadcastMAC, (uint8_t*)&pkt, sizeof(pkt));
    Serial.printf("Beacon → %s\n", dirNames[currentDir]);
    lastSend = millis();
  }
}
