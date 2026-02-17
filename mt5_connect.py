import MetaTrader5 as mt5
import time
import pandas as pd

# CSV File Paths
CREDENTIALS_FILE = "credentials.csv"
CSV_FILE = "symbol_mapping.csv"

# Credentials (loaded from CSV in load_credentials())
MASTER_LOGIN = None
MASTER_PASSWORD = None
MASTER_SERVER = None
SLAVE_LOGIN = None
SLAVE_PASSWORD = None
SLAVE_SERVER = None

# Track whether MT5 terminal has been initialized.
# We initialize once and then only use mt5.login() to switch accounts,
# instead of doing shutdown/initialize on every switch.
mt5_initialized = False
# Current MT5 login (account id). Skip mt5.login() if already on this account.
_current_login = None


def load_credentials(csv_file=CREDENTIALS_FILE):
    """Load Master and Slave credentials from CSV. Expected columns: Title, Value.
    Required titles: master_login, master_password, master_server, slave_login, slave_password, slave_server
    """
    global MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER
    global SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER
    try:
        df = pd.read_csv(csv_file)
        if "Title" not in df.columns or "Value" not in df.columns:
            print(f"❌ {csv_file} must contain 'Title' and 'Value' columns.")
            return False
        cred = df.set_index("Title")["Value"].to_dict()
        required = [
            "master_login", "master_password", "master_server",
            "slave_login", "slave_password", "slave_server"
        ]
        missing = [k for k in required if k not in cred]
        if missing:
            print(f"❌ {csv_file} missing titles: {', '.join(missing)}")
            return False
        MASTER_LOGIN = int(cred["master_login"])
        MASTER_PASSWORD = str(cred["master_password"]).strip()
        MASTER_SERVER = str(cred["master_server"]).strip()
        SLAVE_LOGIN = int(cred["slave_login"])
        SLAVE_PASSWORD = str(cred["slave_password"]).strip()
        SLAVE_SERVER = str(cred["slave_server"]).strip()
        return True
    except Exception as e:
        print(f"❌ Error reading credentials from {csv_file}: {e}")
        return False

# Store existing trade IDs and mappings
existing_trades = set()
order_mapping = {}  # Master Ticket → Slave Ticket mapping

# Cache for per-symbol successful filling modes to avoid repeated trial-and-error
symbol_filling_cache = {}  # symbol -> mt5.ORDER_FILLING_*


# Function to read CSV and create a symbol mapping dictionary
def load_symbol_mapping(csv_file):
    try:
        df = pd.read_csv(csv_file)
        if not all(col in df.columns for col in ["master_symbol", "slave_symbol", "slave_lot"]):
            print("❌ CSV file must contain 'master_symbol', 'slave_symbol', and 'slave_lot' columns.")
            return {}
        return {row["master_symbol"]: {"slave_symbol": row["slave_symbol"], "slave_lot": float(row["slave_lot"])}
                for _, row in df.iterrows()}
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return {}


# Function to connect to an MT5 account
def connect_mt5(login, password, server):
    """
    Ensure MT5 is initialized once, then log in to the requested account.
    Skips mt5.login() if already on this account to avoid redundant round-trips.
    """
    global mt5_initialized, _current_login

    # Initialize terminal once
    if not mt5_initialized:
        if not mt5.initialize():
            print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
            return False
        mt5_initialized = True

    # Skip login if already on this account
    if _current_login == login:
        return True

    # Switch login to the requested account
    if not mt5.login(login, password, server):
        print(f"❌ Failed to login to account {login}: {mt5.last_error()}")
        return False

    _current_login = login
    print(f"✅ Connected to account {login}")
    return True


