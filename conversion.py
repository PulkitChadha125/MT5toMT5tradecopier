import csv


INPUT_FILE = "watchlist.csv"
OUTPUT_FILE = "watchlist_converted.csv"


def convert_watchlist():
    """
    Read symbols from watchlist.csv and write them to
    watchlist_converted.csv with two columns:
      - master_symbol: original symbol from the file
      - slave_symbol:  left part before '.' + '-STD'

    The input file is a UTF-16 encoded, semicolon-separated text file
    where the first column contains the symbol (header: Symbol).
    """
    rows = []

    try:
        # The exported file is UTF-16 with ';' as separator.
        with open(INPUT_FILE, "r", encoding="utf-16") as f:
            reader = csv.reader(f, delimiter=";")

            # Skip header line (e.g. "Symbol,Bid,Ask,Daily Change")
            next(reader, None)

            for row in reader:
                if not row:
                    continue

                raw_symbol = row[0]
                if not raw_symbol:
                    continue

                master_symbol = raw_symbol.strip().strip('"')
                if not master_symbol:
                    continue

                # Take part before '.', then add '-STD'
                base = master_symbol.split(".")[0]
                slave_symbol = f"{base}-STD"

                rows.append((master_symbol, slave_symbol))

    except FileNotFoundError:
        print(f"Error: Input file not found: {INPUT_FILE}")
        return
    except Exception as e:
        print(f"Error while reading {INPUT_FILE}: {e}")
        return

    if not rows:
        print("ℹ️ No symbols found to convert.")
        return

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.writer(out_f)
            writer.writerow(["master_symbol", "slave_symbol"])
            for master_symbol, slave_symbol in rows:
                writer.writerow([master_symbol, slave_symbol])
    except Exception as e:
        print(f"Error while writing {OUTPUT_FILE}: {e}")
        return

    print(f"Converted {len(rows)} symbols to {OUTPUT_FILE}")


if __name__ == "__main__":
    convert_watchlist()

