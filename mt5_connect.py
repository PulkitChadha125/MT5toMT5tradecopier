import MetaTrader5 as mt5
import time
import pandas as pd

# Master Account (Source)
MASTER_LOGIN = 1610001136
MASTER_PASSWORD = "cd66k^PU"
MASTER_SERVER = "STARTRADERINTL-Demo"

# Slave Account (Destination)
SLAVE_LOGIN = 203188600
SLAVE_PASSWORD = "Srinivasam9$"
SLAVE_SERVER = "Exness-MT5Trial7"

# CSV File Path
CSV_FILE = "symbol_mapping.csv"

# Store existing trade IDs and mappings
existing_trades = set()
order_mapping = {}  # Master Ticket → Slave Ticket mapping


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
    mt5.shutdown()
    if not mt5.initialize():
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return False
    if not mt5.login(login, password, server):
        print(f"❌ Failed to login to account {login}: {mt5.last_error()}")
        return False
    print(f"✅ Connected to account {login}")
    return True


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


# Function to copy new trades to Slave account
# Function to copy new trades to Slave account
def copy_trades(symbol_mapping):
    global existing_trades, order_mapping

    master_trades = get_master_trades()
    new_trades = [trade for trade in master_trades if trade.ticket not in existing_trades]

    if not new_trades:
        return  # No new trades, stay in Master account

    print("🔍 New trades detected! Switching to Slave account to copy trades...")

    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return

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

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": slave_symbol,
            "volume": slave_lot,  # ✅ Now uses calculated lot size
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "Copied Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            slave_ticket = result.order
            order_mapping[trade.ticket] = slave_ticket  # Store ticket mapping
            print(f"✅ Copied {master_symbol} → {slave_symbol} (Master Lot: {master_lot}, Slave Lot: {slave_lot})")
            existing_trades.add(trade.ticket)

    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)  # Switch back to Master



# Function to sync SL/TP modifications
def sync_modifications():
    global order_mapping

    master_trades = get_master_trades()
    changes = False  # Track if modifications were detected

    for trade in master_trades:
        if trade.ticket not in order_mapping:
            continue  # Only update mapped trades

        slave_ticket = order_mapping[trade.ticket]

        slave_trade = mt5.positions_get(ticket=slave_ticket)
        if not slave_trade:
            continue  # Trade not found in Slave, skip

        slave_trade = slave_trade[0]
        if slave_trade.sl != trade.sl or slave_trade.tp != trade.tp:
            changes = True  # Changes detected
            break

    if not changes:
        return  # No changes, stay in Master account

    print("🔍 Trade modification detected! Switching to Slave account...")

    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return

    for trade in master_trades:
        if trade.ticket not in order_mapping:
            continue

        slave_ticket = order_mapping[trade.ticket]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": slave_ticket,
            "sl": trade.sl,
            "tp": trade.tp,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Updated SL/TP for Master Ticket {trade.ticket} → Slave Ticket {slave_ticket}")

    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)  # Switch back to Master


# Function to close trades in Slave when closed in Master
# Function to close trades in Slave when closed in Master
# Function to close trades in Slave when closed in Master
def sync_closures():
    global order_mapping

    master_tickets = {trade.ticket for trade in get_master_trades()}
    to_close = [ticket for ticket in order_mapping if ticket not in master_tickets]

    if not to_close:
        return  # No closures detected, stay in Master account

    print("🔍 Trade closure detected! Switching to Slave account...")

    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return

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
            "deviation": 10,
            "magic": 123456,
            "comment": "Closed by Copier",
        }

        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Closed Slave Ticket {slave_ticket} (corresponding to Master Ticket {master_ticket})")
            del order_mapping[master_ticket]  # Remove from tracking
        else:
            print(f"❌ ERROR: Failed to close Slave Ticket {slave_ticket}. Reason: {result.comment}")

    connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER)  # Switch back to Master




# Main function to run the trade copier
def trade_copier():
    symbol_mapping = load_symbol_mapping(CSV_FILE)
    if not symbol_mapping:
        print("❌ No symbol mapping found. Exiting.")
        return

    if not connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER):
        return
    record_existing_trades()

    print("📡 Monitoring for new trades, modifications, and closures...")

    while True:
        copy_trades(symbol_mapping)
        sync_modifications()
        sync_closures()
        time.sleep(5)


# Run the trade copier
if __name__ == "__main__":
    trade_copier()