def get_supported_filling_mode(symbol: str):
    """
    Return an order filling mode supported by the broker for this symbol.
    This avoids 'Unsupported filling mode' errors.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        # Fallback to RETURN if symbol info is not available
        return mt5.ORDER_FILLING_RETURN

    # In the MT5 Python API, symbol.filling_mode is an int that should be
    # compared against ORDER_FILLING_* constants, not SYMBOL_FILLING_*.
    mode = info.filling_mode
    if mode == mt5.ORDER_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode == mt5.ORDER_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if mode == mt5.ORDER_FILLING_RETURN:
        return mt5.ORDER_FILLING_RETURN

    # Default fallback
    return mt5.ORDER_FILLING_RETURN


# Function to get open trades from Master account
def get_master_trades():
    positions = mt5.positions_get()
    return positions if positions else []


# Function to store existing trades at startup
def record_existing_trades():
    global existing_trades
    positions = get_master_trades()
    existing_trades = {pos.ticket for pos in positions}  # Store only trade IDs
    print(f"ℹ️ Ignoring {len(existing_trades)} existing trades.")


# Run copy logic on Slave (caller must be on Slave account).
def _do_copy_trades(new_trades, symbol_mapping):
    global existing_trades, order_mapping, symbol_filling_cache

    for trade in new_trades:
        master_symbol = trade.symbol
        master_lot = trade.volume  # Get the lot size from the Master trade

        if master_symbol not in symbol_mapping:
            print(f"🔹 Skipping {master_symbol} (not in CSV mapping).")
            continue

        slave_symbol = symbol_mapping[master_symbol]["slave_symbol"]
        slave_multiplier = symbol_mapping[master_symbol]["slave_lot"]  # Get multiplier from CSV

        # Calculate Slave Lot Size = Master Lot * Slave Multiplier
        slave_lot = master_lot * slave_multiplier

        if slave_lot<0.01:
            slave_lot=0.01

        # Ensure lot size is valid
        if slave_lot <= 0:
            print(f"⚠️ Invalid slave lot size ({slave_lot}) for {slave_symbol}. Skipping trade.")
            continue

        trade_type = trade.type  # 0=BUY, 1=SELL
        sl = trade.sl
        tp = trade.tp

        if not mt5.symbol_select(slave_symbol, True):
            print(f"❌ ERROR: Failed to select {slave_symbol} in Slave account.")
            continue

        order_type = mt5.ORDER_TYPE_BUY if trade_type == 0 else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(slave_symbol).bid if trade_type == 0 else mt5.symbol_info_tick(slave_symbol).ask


        if price == None or price>0:
            price = mt5.symbol_info_tick(slave_symbol).bid if trade_type == 0 else mt5.symbol_info_tick(
                slave_symbol).ask

        # print("price: ",price)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": slave_symbol,
            "volume": slave_lot,  # ✅ Now uses calculated lot size
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 120,
            "magic": 123456,
            "comment": "Copied Trade",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # If we already discovered a working filling mode for this symbol,
        # use it directly for speed.
        global symbol_filling_cache
        cached_mode = symbol_filling_cache.get(slave_symbol)

        filling_names = {
            mt5.ORDER_FILLING_FOK: "FOK",
            mt5.ORDER_FILLING_IOC: "IOC",
            mt5.ORDER_FILLING_RETURN: "RETURN",
        }

        def log_success(mode_used, result_obj, latency_ms):
            mode_name = filling_names.get(mode_used, str(mode_used))
            slave_ticket = result_obj.order
            order_mapping[trade.ticket] = slave_ticket  # Store ticket mapping
            print(
                f"✅ Copied {master_symbol} → {slave_symbol} "
                f"(Master Lot: {master_lot}, Slave Lot: {slave_lot}) "
                f"using filling mode {mode_name} "
                f"in {latency_ms:.1f} ms"
            )
            try:
                with open("orderlog.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"MASTER_TICKET={trade.ticket} | SLAVE_TICKET={slave_ticket} | "
                        f"{master_symbol}->{slave_symbol} | "
                        f"MASTER_LOT={master_lot} | SLAVE_LOT={slave_lot} | "
                        f"TYPE={'BUY' if trade_type == 0 else 'SELL'} | "
                        f"PRICE={price} | SL={sl} | TP={tp} | "
                        f"FILLING={mode_name} | "
                        f"LATENCY_MS={latency_ms:.1f}\n"
                    )
            except Exception as log_err:
                print(f"⚠️ Failed to write to orderlog.txt: {log_err}")
            existing_trades.add(trade.ticket)

        # 1) Fast path: try cached mode once
        if cached_mode is not None:
            request["type_filling"] = cached_mode
            start_time = time.time()
            result = mt5.order_send(request)
            latency_ms = (time.time() - start_time) * 1000.0
            mode_name = filling_names.get(cached_mode, str(cached_mode))

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                log_success(cached_mode, result, latency_ms)
                # Cache already correct; nothing else to do
                continue

            # If cached mode became invalid, drop from cache and fall back to full strategy
            if result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030):
                print(
                    f"❌ Cached filling mode {mode_name} is now unsupported for {slave_symbol}. "
                    f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
                )
                symbol_filling_cache.pop(slave_symbol, None)
            else:
                print(
                    f"❌ Failed to copy {master_symbol} → {slave_symbol} with cached filling {mode_name}. "
                    f"(Master Lot: {master_lot}, Slave Lot: {slave_lot}). "
                    f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
                )
                continue  # don't try other modes for non-fill errors

        # 2) Discovery path: try multiple filling modes so we learn which one works.
        # Start with IOC to minimize latency on this server, then try others.
        filling_candidates = []
        for mode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            if mode not in filling_candidates:
                filling_candidates.append(mode)

        last_result = None
        copied = False

        for mode in filling_candidates:
            request["type_filling"] = mode
            start_time = time.time()
            result = mt5.order_send(request)
            latency_ms = (time.time() - start_time) * 1000.0
            last_result = result
            mode_name = filling_names.get(mode, str(mode))

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # Save working mode in cache for next orders of this symbol
                symbol_filling_cache[slave_symbol] = mode
                log_success(mode, result, latency_ms)
                copied = True
                break

            # If filling mode is unsupported, try the next one
            if result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030):
                print(
                    f"❌ Filling mode {mode_name} unsupported for {slave_symbol}. "
                    f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
                )
                continue

            # For any other error, stop trying further modes
            print(
                f"❌ Failed to copy {master_symbol} → {slave_symbol} with filling {mode_name}. "
                f"(Master Lot: {master_lot}, Slave Lot: {slave_lot}). "
                f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
            )
            break

        if not copied and last_result is not None:
            print(
                f"❌ Failed to copy {master_symbol} → {slave_symbol} after trying all filling modes. "
                f"(Master Lot: {master_lot}, Slave Lot: {slave_lot}). "
                f"Last retcode: {last_result.retcode}, "
                f"Comment: {getattr(last_result, 'comment', '')}"
            )


# Function to copy new trades to Slave account (switches to Slave, runs _do_copy_trades, switches back).
def copy_trades(symbol_mapping):
    global existing_trades, order_mapping

    master_trades = get_master_trades()
    new_trades = [trade for trade in master_trades if trade.ticket not in existing_trades]

    if not new_trades:
        return

    print("🔍 New trades detected! Switching to Slave account to copy trades...")
    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return
    _do_copy_trades(new_trades, symbol_mapping)
    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)


# Run SL/TP sync on Slave (caller must be on Slave account).
def _do_sync_modifications(master_trades):
    global order_mapping

    for trade in master_trades:
        if trade.ticket not in order_mapping:
            continue

        slave_ticket = order_mapping[trade.ticket]
        slave_trade = mt5.positions_get(ticket=slave_ticket)
        if not slave_trade:
            continue
        slave_trade = slave_trade[0]
        if slave_trade.sl == trade.sl and slave_trade.tp == trade.tp:
            continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": slave_ticket,
            "sl": trade.sl,
            "tp": trade.tp,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Updated SL/TP for Master Ticket {trade.ticket} → Slave Ticket {slave_ticket}")


# Function to sync SL/TP modifications (switches to Slave, runs _do_sync_modifications, switches back).
def sync_modifications():
    global order_mapping

    master_trades = get_master_trades()
    changes = False
    for trade in master_trades:
        if trade.ticket not in order_mapping:
            continue
        slave_ticket = order_mapping[trade.ticket]
        slave_trade = mt5.positions_get(ticket=slave_ticket)
        if not slave_trade:
            continue
        slave_trade = slave_trade[0]
        if slave_trade.sl != trade.sl or slave_trade.tp != trade.tp:
            changes = True
            break

    if not changes:
        return

    print("🔍 Trade modification detected! Switching to Slave account...")
    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return
    _do_sync_modifications(master_trades)
    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)


# Run close logic on Slave (caller must be on Slave account).
def _do_sync_closures(to_close):
    global order_mapping, symbol_filling_cache

    for master_ticket in to_close:
        slave_ticket = order_mapping[master_ticket]
        slave_trade = mt5.positions_get(ticket=slave_ticket)

        if not slave_trade:
            print(f"⚠️ Slave trade not found for Master Ticket {master_ticket}. Skipping closure.")
            continue

        slave_trade = slave_trade[0]  # Get the first matching position
        symbol = slave_trade.symbol  # Get correct symbol
        volume = slave_trade.volume  # Get correct trade size
        trade_type = slave_trade.type  # Get trade type (BUY/SELL)

        # Ensure the symbol is selected
        mt5.symbol_select(symbol, True)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": slave_ticket,  # Use correct slave position ID
            "symbol": symbol,
            "volume": volume,  # Ensure correct volume
            "type": mt5.ORDER_TYPE_SELL if trade_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,  # Close opposite order
            "price": mt5.symbol_info_tick(symbol).bid if trade_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask,
            "deviation": 35,
            "magic": 123456,
            "comment": "Closed by Copier",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # Reuse the same per-symbol filling cache as for opening trades
        global symbol_filling_cache
        cached_mode = symbol_filling_cache.get(symbol)

        filling_names = {
            mt5.ORDER_FILLING_FOK: "FOK",
            mt5.ORDER_FILLING_IOC: "IOC",
            mt5.ORDER_FILLING_RETURN: "RETURN",
        }

        def log_close_success(mode_used, result_obj, latency_ms):
            mode_name = filling_names.get(mode_used, str(mode_used))
            print(
                f"✅ Closed Slave Ticket {slave_ticket} (Master Ticket {master_ticket}) "
                f"using filling mode {mode_name} "
                f"in {latency_ms:.1f} ms"
            )
            try:
                with open("orderlog.txt", "a", encoding="utf-8") as log_file:
                    log_file.write(
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"CLOSE | MASTER_TICKET={master_ticket} | SLAVE_TICKET={slave_ticket} | "
                        f"SYMBOL={symbol} | VOLUME={volume} | "
                        f"TYPE={'BUY' if trade_type == mt5.ORDER_TYPE_BUY else 'SELL'} | "
                        f"FILLING={mode_name} | "
                        f"LATENCY_MS={latency_ms:.1f}\n"
                    )
            except Exception as log_err:
                print(f"⚠️ Failed to write close to orderlog.txt: {log_err}")
            del order_mapping[master_ticket]  # Remove from tracking

        # 1) Fast path: try cached filling mode if we already know it works
        if cached_mode is not None:
            request["type_filling"] = cached_mode
            start_time = time.time()
            result = mt5.order_send(request)
            latency_ms = (time.time() - start_time) * 1000.0
            mode_name = filling_names.get(cached_mode, str(cached_mode))

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                log_close_success(cached_mode, result, latency_ms)
                continue

            if result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030):
                print(
                    f"❌ Cached filling mode {mode_name} is now unsupported for closing {symbol}. "
                    f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
                )
                symbol_filling_cache.pop(symbol, None)
            else:
                print(
                    f"❌ ERROR: Failed to close Slave Ticket {slave_ticket} with cached filling {mode_name}. "
                    f"Reason: {result.comment}"
                )
                continue

        # 2) Discovery path: try multiple filling modes to close the trade.
        # Start with IOC to minimize latency on this server, then try others.
        filling_candidates = []
        for mode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            if mode not in filling_candidates:
                filling_candidates.append(mode)

        last_result = None
        closed = False

        for mode in filling_candidates:
            request["type_filling"] = mode
            start_time = time.time()
            result = mt5.order_send(request)
            latency_ms = (time.time() - start_time) * 1000.0
            last_result = result
            mode_name = filling_names.get(mode, str(mode))

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                symbol_filling_cache[symbol] = mode
                log_close_success(mode, result, latency_ms)
                closed = True
                break

            if result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030):
                print(
                    f"❌ Filling mode {mode_name} unsupported for closing {symbol}. "
                    f"Retcode: {result.retcode}, Comment: {getattr(result, 'comment', '')}"
                )
                continue

            print(
                f"❌ ERROR: Failed to close Slave Ticket {slave_ticket} with filling {mode_name}. "
                f"Reason: {result.comment}"
            )
            break

        if not closed and last_result is not None:
            print(
                f"❌ ERROR: Failed to close Slave Ticket {slave_ticket} after trying all filling modes. "
                f"Last retcode: {last_result.retcode}, Comment: {getattr(last_result, 'comment', '')}"
            )


# Function to close trades in Slave when closed in Master (switches to Slave, runs _do_sync_closures, switches back).
def sync_closures():
    global order_mapping

    master_tickets = {trade.ticket for trade in get_master_trades()}
    to_close = [ticket for ticket in order_mapping if ticket not in master_tickets]

    if not to_close:
        return

    print("🔍 Trade closure detected! Switching to Slave account...")
    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return
    _do_sync_closures(to_close)
    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)


# Main function to run the trade copier
def trade_copier():
    if not load_credentials():
        print("❌ Failed to load credentials. Exiting.")
        return

    symbol_mapping = load_symbol_mapping(CSV_FILE)
    if not symbol_mapping:
        print("❌ No symbol mapping found. Exiting.")
        return

    # Initialize MT5 and validate both accounts.
    # Login to Slave first, then Master so we end up on the Master account.
    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        return
    if not connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER):
        return

    record_existing_trades()

    print("📡 Monitoring for new trades, modifications, and closures...")
    print("💡 Using batched slave switch: one login to slave per loop when there is work.")

    while True:
        master_trades = get_master_trades()
        new_trades = [t for t in master_trades if t.ticket not in existing_trades]
        master_tickets = {t.ticket for t in master_trades}
        to_close = [t for t in order_mapping if t not in master_tickets]

        if new_trades or to_close:
            if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
                print("❌ ERROR: Failed to switch to Slave account.")
            else:
                if new_trades:
                    print("🔍 New trades detected! Copying on Slave...")
                    _do_copy_trades(new_trades, symbol_mapping)
                _do_sync_modifications(master_trades)
                if to_close:
                    print("🔍 Closures detected! Closing on Slave...")
                    _do_sync_closures(to_close)
                connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)

        time.sleep(0.3)


# Run the trade copier
if __name__ == "__main__":
    trade_copier()
