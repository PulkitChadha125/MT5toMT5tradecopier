import MetaTrader5 as mt5
import time
import pandas as pd

# Master Account (Source)
MASTER_LOGIN = 9094029  # Your Master account login
MASTER_PASSWORD = "Srinivasam9$"
MASTER_SERVER = "STARTRADERINTL-Live"

# Slave Account (Destination)
SLAVE_LOGIN = 203188600  # Your Slave account login
SLAVE_PASSWORD = "Srinivasam9$"
SLAVE_SERVER = "Exness-MT5Trial7"

# CSV File Path
CSV_FILE = "symbol_mapping.csv"

# Store existing trade IDs (to ignore old trades)
existing_trades = set()


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


# Function to copy trades to Slave account only when new trade appears
def copy_trades(symbol_mapping, master_trades):
    global existing_trades

    new_trades = [trade for trade in master_trades if trade.ticket not in existing_trades]

    if not new_trades:
        return  # No new trades, no need to switch accounts

    print("🔍 New trades detected! Switching to Slave account to copy trades...")

    # **Switch to Slave Account only when new trades are found**
    if not connect_mt5(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print("❌ ERROR: Failed to switch to Slave account.")
        return

    for trade in new_trades:
        master_symbol = trade.symbol
        if master_symbol not in symbol_mapping:
            print(f"🔹 Skipping {master_symbol} (not in CSV mapping).")
            continue

        slave_symbol = symbol_mapping[master_symbol]["slave_symbol"]
        slave_lot = symbol_mapping[master_symbol]["slave_lot"]
        trade_type = trade.type  # 0=BUY, 1=SELL
        sl = trade.sl
        tp = trade.tp

        # Ensure the symbol is enabled in Slave account
        if not mt5.symbol_select(slave_symbol, True):
            print(f"❌ ERROR: Failed to select {slave_symbol} in Slave account.")
            continue

        # Place trade in Slave account
        order_type = mt5.ORDER_TYPE_BUY if trade_type == 0 else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(slave_symbol).bid if trade_type == 0 else mt5.symbol_info_tick(slave_symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": slave_symbol,
            "volume": slave_lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 120,
            "magic": 123456,
            "comment": "Copied Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ ERROR: Failed to copy {master_symbol} → {slave_symbol}: {result.comment}")
        else:
            print(f"✅ Copied {master_symbol} → {slave_symbol} with lot size {slave_lot}")
            existing_trades.add(trade.ticket)  # Store trade ID to track new trades

    # **Switch Back to Master Account Immediately**
    print("🔄 Switching back to Master account...")
    if not connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER):
        print("❌ ERROR: Failed to switch back to Master account.")
        return


# Main function to run the trade copier
def trade_copier():
    symbol_mapping = load_symbol_mapping(CSV_FILE)
    if not symbol_mapping:
        print("❌ No symbol mapping found. Exiting.")
        return

    # Connect to Master and store existing trades
    if not connect_mt5(MASTER_LOGIN, MASTER_PASSWORD, MASTER_SERVER):
        return
    record_existing_trades()  # Store existing trades before starting copying

    print("📡 Monitoring for new trades...")

    # Continuous Monitoring for New Trades
    while True:
        master_trades = get_master_trades()
        copy_trades(symbol_mapping, master_trades)  # Copy only when new trade appears
        time.sleep(5)  # Check every 5 seconds


# Run the trade copier
if __name__ == "__main__":
    trade_copier()
