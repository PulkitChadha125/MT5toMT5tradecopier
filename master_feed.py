"""
Master account feed for MQL5 EA (backup / low-latency path).

- Connects to MASTER account only and runs on your server.
- Continuously fetches positions from master and writes state to a file
  (and optionally serves the same over HTTP on localhost).
- Your MQL5 EA on the SLAVE terminal reads this file (or HTTP) and places
  trades immediately—no account switching in Python, minimal latency.

Output format: JSON that MQL5 can parse (or use the HTTP endpoint with WebRequest).
File path is configurable so the EA can read from MT5 Common\\Files if needed.
"""

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

import MetaTrader5 as mt5
import pandas as pd

# -----------------------------------------------------------------------------
# Config (same files as main copier; only master credentials used here)
# -----------------------------------------------------------------------------
CREDENTIALS_FILE = "credentials.csv"
SYMBOL_MAPPING_FILE = "symbol_mapping.csv"

# Where to write state so the EA can read it.
# Use a path the EA can open: e.g. MT5 Common\\Files.
# In MQL5: FileOpen("master_state.json", FILE_READ|FILE_TXT|FILE_COMMON) reads from Common\\Files.
# Default: same folder as this script. Set OUTPUT_DIR or set MT5_COMMON_FILES to a path like:
#   C:\\Users\\YourName\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files
OUTPUT_DIR = os.environ.get("MT5_COPIER_OUTPUT_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_FILENAME = "master_state.json"

# How often to poll master positions (seconds). Lower = faster updates, more CPU.
POLL_INTERVAL = 0.2

# Optional HTTP server so EA can use WebRequest instead of file (add URL in MT5 Tools -> Options -> Expert Advisors -> "Allow WebRequest for listed URL").
HTTP_PORT = int(os.environ.get("MT5_COPIER_HTTP_PORT", "0"))  # 0 = disabled. Set e.g. 8765 to enable.

# -----------------------------------------------------------------------------
# Load credentials (master only)
# -----------------------------------------------------------------------------
def load_master_credentials():
    try:
        df = pd.read_csv(CREDENTIALS_FILE)
        if "Title" not in df.columns or "Value" not in df.columns:
            print(f"❌ {CREDENTIALS_FILE} must have 'Title' and 'Value' columns.")
            return None
        cred = df.set_index("Title")["Value"].to_dict()
        login = int(cred.get("master_login", 0))
        password = str(cred.get("master_password", "")).strip()
        server = str(cred.get("master_server", "")).strip()
        if not all([login, password, server]):
            print("❌ Missing master_login, master_password, or master_server in credentials.")
            return None
        return {"login": login, "password": password, "server": server}
    except Exception as e:
        print(f"❌ Error reading {CREDENTIALS_FILE}: {e}")
        return None


def load_symbol_mapping():
    try:
        df = pd.read_csv(SYMBOL_MAPPING_FILE)
        if not all(c in df.columns for c in ["master_symbol", "slave_symbol", "slave_lot"]):
            print(f"❌ {SYMBOL_MAPPING_FILE} must have master_symbol, slave_symbol, slave_lot.")
            return []
        return [
            {
                "master_symbol": row["master_symbol"],
                "slave_symbol": row["slave_symbol"],
                "slave_lot": float(row["slave_lot"]),
            }
            for _, row in df.iterrows()
        ]
    except Exception as e:
        print(f"❌ Error reading {SYMBOL_MAPPING_FILE}: {e}")
        return []


# -----------------------------------------------------------------------------
# Build state dict from current master positions (for JSON / HTTP)
# -----------------------------------------------------------------------------
def positions_to_state(positions):
    out = []
    for p in positions or []:
        out.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": int(p.type),
            "volume": round(p.volume, 2),
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "time": int(p.time) if hasattr(p, "time") else 0,
            "comment": getattr(p, "comment", "") or "",
        })
    return out


def build_state(positions, symbol_mapping):
    return {
        "last_updated": time.time(),
        "symbol_mapping": symbol_mapping,
        "positions": positions_to_state(positions),
    }


# -----------------------------------------------------------------------------
# File writer (fast: only write when state changed)
# -----------------------------------------------------------------------------
_last_state_json = None


def write_state_if_changed(state):
    global _last_state_json
    js = json.dumps(state, separators=(",", ":"))
    if js == _last_state_json:
        return
    _last_state_json = js
    path = os.path.join(OUTPUT_DIR, STATE_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(js)
    except Exception as e:
        print(f"⚠️ Failed to write {path}: {e}")


# -----------------------------------------------------------------------------
# Optional HTTP server (serves same JSON for EA WebRequest)
# -----------------------------------------------------------------------------
_state_for_http = None


def set_state_for_http(state):
    global _state_for_http
    _state_for_http = state


def get_state_for_http():
    return _state_for_http


class StateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.strip("/") in ("", "state", "master_state.json"):
            state = get_state_for_http()
            body = json.dumps(state, separators=(",", ":")).encode("utf-8") if state else b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # quiet


def run_http_server(port):
    server = HTTPServer(("127.0.0.1", port), StateHandler)
    server.serve_forever()


# -----------------------------------------------------------------------------
# Main loop: connect to master, poll positions, write state
# -----------------------------------------------------------------------------
def main():
    cred = load_master_credentials()
    if not cred:
        return
    symbol_mapping = load_symbol_mapping()
    if not symbol_mapping:
        print("⚠️ No symbol mapping; EA will need its own mapping.")

    if not mt5.initialize():
        print(f"❌ MT5 initialize failed: {mt5.last_error()}")
        return
    if not mt5.login(cred["login"], cred["password"], cred["server"]):
        print(f"❌ Login failed: {mt5.last_error()}")
        mt5.shutdown()
        return

    print(f"✅ Connected to master {cred['login']}. Writing state every {POLL_INTERVAL}s to:")
    print(f"   {os.path.join(OUTPUT_DIR, STATE_FILENAME)}")
    if HTTP_PORT > 0:
        t = Thread(target=run_http_server, args=(HTTP_PORT,), daemon=True)
        t.start()
        print(f"   HTTP: http://127.0.0.1:{HTTP_PORT}/state (add this URL in MT5 WebRequest allow list)")
    print("   (Stop with Ctrl+C)")

    try:
        while True:
            positions = mt5.positions_get()
            state = build_state(positions, symbol_mapping)
            write_state_if_changed(state)
            set_state_for_http(state)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
