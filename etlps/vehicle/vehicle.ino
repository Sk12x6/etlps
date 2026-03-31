// ═══════════════════════════════════════════════════
//  ESP32 #1 — VEHICLE NODE
//  Press BOOT button to toggle siren ON/OFF
//  MAC: 6C:C8:40:05:59:D8
// ═══════════════════════════════════════════════════

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#define BOOT_BTN 0

typedef struct {
  char     id[10];
  bool     active;
  uint8_t  direction;
  uint32_t timestamp;
} EmergencyPacket;

EmergencyPacket pkt;
uint8_t broadcastMAC[] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

bool          sirenOn      = false;
bool          lastBtn      = HIGH;
unsigned long lastDebounce = 0;
unsigned long lastSend     = 0;

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_BTN, INPUT);

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  esp_now_init();

  esp_now_peer_info_t peer;
  memset(&peer, 0, sizeof(peer));
  memcpy(peer.peer_addr, broadcastMAC, 6);
  peer.channel = 1;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  strcpy(pkt.id, "AMBU_01");
  pkt.direction = 0;  // 0=NORTH 1=EAST 2=SOUTH 3=WEST

  Serial.println("Vehicle ready. Press BOOT to toggle siren.");
}

void loop() {
  bool btnState = digitalRead(BOOT_BTN);

  if (btnState == LOW && lastBtn == HIGH) {
    if (millis() - lastDebounce > 50) {
      sirenOn = !sirenOn;
      lastDebounce = millis();
      Serial.println(sirenOn ? "SIREN ON" : "SIREN OFF");

      if (!sirenOn) {
        pkt.active    = false;
        pkt.timestamp = millis();
        esp_now_send(broadcastMAC, (uint8_t*)&pkt, sizeof(pkt));
      }
    }
  }
  lastBtn = btnState;

  if (sirenOn && millis() - lastSend > 200) {
    pkt.active    = true;
    pkt.timestamp = millis();
    esp_now_send(broadcastMAC, (uint8_t*)&pkt, sizeof(pkt));
    Serial.println("Beacon sent");
    lastSend = millis();
  }
}
