// ═══════════════════════════════════════════════════
//  ESP32 #2 — MONITOR NODE
//  MAC: 6C:C8:40:05:59:D8
//
//  Bridges ESP-NOW ↔ WiFi/MQTT
//  - Receives emergency beacons from vehicle
//  - Publishes to Raspberry Pi via MQTT
//  - Receives override commands from dashboard
//  - Forwards overrides to junction via ESP-NOW
// ═══════════════════════════════════════════════════

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <PubSubClient.h>

const char* SSID     = "Kumaran_2";
const char* PASSWORD = "Palani@2012";
const char* MQTT_IP  = "192.168.1.163";

// Junction MAC — ESP32 #3
uint8_t junctionMAC[] = {0x78,0x1C,0x3C,0xB7,0xD8,0x84};

typedef struct {
  char     id[10];
  bool     active;
  uint8_t  direction;
  uint32_t timestamp;
} EmergencyPacket;

typedef struct {
  uint8_t type;      // always 2 for override
  char    command[12];
} OverridePacket;

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
const char*  dirName[] = {"NORTH","EAST","SOUTH","WEST"};
unsigned long lastReconnect = 0;

// ── MQTT CALLBACK — override from RPi dashboard ──
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  char cmd[12];
  memset(cmd, 0, sizeof(cmd));
  for (int i = 0; i < min((int)length, 11); i++)
    cmd[i] = (char)payload[i];
  Serial.printf("[OVERRIDE] forwarding: %s\n", cmd);

  OverridePacket pkt;
  memset(&pkt, 0, sizeof(pkt));
  pkt.type = 2;
  strncpy(pkt.command, cmd, 11);
  esp_now_send(junctionMAC, (uint8_t*)&pkt, sizeof(pkt));
}

// ── ESP-NOW CALLBACK — emergency from vehicle ──
void onReceive(const uint8_t* mac, const uint8_t* data, int len) {
  if (len != sizeof(EmergencyPacket)) return;
  EmergencyPacket pkt;
  memcpy(&pkt, data, sizeof(pkt));
  if (!mqtt.connected()) return;

  if (pkt.active) {
    char msg[32];
    sprintf(msg, "ACTIVE from %s", dirName[pkt.direction]);
    mqtt.publish("traffic/emergency", msg);
    Serial.println(msg);
  } else {
    mqtt.publish("traffic/emergency", "INACTIVE");
    Serial.println("INACTIVE");
  }
}

void reconnectMQTT() {
  if (mqtt.connected()) return;
  unsigned long now = millis();
  if (now - lastReconnect > 2000) {
    lastReconnect = now;
    Serial.print("Connecting MQTT...");
    if (mqtt.connect("ESP32Monitor")) {
      Serial.println("connected");
      mqtt.subscribe("traffic/override");
      mqtt.publish("traffic/status", "monitor online");
    } else {
      Serial.print("failed rc=");
      Serial.println(mqtt.state());
    }
  }
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_AP_STA);
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  uint8_t ch = WiFi.channel();
  Serial.printf("Channel: %d\n", ch);
  esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);

  esp_now_init();
  esp_now_register_recv_cb(onReceive);

  // Register junction as peer for override forwarding
  esp_now_peer_info_t peer;
  memset(&peer, 0, sizeof(peer));
  memcpy(peer.peer_addr, junctionMAC, 6);
  peer.channel = ch;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  mqtt.setServer(MQTT_IP, 1883);
  mqtt.setCallback(mqttCallback);
}

void loop() {
  reconnectMQTT();
  mqtt.loop();
}
