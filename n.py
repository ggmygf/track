import threading
import time
import requests
import datetime
import os  # <--- Added missing import
from flask import Flask, request, jsonify
from markupsafe import escape

app = Flask(__name__)

# === Config ===
TG_BOT   = "https://api.telegram.org/bot8294381858:AAE0W6K3dzgMPfyUTdHLKI-hY2XQLgEi9Ag/sendMessage"
CHAT_ID  = "6303386118"
BYBIT    = "https://api.bybit.com/v5/market/tickers"
LOG_FILE = "trend_linker.log"

# Proxy Setup
PROXIES = {
    "http": "http://isqzkcpt:hn0ol1pcvaob@142.111.67.146:5611",
    "https": "http://isqzkcpt:hn0ol1pcvaob@142.111.67.146:5611"
}

# Task Structure: {tid: {symbol, t1, p1, t2, p2, tag, created_at, failures: []}}
ACTIVE_TASKS = {}      
NEXT_ID = 1
LOCK = threading.Lock()

# === Helpers ===
def file_log(msg):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except:
        pass

def get_price(symbol):
    try:
        r = requests.get(BYBIT, params={'category':'linear', 'symbol':symbol}, timeout=8, proxies=PROXIES)
        if r.ok:
            data = r.json()
            if data.get('retCode') == 0:
                return float(data['result']['list'][0]['lastPrice'])
    except:
        pass
    return None

def tg(text):
    try:
        requests.get(TG_BOT, params={'chat_id':CHAT_ID, 'text':text}, timeout=8, proxies=PROXIES)
    except Exception as e:
        print(f"[tg] Error: {e}")

def clean_num(x):
    return ("{:.6f}".format(x)).rstrip('0').rstrip('.')

# === Monitor Thread ===
def monitor(tid, symbol, t1, p1, t2, p2):
    file_log(f"Started Monitoring: {symbol} ID:{tid}")
    tg(f"▶️ {symbol} task started")
    
    slope = (p2 - p1) / (t2 - t1) if t2 != t1 else 0

    while tid in ACTIVE_TASKS:
        now = int(time.time()*1000)
        price = get_price(symbol)

        # --- Failure Handling ---
        if price is None:
            with LOCK:
                if tid not in ACTIVE_TASKS: break
                task = ACTIVE_TASKS[tid]
                now_sec = time.time()
                task['failures'].append(now_sec)
                
                recent_fails = [t for t in task['failures'] if now_sec - t < 3600]
                task['failures'] = recent_fails
                
                if len(recent_fails) <= 5:
                    tg(f"⚠️⚠️⚠️ {symbol} fail fetch")
            
            time.sleep(10) 
            continue
        
        # --- Calc Diff ---
        expected = slope * (now - t1) + p1
        diff_pct = abs((price - expected)/expected*100) if expected else 100

        # --- Logic & Frequency ---
        if diff_pct <= 0.6:
            tg(f"🚨🚨🚨 {symbol} is ready")
            file_log(f"Triggered & Killed: {symbol} Diff:{diff_pct:.2f}%")
            with LOCK:
                ACTIVE_TASKS.pop(tid, None)
            break

        sleep_sec = 18 
        if diff_pct >= 5:   sleep_sec = 3600
        elif diff_pct >= 3: sleep_sec = 1800
        elif diff_pct >= 2: sleep_sec = 300
        elif diff_pct >= 1: sleep_sec = 60
        elif diff_pct >= 0.7: sleep_sec = 20
        
        time.sleep(sleep_sec)

# === Routes ===
@app.route('/start', methods=['GET'])
def start():
    # If params exist, create task silently
    if request.args.get('symbol') and request.args.get('p1'):
        try:
            symbol = request.args['symbol'].upper()
            t1 = int(request.args['t1'])
            p1 = float(request.args['p1'])
            # Logic handled in JS, but safety check here:
            t2 = int(request.args.get('t2', t1 + 3600000)) 
            p2 = float(request.args.get('p2', p1))
            tag = request.args.get('tag', '') # Get the tag

            global NEXT_ID
            with LOCK:
                tid = NEXT_ID
                NEXT_ID += 1
                created_date = datetime.datetime.now().strftime("%Y-%m-%d")
                ACTIVE_TASKS[tid] = {
                    'symbol':symbol, 't1':t1, 'p1':p1, 't2':t2, 'p2':p2,
                    'tag': tag,
                    'created_at': created_date,
                    'failures': []
                }
            
            threading.Thread(target=monitor, args=(tid,symbol,t1,p1,t2,p2), daemon=True).start()
            print(f"[Server] Task {tid} ({symbol}) started") 
            file_log(f"Added Task: {tid} {symbol} Tag:{tag}")
            
        except Exception as e:
            print(f"[Server] Error adding task: {e}")

    # Render List
    with LOCK:
        tasks = ACTIVE_TASKS.copy()
        file_log(f"List Sync: {len(tasks)} active")

    rows = ""
    for tid, d in tasks.items():
        rows += f"""
        <tr>
            <td>{escape(d['symbol'])}</td>
            <td>{clean_num(d['p1'])}</td>
            <td>{clean_num(d['p2'])}</td>
            <td style="color:#4fc3f7">{d.get('tag','')}</td>
            <td>{d['created_at']}</td>
            <td><button onclick="fetch('/delete/{tid}',{{method:'DELETE'}}).then(()=>location.reload())" 
                style="background:#d9534f;border:none;color:white;padding:8px 16px;border-radius:4px;cursor:pointer;">DELETE</button></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html style="height:100%;margin:0;background:#111;color:#eee;font-family:system-ui,sans-serif">
<head>
    <meta charset="utf-8">
    <title>Tasks</title>
</head>
<body style="height:100%;display:grid;place-items:center;">
<div style="background:#222;padding:30px;border-radius:12px;min-width:700px;">
<h2 style="margin-top:0;text-align:center;color:#4fc3f7">Active Trend Tasks</h2>
<table style="width:100%;border-collapse:collapse;color:#ccc;text-align:left;">
<tr style="background:#333;text-transform:uppercase;font-size:0.85em;color:#999;">
<th style="padding:10px;">Symbol</th>
<th>P1</th>
<th>P2</th>
<th>Tag</th>
<th>Date</th>
<th style="text-align:right;padding-right:10px;">Action</th>
</tr>
{rows or "<tr><td colspan='6' style='text-align:center;padding:30px;color:#555;'>No active tasks</td></tr>"}
</table>
</div>
</body></html>"""
    return html

@app.route('/delete/<int:tid>', methods=['DELETE'])
def delete(tid):
    symbol = "Unknown"
    with LOCK:
        if tid in ACTIVE_TASKS:
            symbol = ACTIVE_TASKS[tid]['symbol']
            ACTIVE_TASKS.pop(tid, None)
            file_log(f"Deleted Task: {tid} {symbol}")
    tg(f"🗑️ Task {symbol} deleted")
    return jsonify(success=True)

if __name__ == '__main__':
    if not os.path.exists(LOG_FILE): # <--- Fixed typo
        with open(LOG_FILE, 'w') as f: f.write("Log started\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
