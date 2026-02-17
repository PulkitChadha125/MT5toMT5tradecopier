# Master feed → MQL5 EA (backup / low-latency)

## Flow

1. **Python (`master_feed.py`)** runs on your server, connected **only to the master** account.
2. It continuously polls master positions and writes **`master_state.json`** (and optionally serves the same over HTTP).
3. Your **MQL5 EA** runs on the **slave** terminal. It reads `master_state.json` (or calls the HTTP URL) on a timer (e.g. every 100–200 ms).
4. When the EA sees a **new** master position (ticket it hasn’t copied yet), it opens the same trade on the slave. When a master position **disappears**, it closes the corresponding slave position.

No account switching in Python; the EA is always on the slave and only reads from your server → minimal latency.

---

## Output format (`master_state.json`)

```json
{
  "last_updated": 1739265432.123,
  "symbol_mapping": [
    {"master_symbol": "EURUSD.c", "slave_symbol": "EURUSD", "slave_lot": 1.0},
    ...
  ],
  "positions": [
    {
      "ticket": 47423251,
      "symbol": "USDJPY.c",
      "type": 1,
      "volume": 0.02,
      "price_open": 153.395,
      "sl": 0,
      "tp": 0,
      "time": 1739265420,
      "comment": ""
    }
  ]
}
```

- **type:** 0 = BUY, 1 = SELL  
- Use **symbol_mapping** to get `slave_symbol` and `slave_lot` from `master_symbol`.  
- **positions** = current open positions on the master. If a ticket disappears in the next read, that position was closed on the master.

---

## Where the EA reads the file

- **Default:** Python writes to the same folder as `master_feed.py`.  
- **MT5 Common folder (recommended):** so the EA can open it with `FILE_COMMON`:
  - Set env var `MT5_COPIER_OUTPUT_DIR` to your MT5 Common path, e.g.  
    `C:\Users\YourName\AppData\Roaming\MetaQuotes\Terminal\Common\Files`
  - Or in Python, set `OUTPUT_DIR` in `master_feed.py` to that path.
- In MQL5, open with:  
  `FileOpen("master_state.json", FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI)`  
  (or without `FILE_COMMON` if you use a path under the terminal).

---

## Optional HTTP (for EA WebRequest)

- In `master_feed.py`, set `HTTP_PORT` (e.g. `8765`) or set env `MT5_COPIER_HTTP_PORT=8765`.
- Python will serve: `http://127.0.0.1:8765/state` with the same JSON.
- In MT5: **Tools → Options → Expert Advisors** → add `http://127.0.0.1:8765` to “Allow WebRequest for listed URL”.
- In the EA, use `WebRequest("GET", "http://127.0.0.1:8765/state", "", "", buf)` and parse the response as JSON.

---

## EA logic (outline)

1. **OnTimer (e.g. 100–200 ms) or OnTick:**
   - Read `master_state.json` (file or HTTP).
   - Parse JSON (use an MQL5 JSON library or simple string parsing for the fields above).

2. **Copy new positions:**
   - Keep a set/map of “master tickets already copied” (e.g. in a file or global array).
   - For each `positions[]` entry:
     - If `ticket` is not in “already copied”, open a trade on the slave:
       - Symbol = slave symbol from `symbol_mapping` for this `position.symbol`.
       - Volume = `position.volume * slave_lot` from mapping.
       - Type = BUY if `type==0`, SELL if `type==1`.
       - Store mapping: master_ticket → slave_ticket (for later close and to avoid re-opening).
     - Add this master ticket to “already copied”.

3. **Close when master closed:**
   - Compare current `positions[]` with the previous read (or with your “already copied” list).
   - If a master ticket was copied before but is no longer in `positions[]`, close the corresponding slave position (using the stored slave_ticket) and remove it from the mapping.

4. **SL/TP sync (optional):**  
   If a position’s `sl` or `tp` in the JSON changed, send a modification for the slave position.

---

## Run the Python feed

```bash
python master_feed.py
```

Or use your existing venv and run it on the server next to the main copier (as a backup path). The main copier (`mt5_connect.py`) and `master_feed.py` cannot both be connected to the same MT5 terminal at the same time from the same machine; run the feed on the machine where the master is logged in (or use a separate terminal/process as needed).
