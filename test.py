import MetaTrader5 as mt5

# Slave Account (Destination)
SLAVE_LOGIN = 203188600  # Your Slave account login
SLAVE_PASSWORD = "Srinivasam9$"
SLAVE_SERVER = "Exness-MT5Trial7"

def connect_mt5():
    mt5.shutdown()
    if not mt5.initialize():
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return False
    if not mt5.login(SLAVE_LOGIN, SLAVE_PASSWORD, SLAVE_SERVER):
        print(f"❌ Failed to login to Slave account: {mt5.last_error()}")
        return False
    print(f"✅ Connected to Slave account {SLAVE_LOGIN}")
    return True

# Function to check available symbols
def check_symbols():
    symbols = mt5.symbols_get()
    print(f"📌 Total symbols in Slave account: {len(symbols)}")
    found = False
    for symbol in symbols:
        if "XAUUSD" in symbol.name:  # Adjust search based on your broker's symbol name
            print(f"✅ Found symbol: {symbol.name}")
            found = True
    if not found:
        print("❌ XAUUSDm or similar symbols not found in Slave account.")

# Run the script
if __name__ == "__main__":
    if connect_mt5():
        check_symbols()
