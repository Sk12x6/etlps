from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt_client
import threading
import sqlite3
import time
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'etlp2025'
sio = SocketIO(app, cors_allowed_origins="*")

MQTT_IP  = "localhost"
MQTT_PORT = 1883
DB_PATH  = "traffic.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, direction TEXT, duration REAL, latency REAL)''')
    conn.commit(); conn.close()

def save_event(direction, duration, latency):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO events (ts,direction,duration,latency) VALUES (?,?,?,?)',
              (time.time(), direction, duration, latency))
    conn.commit(); conn.close()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM events')
    total = c.fetchone()[0]
    c.execute('SELECT AVG(duration) FROM events WHERE duration > 0')
    avg_dur = c.fetchone()[0] or 0
    c.execute('SELECT AVG(latency) FROM events WHERE latency > 0')
    avg_lat = c.fetchone()[0] or 0
    c.execute('SELECT direction, COUNT(*) FROM events GROUP BY direction ORDER BY COUNT(*) DESC')
    by_dir = c.fetchall()
    c.execute('SELECT ts,direction,duration,latency FROM events ORDER BY ts DESC LIMIT 20')
    recent = c.fetchall()
    conn.close()
    return {"total":total,"avg_duration":round(avg_dur,1),
            "avg_latency":round(avg_lat,0),"by_direction":by_dir,"recent":recent}

state = {"emergency":False,"direction":None,"phase":"NS_GREEN",
         "start_ts":None,"mqtt_ts":None}
mqtt_publisher = None

def on_message(client, userdata, msg):
    global state
    topic = msg.topic; payload = msg.payload.decode(); now = time.time()
    if topic == "traffic/emergency":
        if payload.startswith("ACTIVE"):
            direction = payload.split(" ")[-1]
            latency = round((now - state["mqtt_ts"])*1000) if state["mqtt_ts"] else 0
            state.update({"emergency":True,"direction":direction,"start_ts":now,"mqtt_ts":now})
            sio.emit("emergency_on",{"direction":direction,"latency":latency,
                                     "time":datetime.now().strftime("%H:%M:%S")})
        else:
            duration = round(now - state["start_ts"],1) if state["start_ts"] else 0
            latency  = round((now - state["mqtt_ts"])*1000) if state["mqtt_ts"] else 0
            if state["direction"]: save_event(state["direction"],duration,latency)
            state.update({"emergency":False,"direction":None,"start_ts":None,"mqtt_ts":now})
            sio.emit("emergency_off",{"duration":duration,"time":datetime.now().strftime("%H:%M:%S")})
            sio.emit("stats_update", get_stats())
    elif topic == "traffic/state":
        state["phase"] = payload
        sio.emit("phase_update",{"phase":payload})
    elif topic == "traffic/status":
        sio.emit("log",{"msg":payload,"type":"info"})

def mqtt_thread():
    global mqtt_publisher
    client = mqtt_client.Client()
    client.on_message = on_message
    client.connect(MQTT_IP, MQTT_PORT)
    client.subscribe([("traffic/emergency",0),("traffic/state",0),("traffic/status",0)])
    mqtt_publisher = client
    client.loop_forever()

@app.route('/override/<cmd>')
def override(cmd):
    if mqtt_publisher:
        mqtt_publisher.publish("traffic/override", cmd)
        sio.emit("log",{"msg":f"Override: {cmd}","type":"warn"})
    return jsonify({"ok":True})

