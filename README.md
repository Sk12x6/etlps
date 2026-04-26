# Emergency Traffic Light Preemption System (ETLPS)
### ESP32 × ESP-NOW × MQTT × Raspberry Pi

A real-time emergency vehicle preemption system. When an ambulance activates its siren, the traffic junction automatically clears the path — no internet, no cloud, no delay.

---

## Demo

Press BOOT on vehicle ESP32 to cycle directions:
```
OFF → NORTH → EAST → SOUTH → WEST → OFF
```
Each press activates that direction's emergency. Junction safely transitions and gives green to that lane. Dashboard at `http://192.168.1.163:5000` shows everything live.

---

## Architecture

```
[ESP32-C3 VEHICLE]
      │  ESP-NOW broadcast (200ms)
      ▼
[ESP32 #3 JUNCTION] ←─── [ESP32 #2 MONITOR]
  Controls 4×            WiFi + MQTT bridge
  traffic lights         forwards overrides
                               │
                               │ MQTT
                               ▼
                        [RASPBERRY PI]
                        Mosquitto broker
                        Flask dashboard :5000
```

---

## MAC Addresses

| Node | MAC |
|---|---|
| Vehicle (ESP32-C3) | `AC:A7:04:BC:CC:80` |
| Monitor (ESP32 #2) | `6C:C8:40:05:59:D8` |
| Junction (ESP32 #3) | `78:1C:3C:B7:D8:84` |

---

## Hardware

| Component | Qty | Notes |
|---|---|---|
| ESP32-C3 | 1× | Vehicle node |
| ESP32 DevKit V1 | 2× | Monitor + Junction |
| Raspberry Pi | 1× | Any WiFi model |
| Traffic light module (R/Y/G) | 4× | Built-in resistors |

---

## Pin Map — Junction (ESP32 #3)

```
NORTH:  RED=27   YELLOW=14   GREEN=13
EAST:   RED=5    YELLOW=18   GREEN=19
SOUTH:  RED=22   YELLOW=21   GREEN=23
WEST:   RED=4    YELLOW=15   GREEN=2
```

---

## Folder Structure

```
etlps/
├── vehicle/
│   └── vehicle.ino       ESP32-C3 — siren transmitter
├── junction/
│   └── junction.ino      ESP32 #3 — FSM + light control
├── monitor/
│   └── monitor.ino       ESP32 #2 — WiFi/MQTT bridge
├── dashboard/
│   └── app.py            Raspberry Pi Flask dashboard
└── README.md
```

---

## Flash Order

```
1. junction.ino  → ESP32 #3  (confirm lights cycle)
2. vehicle.ino   → ESP32-C3  (test BOOT button)
3. monitor.ino   → ESP32 #2  (confirm WiFi+MQTT)
4. app.py        → Raspberry Pi
```

---

## Raspberry Pi Setup

```bash
sudo apt install -y mosquitto mosquitto-clients python3-pip
sudo systemctl enable mosquitto && sudo systemctl start mosquitto

# Allow external connections
sudo nano /etc/mosquitto/mosquitto.conf
# Add at bottom:
#   listener 1883
#   allow_anonymous true
sudo systemctl restart mosquitto

mkdir ~/traffic && cd ~/traffic
python3 -m venv venv
source venv/bin/activate
pip install flask flask-socketio paho-mqtt
# Copy app.py here then:
python3 app.py
```

Dashboard at `http://<rpi-ip>:5000`

---

## WiFi Channel

Router must be on a fixed channel. Check with:
```bash
iwlist wlan0 channel | grep Current
```

Update this line in **vehicle.ino** and **junction.ino** to match:
```cpp
esp_wifi_set_channel(4, WIFI_SECOND_CHAN_NONE);  // change 4 to your channel
```

Monitor reads channel automatically after WiFi connects.

---

## State Machine

```
NS_GREEN → NS_YELLOW → EW_GREEN → EW_YELLOW → (loop)

Emergency trigger:
  current phase → SAFE_TRANSITION → ALLRED_BUFFER
  → EMERGENCY_HOLD → ALLRED_BUFFER → saved phase

Override trigger:
  any state → OVERRIDE_HOLD (held until NORMAL command)
```

---

## MQTT Topics

| Topic | Direction | Payload |
|---|---|---|
| `traffic/emergency` | Monitor → RPi | `ACTIVE from NORTH` / `INACTIVE` |
| `traffic/override` | RPi → Monitor → Junction | `NORTH` / `EAST` / `SOUTH` / `WEST` / `ALLRED` / `NORMAL` |
| `traffic/status` | Monitor → RPi | `monitor online` |

---

## Dashboard Features

- Live intersection view with colored lights
- Emergency status with direction
- Manual override panel (6 buttons)
- Event log with timestamps
- Statistics — today, total, avg duration
- Direction breakdown chart
- Uptime counter

---

## Known Limitations

- No authentication on ESP-NOW beacon
- Single intersection only
- Direction hardcoded per vehicle unit
- ESP32 core must be 2.0.17 (not 3.x)

---

*Sathyabama Institute of Science and Technology — ECE Batch 2028*
