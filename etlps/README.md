# Emergency Traffic Light Preemption System
### ESP32 × ESP-NOW × MQTT × Raspberry Pi

A real-time emergency vehicle preemption system that forces a 4-way traffic intersection to clear the path for an ambulance — automatically, with no internet dependency.

---

## How It Works

When the siren switch (BOOT button) is pressed on the vehicle ESP32, it broadcasts an emergency beacon every 200ms via ESP-NOW. The junction controller receives it, safely transitions through yellow and all-red phases, then holds the ambulance lane GREEN and all others RED. When the button is released, the system resumes the normal traffic cycle from where it left off. The Raspberry Pi logs everything and shows a live dashboard.

```
[VEHICLE ESP32]
      │  ESP-NOW broadcast (200ms)
      ▼
[JUNCTION ESP32] ──ESP-NOW──► [MONITOR ESP32]
  Controls lights                    │
  Runs FSM                           │ MQTT
                                     ▼
                              [RASPBERRY PI]
                              Dashboard :5000
```

---

## Hardware

| Component | Qty | Notes |
|---|---|---|
| ESP32 DevKit V1 | 3× | Vehicle, Junction, Monitor |
| Raspberry Pi | 1× | Any model with WiFi |
| Traffic light module (R/Y/G) | 4× | Built-in resistors |
| Push button | 1× | Siren switch (uses BOOT pin) |
| 100µF capacitor | 1× | Across 3.3V on Monitor ESP32 |

---

## MAC Addresses (update if boards change)

| Node | MAC |
|---|---|
| Vehicle  | `6C:C8:40:05:59:D8` |
| Junction | `78:1C:3C:B7:D8:84` |
| Monitor  | `6C:C8:40:05:59:C4` |

---

## Pin Map — Junction (ESP32 #2)

```
NORTH:  RED=27   YELLOW=14   GREEN=13
EAST:   RED=32   YELLOW=18   GREEN=19
SOUTH:  RED=26   YELLOW=25   GREEN=33
WEST:   RED=23   YELLOW=22   GREEN=21
```

Traffic light modules connect directly — GND to GND, VCC to 3.3V or 5V, R/Y/G signal pins to GPIO.

---

## Folder Structure

```
etlps/
├── vehicle/
│   └── vehicle.ino       ESP32 #1 — siren transmitter
├── junction/
│   └── junction.ino      ESP32 #2 — FSM + light control
├── monitor/
│   └── monitor.ino       ESP32 #3 — WiFi/MQTT bridge
├── dashboard/
│   └── app.py            Raspberry Pi Flask dashboard
└── README.md
```

---

## Flash Order

```
1. Flash junction.ino  → ESP32 #2
2. Flash vehicle.ino   → ESP32 #1
3. Flash monitor.ino   → ESP32 #3
4. Run dashboard on RPi
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
# Copy app.py here
python3 app.py
```

Dashboard available at `http://<rpi-ip>:5000`

---

## State Machine (Junction)

```
NS_GREEN → NS_YELLOW → EW_GREEN → EW_YELLOW → (loop)

On emergency:
  current phase → SAFE_TRANSITION → ALLRED_BUFFER
  → EMERGENCY_HOLD → ALLRED_BUFFER → saved phase → normal loop

On override:
  any state → OVERRIDE_HOLD (held until NORMAL command)
```

---

## MQTT Topics

| Topic | Publisher | Payload |
|---|---|---|
| `traffic/emergency` | ESP32 #3 | `ACTIVE from NORTH` / `INACTIVE` |
| `traffic/state` | ESP32 #3 | `NS_GREEN`, `EW_GREEN`, etc. |
| `traffic/override` | RPi dashboard | `NORTH`, `EAST`, `SOUTH`, `WEST`, `ALLRED`, `NORMAL` |
| `traffic/status` | ESP32 #3 | `monitor online` |

---

## Dashboard Features

- Live intersection view with colored traffic lights
- Emergency status with direction display
- Manual override — force any direction green or all-red
- Event log with timestamps
- Statistics — today's count, total, avg duration
- Direction breakdown charts
- Uptime counter

---

## Known Limitations

- No authentication on ESP-NOW beacon — any ESP32 with matching packet structure can trigger emergency
- Single intersection only — multi-junction requires separate junction nodes each with their own MAC
- Direction is hardcoded per vehicle unit

---

## Built With

- ESP-NOW (peer-to-peer, no router dependency)
- Arduino framework for ESP32 (core 2.0.x)
- Mosquitto MQTT broker
- Flask + Socket.IO + paho-mqtt
- SQLite for event persistence

---

*Sathyabama Institute of Science and Technology — ECE, Batch of 2028*