@app.route('/stats')
def stats():
    return jsonify(get_stats())

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>ETLP Control Centre</title>
<link href="https://fonts.googleapis.com/css2?family=Syne+Mono&family=Syne:wght@400;600;800&display=swap" rel="stylesheet"/>
<script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
<style>
:root{--bg:#06080f;--bg2:#0c1020;--bg3:#111828;--grn:#00e676;--red:#ff1744;--amb:#ffab00;--blu:#2979ff;--cyan:#00e5ff;--txt:#b0bec5;--muted:#37474f;--bdr:#1c2a3a;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:'Syne',sans-serif;font-size:14px;min-height:100vh;overflow-x:hidden;}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.03) 2px,rgba(0,0,0,0.03) 4px);pointer-events:none;z-index:999;}
header{padding:16px 28px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;background:var(--bg2);position:sticky;top:0;z-index:100;}
.logo{font-family:'Syne Mono',monospace;font-size:13px;color:var(--grn);letter-spacing:3px;}
.header-right{display:flex;align-items:center;gap:20px;}
.clock{font-family:'Syne Mono',monospace;font-size:12px;color:var(--muted);}
.conn-dot{width:8px;height:8px;border-radius:50%;background:var(--grn);box-shadow:0 0 8px var(--grn);animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.alert-bar{margin:16px 20px 0;padding:14px 20px;border-radius:4px;border:1px solid var(--bdr);background:var(--bg3);display:flex;align-items:center;gap:14px;transition:all 0.4s;}
.alert-bar.active{border-color:var(--red);background:rgba(255,23,68,0.08);animation:alertpulse 1s infinite;}
@keyframes alertpulse{0%,100%{box-shadow:0 0 0 0 rgba(255,23,68,0)}50%{box-shadow:0 0 0 6px rgba(255,23,68,0.15)}}
.alert-icon{font-size:22px;}
.alert-label{font-family:'Syne Mono',monospace;font-size:10px;color:var(--muted);letter-spacing:2px;margin-bottom:2px;}
.alert-msg{font-size:16px;font-weight:800;color:var(--grn);transition:color 0.3s;}
.alert-msg.emergency{color:var(--red);}
.alert-latency{font-family:'Syne Mono',monospace;font-size:11px;color:var(--muted);}
.grid{display:grid;grid-template-columns:1fr 340px;gap:16px;padding:16px 20px;max-width:1400px;margin:0 auto;}
.panel{background:var(--bg2);border:1px solid var(--bdr);border-radius:4px;overflow:hidden;}
.panel-header{padding:10px 16px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;}
.panel-title{font-family:'Syne Mono',monospace;font-size:10px;letter-spacing:3px;color:var(--muted);text-transform:uppercase;}
.panel-body{padding:16px;}
.intersection-wrap{display:flex;justify-content:center;align-items:center;padding:24px;}
.intersection{display:grid;grid-template-columns:100px 60px 100px;grid-template-rows:100px 60px 100px;}
.center-box{background:#111828;display:flex;align-items:center;justify-content:center;}
.center-mark{width:8px;height:8px;border-radius:50%;background:var(--muted);opacity:0.3;}
.tl-slot{display:flex;align-items:center;justify-content:center;background:#111828;}
.tl-unit{background:var(--bg3);border:1px solid var(--bdr);border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;align-items:center;gap:6px;min-width:68px;transition:border-color 0.3s,box-shadow 0.3s;}
.tl-unit.emergency-active{border-color:var(--grn);box-shadow:0 0 20px rgba(0,230,118,0.25);}
.tl-name{font-family:'Syne Mono',monospace;font-size:8px;color:var(--muted);letter-spacing:2px;}
.tl-lights{display:flex;flex-direction:column;gap:5px;}
.tl-light{width:16px;height:16px;border-radius:50%;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);transition:all 0.25s;}
.tl-light.on-red{background:var(--red);box-shadow:0 0 10px rgba(255,23,68,0.8);border-color:transparent;}
.tl-light.on-yellow{background:var(--amb);box-shadow:0 0 10px rgba(255,171,0,0.8);border-color:transparent;}
.tl-light.on-green{background:var(--grn);box-shadow:0 0 10px rgba(0,230,118,0.8);border-color:transparent;}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;}
.stat-card{background:var(--bg3);border:1px solid var(--bdr);border-radius:4px;padding:12px 14px;text-align:center;}
.stat-val{font-family:'Syne Mono',monospace;font-size:24px;font-weight:800;color:var(--grn);line-height:1;margin-bottom:4px;}
.stat-val.red{color:var(--red);}.stat-val.blu{color:var(--cyan);}
.stat-label{font-family:'Syne Mono',monospace;font-size:8px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;}
.dir-bars{display:flex;flex-direction:column;gap:6px;}
.dir-row{display:flex;align-items:center;gap:8px;font-family:'Syne Mono',monospace;font-size:10px;}
.dir-name{width:48px;color:var(--muted);}
.dir-bar-wrap{flex:1;height:6px;background:var(--bdr);border-radius:3px;overflow:hidden;}
.dir-bar{height:100%;background:var(--grn);border-radius:3px;transition:width 0.5s;}
.dir-count{width:20px;text-align:right;color:var(--txt);}
.override-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.override-btn{padding:10px 8px;border:1px solid var(--bdr);background:var(--bg3);color:var(--txt);font-family:'Syne Mono',monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;border-radius:4px;cursor:pointer;transition:all 0.2s;}
.override-btn:hover{border-color:var(--cyan);color:var(--cyan);background:rgba(0,229,255,0.05);}
.override-btn.allred{grid-column:span 2;border-color:var(--red);color:var(--red);background:rgba(255,23,68,0.06);}
.override-btn.allred:hover{background:rgba(255,23,68,0.12);}
.override-btn.resume{grid-column:span 2;border-color:var(--grn);color:var(--grn);}
.log-wrap{height:220px;overflow-y:auto;display:flex;flex-direction:column;gap:4px;scrollbar-width:thin;scrollbar-color:var(--bdr) transparent;}
.log-entry{font-family:'Syne Mono',monospace;font-size:10px;padding:5px 8px;border-left:2px solid var(--bdr);color:var(--muted);line-height:1.4;}
.log-entry.emergency{border-color:var(--red);color:var(--red);}
.log-entry.clear{border-color:var(--grn);color:var(--grn);}
.log-entry.warn{border-color:var(--amb);color:var(--amb);}
.log-entry.info{border-color:var(--blu);color:var(--blu);}
.history-table{width:100%;border-collapse:collapse;font-family:'Syne Mono',monospace;font-size:10px;}
.history-table th{color:var(--muted);letter-spacing:2px;font-weight:400;padding:6px 10px;text-align:left;border-bottom:1px solid var(--bdr);}
.history-table td{padding:7px 10px;border-bottom:1px solid rgba(28,42,58,0.5);color:var(--txt);}
.dir-badge{padding:2px 6px;border-radius:2px;font-size:9px;letter-spacing:1px;}
.dir-badge.NORTH,.dir-badge.SOUTH{background:rgba(0,230,118,0.1);color:var(--grn);}
.dir-badge.EAST,.dir-badge.WEST{background:rgba(41,121,255,0.1);color:var(--blu);}
</style>
</head>
<body>

<header>
  <div class="logo">⬡ ETLP Control Centre</div>
  <div class="header-right">
    <div class="clock" id="clock">--:--:--</div>
    <div class="conn-dot"></div>
  </div>
</header>

<div class="alert-bar" id="alert-bar">
  <div class="alert-icon" id="alert-icon">🟢</div>
  <div style="flex:1;">
    <div class="alert-label">SYSTEM STATUS</div>
    <div class="alert-msg" id="alert-msg">All clear — Normal cycle running</div>
  </div>
  <div class="alert-latency" id="alert-latency"></div>
</div>

<div class="grid">
  <div style="display:flex;flex-direction:column;gap:16px;">

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">// Live Intersection</span>
        <span class="panel-title" id="phase-label" style="color:var(--grn)">NS_GREEN</span>
      </div>
      <div class="intersection-wrap">
        <div class="intersection">
          <div class="tl-slot"></div>
          <div class="tl-slot">
            <div class="tl-unit" id="tl-north">
              <div class="tl-name">NORTH</div>
              <div class="tl-lights">
                <div class="tl-light on-red" id="n-r"></div>
                <div class="tl-light" id="n-y"></div>
                <div class="tl-light" id="n-g"></div>
              </div>
            </div>
          </div>
          <div class="tl-slot"></div>
          <div class="tl-slot">
            <div class="tl-unit" id="tl-west">
              <div class="tl-name">WEST</div>
              <div class="tl-lights">
                <div class="tl-light on-red" id="w-r"></div>
                <div class="tl-light" id="w-y"></div>
                <div class="tl-light" id="w-g"></div>
              </div>
            </div>
          </div>
          <div class="center-box"><div class="center-mark"></div></div>
          <div class="tl-slot">
            <div class="tl-unit" id="tl-east">
              <div class="tl-name">EAST</div>
              <div class="tl-lights">
                <div class="tl-light on-red" id="e-r"></div>
                <div class="tl-light" id="e-y"></div>
                <div class="tl-light" id="e-g"></div>
              </div>
            </div>
          </div>
          <div class="tl-slot"></div>
          <div class="tl-slot">
            <div class="tl-unit" id="tl-south">
              <div class="tl-name">SOUTH</div>
              <div class="tl-lights">
                <div class="tl-light on-red" id="s-r"></div>
                <div class="tl-light" id="s-y"></div>
                <div class="tl-light" id="s-g"></div>
              </div>
            </div>
          </div>
          <div class="tl-slot"></div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">// Statistics</span></div>
      <div class="panel-body">
        <div class="stat-row">
          <div class="stat-card"><div class="stat-val" id="stat-total">0</div><div class="stat-label">Total Events</div></div>
          <div class="stat-card"><div class="stat-val blu" id="stat-latency">—</div><div class="stat-label">Avg Latency ms</div></div>
          <div class="stat-card"><div class="stat-val red" id="stat-duration">—</div><div class="stat-label">Avg Duration s</div></div>
        </div>
        <div class="dir-bars">
          <div class="dir-row"><div class="dir-name">NORTH</div><div class="dir-bar-wrap"><div class="dir-bar" id="bar-north" style="width:0%"></div></div><div class="dir-count" id="cnt-north">0</div></div>
          <div class="dir-row"><div class="dir-name">EAST</div><div class="dir-bar-wrap"><div class="dir-bar" id="bar-east" style="width:0%"></div></div><div class="dir-count" id="cnt-east">0</div></div>
          <div class="dir-row"><div class="dir-name">SOUTH</div><div class="dir-bar-wrap"><div class="dir-bar" id="bar-south" style="width:0%"></div></div><div class="dir-count" id="cnt-south">0</div></div>
          <div class="dir-row"><div class="dir-name">WEST</div><div class="dir-bar-wrap"><div class="dir-bar" id="bar-west" style="width:0%"></div></div><div class="dir-count" id="cnt-west">0</div></div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><span class="panel-title">// Emergency History</span></div>
      <div class="panel-body" style="padding:0;">
        <table class="history-table">
          <thead><tr><th>TIME</th><th>DIRECTION</th><th>DURATION</th><th>LATENCY</th></tr></thead>
          <tbody id="history-body"><tr><td colspan="4" style="color:var(--muted);text-align:center;padding:20px;">No events yet</td></tr></tbody>
        </table>
      </div>
    </div>

  </div>

  <div style="display:flex;flex-direction:column;gap:16px;">

    <div class="panel">
      <div class="panel-header"><span class="panel-title">// Manual Override</span></div>
      <div class="panel-body">
        <div class="override-grid">
          <button class="override-btn" onclick="override('NORTH')">🔼 North Green</button>
          <button class="override-btn" onclick="override('SOUTH')">🔽 South Green</button>
          <button class="override-btn" onclick="override('EAST')">▶ East Green</button>
          <button class="override-btn" onclick="override('WEST')">◀ West Green</button>
          <button class="override-btn allred" onclick="override('ALLRED')">⬛ Force All Red</button>
          <button class="override-btn resume" onclick="override('RESUME')">▶▶ Resume Normal</button>
        </div>
        <p style="font-size:10px;color:var(--muted);margin-top:10px;font-family:'Syne Mono',monospace;line-height:1.6;">Commands publish to traffic/override via MQTT.</p>
      </div>
    </div>

    <div class="panel" style="flex:1;">
      <div class="panel-header">
        <span class="panel-title">// Live Log</span>
        <button onclick="clearLog()" style="font-family:'Syne Mono',monospace;font-size:9px;color:var(--muted);background:none;border:none;cursor:pointer;letter-spacing:1px;">CLEAR</button>
      </div>
      <div class="panel-body">
        <div class="log-wrap" id="log"></div>
      </div>
    </div>

  </div>
</div>

<script>
const socket = io();
setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleTimeString('en-GB');},1000);
socket.on('connect',()=>{addLog('Dashboard connected','info');loadStats();});
socket.on('emergency_on',(d)=>{
  setEmergency(d.direction);
  document.getElementById('alert-bar').classList.add('active');
  document.getElementById('alert-icon').textContent='🚨';
  document.getElementById('alert-msg').textContent='🚨 EMERGENCY — '+d.direction;
  document.getElementById('alert-msg').classList.add('emergency');
  document.getElementById('alert-latency').textContent=d.latency+'ms latency';
  addLog('EMERGENCY from '+d.direction+' ['+d.time+']','emergency');
});
socket.on('emergency_off',(d)=>{
  setNormal();
  document.getElementById('alert-bar').classList.remove('active');
  document.getElementById('alert-icon').textContent='🟢';
  document.getElementById('alert-msg').textContent='All clear — Normal cycle running';
  document.getElementById('alert-msg').classList.remove('emergency');
  document.getElementById('alert-latency').textContent='Duration: '+d.duration+'s';
  addLog('Cleared — duration '+d.duration+'s ['+d.time+']','clear');
});
socket.on('phase_update',(d)=>{document.getElementById('phase-label').textContent=d.phase;updatePhase(d.phase);});
socket.on('stats_update',(s)=>applyStats(s));
socket.on('log',(d)=>addLog(d.msg,d.type||'info'));
const dirs=['n','e','s','w'];
const dmap={north:'n',east:'e',south:'s',west:'w'};
const tlmap={n:'tl-north',e:'tl-east',s:'tl-south',w:'tl-west'};
function clearLights(){dirs.forEach(d=>{['r','y','g'].forEach(c=>{document.getElementById(d+'-'+c).className='tl-light';});document.getElementById(tlmap[d]).classList.remove('emergency-active');});}
function setLight(d,c){const cls=c==='r'?'on-red':c==='y'?'on-yellow':'on-green';document.getElementById(d+'-'+c).className='tl-light '+cls;}
function setAllRed(){clearLights();dirs.forEach(d=>setLight(d,'r'));}
function setEmergency(direction){setAllRed();const d=dmap[direction.toLowerCase()];if(!d)return;document.getElementById(d+'-r').className='tl-light';setLight(d,'g');document.getElementById(tlmap[d]).classList.add('emergency-active');}
function setNormal(){clearLights();dirs.forEach(d=>setLight(d,'r'));}
function updatePhase(p){clearLights();if(p==='NS_GREEN'){setLight('n','g');setLight('s','g');setLight('e','r');setLight('w','r');}else if(p==='NS_YELLOW'){setLight('n','y');setLight('s','y');setLight('e','r');setLight('w','r');}else if(p==='EW_GREEN'){setLight('e','g');setLight('w','g');setLight('n','r');setLight('s','r');}else if(p==='EW_YELLOW'){setLight('e','y');setLight('w','y');setLight('n','r');setLight('s','r');}else{setAllRed();}}
function loadStats(){fetch('/stats').then(r=>r.json()).then(applyStats);}
function applyStats(s){
  document.getElementById('stat-total').textContent=s.total;
  document.getElementById('stat-latency').textContent=s.avg_latency||'—';
  document.getElementById('stat-duration').textContent=s.avg_duration||'—';
  const max=Math.max(...(s.by_direction.map(d=>d[1])),1);
  const dm={NORTH:'north',EAST:'east',SOUTH:'south',WEST:'west'};
  ['north','east','south','west'].forEach(d=>{document.getElementById('bar-'+d).style.width='0%';document.getElementById('cnt-'+d).textContent='0';});
  s.by_direction.forEach(([dir,cnt])=>{const k=dm[dir];if(!k)return;document.getElementById('bar-'+k).style.width=(cnt/max*100)+'%';document.getElementById('cnt-'+k).textContent=cnt;});
  const tbody=document.getElementById('history-body');
  if(!s.recent.length)return;
  tbody.innerHTML='';
  s.recent.forEach(([ts,dir,dur,lat])=>{const t=new Date(ts*1000).toLocaleTimeString('en-GB');const row=document.createElement('tr');row.innerHTML=`<td>${t}</td><td><span class="dir-badge ${dir}">${dir}</span></td><td>${dur?dur+'s':'—'}</td><td>${lat?lat+'ms':'—'}</td>`;tbody.appendChild(row);});
}
function addLog(msg,type){const wrap=document.getElementById('log');const el=document.createElement('div');const t=new Date().toLocaleTimeString('en-GB');el.className='log-entry '+(type||'');el.textContent='['+t+'] '+msg;wrap.prepend(el);if(wrap.children.length>60)wrap.lastChild.remove();}
function clearLog(){document.getElementById('log').innerHTML='';}
function override(cmd){fetch('/override/'+cmd).then(()=>addLog('Override: '+cmd,'warn'));}
setNormal();
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

if __name__ == '__main__':
    init_db()
    t = threading.Thread(target=mqtt_thread)
    t.daemon = True
    t.start()
    print("="*50)
    print("  ETLP Dashboard → http://192.168.1.163:5000")
    print("="*50)
    sio.run(app, host='0.0.0.0', port=5000)
