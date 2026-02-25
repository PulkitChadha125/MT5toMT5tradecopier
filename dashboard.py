import os
import sys
import webbrowser
import subprocess
from datetime import datetime, date

import pandas as pd
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    flash,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOL_MAPPING_FILE = os.path.join(BASE_DIR, "symbol_mapping.csv")
ORDERLOG_FILE = os.path.join(BASE_DIR, "orderlog.txt")

app = Flask(__name__)
app.secret_key = "mt5_trade_copier_dashboard"

# Track copier subprocess (mt5_connect.py) started from the dashboard
_copier_process: subprocess.Popen | None = None


def is_copier_running() -> bool:
    global _copier_process
    if _copier_process is None:
        return False
    if _copier_process.poll() is not None:
        # Process has exited; clear handle
        _copier_process = None
        return False
    return True


# ----------------------------- Helpers: Watchlist ----------------------------- #

def load_symbol_mapping_df() -> pd.DataFrame:
    if not os.path.exists(SYMBOL_MAPPING_FILE):
        return pd.DataFrame(columns=["master_symbol", "slave_symbol", "slave_lot"])
    try:
        df = pd.read_csv(SYMBOL_MAPPING_FILE)
        # Ensure expected columns exist
        for col in ["master_symbol", "slave_symbol", "slave_lot"]:
            if col not in df.columns:
                df[col] = "" if col != "slave_lot" else 1.0
        return df
    except Exception as e:
        flash(f"Failed to read symbol_mapping.csv: {e}", "danger")
        return pd.DataFrame(columns=["master_symbol", "slave_symbol", "slave_lot"])


def save_symbol_mapping_df(df: pd.DataFrame) -> None:
    try:
        df.to_csv(SYMBOL_MAPPING_FILE, index=False)
    except Exception as e:
        flash(f"Failed to save symbol_mapping.csv: {e}", "danger")


# ------------------------------ Helpers: Logs -------------------------------- #

def parse_orderlog_line(line: str):
    line = line.strip()
    if not line:
        return None
    parts = [p.strip() for p in line.split("|")]
    try:
        ts_str = parts[0]
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = None

    latency_ms = None
    for p in parts:
        if "LATENCY_MS=" in p:
            try:
                latency_ms = float(p.split("LATENCY_MS=")[-1])
            except ValueError:
                latency_ms = None
            break

    return {
        "timestamp": ts,
        "timestamp_str": parts[0],
        "raw": line,
        "latency_ms": latency_ms,
    }


def load_orderlogs():
    if not os.path.exists(ORDERLOG_FILE):
        return []
    rows = []
    with open(ORDERLOG_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            parsed = parse_orderlog_line(line)
            if parsed is None:
                continue
            parsed["id"] = idx  # line index used for delete
            rows.append(parsed)
    return rows


def filter_logs(logs, filter_type, start_date_str=None, end_date_str=None):
    if filter_type == "all":
        return logs

    if filter_type == "today":
        today = date.today()
        return [
            log
            for log in logs
            if log["timestamp"] is not None and log["timestamp"].date() == today
        ]

    if filter_type == "custom":
        try:
            start = (
                datetime.strptime(start_date_str, "%Y-%m-%d").date()
                if start_date_str
                else None
            )
            end = (
                datetime.strptime(end_date_str, "%Y-%m-%d").date()
                if end_date_str
                else None
            )
        except Exception:
            return logs

        def in_range(d: date):
            if start and d < start:
                return False
            if end and d > end:
                return False
            return True

        return [
            log
            for log in logs
            if log["timestamp"] is not None and in_range(log["timestamp"].date())
        ]

    return logs


# --------------------------------- Routes ----------------------------------- #


@app.route("/", methods=["GET"])
def index():
    active_tab = request.args.get("tab", "watchlist")

    # Watchlist data + search
    search_query = request.args.get("search", "").strip()
    mapping_df = load_symbol_mapping_df()
    filtered_mapping_df = mapping_df
    if search_query and not mapping_df.empty:
        mask = (
            mapping_df["master_symbol"].astype(str).str.contains(search_query, case=False, na=False)
            | mapping_df["slave_symbol"].astype(str).str.contains(search_query, case=False, na=False)
        )
        filtered_mapping_df = mapping_df[mask]

    # Orderlogs data and filters
    filter_type = request.args.get("filter", "today")
    start_date_str = request.args.get("start_date", "")
    end_date_str = request.args.get("end_date", "")

    logs = load_orderlogs()
    filtered_logs = filter_logs(logs, filter_type, start_date_str, end_date_str)

    return render_template(
        "dashboard.html",
        copier_running=is_copier_running(),
        active_tab=active_tab,
        mapping=filtered_mapping_df.to_dict(orient="records"),
        search=search_query,
        logs=filtered_logs,
        filter_type=filter_type,
        start_date=start_date_str,
        end_date=end_date_str,
    )


# ------------------------------ Watchlist CRUD ------------------------------ #


@app.post("/watchlist/add")
def watchlist_add():
    master_symbol = request.form.get("master_symbol", "").strip()
    slave_symbol = request.form.get("slave_symbol", "").strip()
    slave_lot = request.form.get("slave_lot", "").strip() or "1.0"

    if not master_symbol or not slave_symbol:
        flash("Master and slave symbols are required.", "warning")
        return redirect(url_for("index", tab="watchlist"))

    try:
        lot = float(slave_lot)
    except ValueError:
        flash("Slave lot must be a number.", "warning")
        return redirect(url_for("index", tab="watchlist"))

    df = load_symbol_mapping_df()
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [
                    {
                        "master_symbol": master_symbol,
                        "slave_symbol": slave_symbol,
                        "slave_lot": lot,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    save_symbol_mapping_df(df)
    flash("Symbol mapping added.", "success")
    return redirect(url_for("index", tab="watchlist"))


@app.post("/watchlist/edit/<int:row_index>")
def watchlist_edit(row_index: int):
    df = load_symbol_mapping_df()
    if row_index < 0 or row_index >= len(df):
        flash("Invalid row selected.", "danger")
        return redirect(url_for("index", tab="watchlist"))

    master_symbol = request.form.get("master_symbol", "").strip()
    slave_symbol = request.form.get("slave_symbol", "").strip()
    slave_lot = request.form.get("slave_lot", "").strip() or "1.0"

    if not master_symbol or not slave_symbol:
        flash("Master and slave symbols are required.", "warning")
        return redirect(url_for("index", tab="watchlist"))

    try:
        lot = float(slave_lot)
    except ValueError:
        flash("Slave lot must be a number.", "warning")
        return redirect(url_for("index", tab="watchlist"))

    df.iloc[row_index] = {
        "master_symbol": master_symbol,
        "slave_symbol": slave_symbol,
        "slave_lot": lot,
    }
    save_symbol_mapping_df(df)
    flash("Symbol mapping updated.", "success")
    return redirect(url_for("index", tab="watchlist"))


@app.post("/watchlist/delete/<int:row_index>")
def watchlist_delete(row_index: int):
    df = load_symbol_mapping_df()
    if 0 <= row_index < len(df):
        df = df.drop(df.index[row_index]).reset_index(drop=True)
        save_symbol_mapping_df(df)
        flash("Symbol mapping deleted.", "success")
    else:
        flash("Invalid row selected.", "danger")
    return redirect(url_for("index", tab="watchlist"))


@app.post("/watchlist/delete_all")
def watchlist_delete_all():
    df = pd.DataFrame(columns=["master_symbol", "slave_symbol", "slave_lot"])
    save_symbol_mapping_df(df)
    flash("All symbol mappings deleted.", "success")
    return redirect(url_for("index", tab="watchlist"))


@app.route("/watchlist/export", methods=["GET"])
def watchlist_export():
    if not os.path.exists(SYMBOL_MAPPING_FILE):
        flash("No symbol_mapping.csv to export.", "warning")
        return redirect(url_for("index", tab="watchlist"))
    return send_file(
        SYMBOL_MAPPING_FILE,
        as_attachment=True,
        download_name="symbol_mapping_export.csv",
    )


@app.post("/watchlist/import")
def watchlist_import():
    file = request.files.get("file")
    if not file:
        flash("No file selected.", "warning")
        return redirect(url_for("index", tab="watchlist"))
    try:
        df = pd.read_csv(file)
        if not all(c in df.columns for c in ["master_symbol", "slave_symbol", "slave_lot"]):
            flash("CSV must contain master_symbol, slave_symbol, slave_lot.", "danger")
            return redirect(url_for("index", tab="watchlist"))
        save_symbol_mapping_df(df)
        flash("Symbol mappings imported (existing settings overwritten).", "success")
    except Exception as e:
        flash(f"Failed to import CSV: {e}", "danger")
    return redirect(url_for("index", tab="watchlist"))


# ------------------------------ Orderlogs ops ------------------------------- #


@app.post("/orderlogs/delete")
def orderlogs_delete():
    selected = request.form.getlist("selected_ids")
    if not selected:
        flash("No logs selected for deletion.", "warning")
        return redirect(url_for("index", tab="orderlogs"))

    if not os.path.exists(ORDERLOG_FILE):
        flash("orderlog.txt not found.", "danger")
        return redirect(url_for("index", tab="orderlogs"))

    try:
        selected_ids = {int(x) for x in selected}
    except ValueError:
        flash("Invalid selection.", "danger")
        return redirect(url_for("index", tab="orderlogs"))

    lines = []
    with open(ORDERLOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    remaining = [
        line for idx, line in enumerate(lines) if idx not in selected_ids
    ]
    with open(ORDERLOG_FILE, "w", encoding="utf-8") as f:
        f.writelines(remaining)

    flash(f"Deleted {len(selected_ids)} log(s).", "success")
    return redirect(url_for("index", tab="orderlogs"))


@app.post("/orderlogs/delete_all")
def orderlogs_delete_all():
    if os.path.exists(ORDERLOG_FILE):
        open(ORDERLOG_FILE, "w", encoding="utf-8").close()
        flash("All logs deleted.", "success")
    else:
        flash("orderlog.txt not found.", "danger")
    return redirect(url_for("index", tab="orderlogs"))


# ------------------------------ Copier control ------------------------------ #


@app.post("/copier/start")
def copier_start():
    global _copier_process
    if is_copier_running():
        flash("Copier is already running.", "info")
        return redirect(url_for("index"))

    try:
        cmd = [sys.executable, os.path.join(BASE_DIR, "mt5_connect.py")]
        _copier_process = subprocess.Popen(cmd, cwd=BASE_DIR)
        flash("Copier started.", "success")
    except Exception as e:
        flash(f"Failed to start copier: {e}", "danger")
    return redirect(url_for("index"))


@app.post("/copier/stop")
def copier_stop():
    global _copier_process
    if not is_copier_running():
        flash("Copier is not running.", "info")
        return redirect(url_for("index"))

    try:
        _copier_process.terminate()
        _copier_process.wait(timeout=5)
        flash("Copier stopped.", "success")
    except Exception as e:
        flash(f"Failed to stop copier: {e}", "danger")
    finally:
        _copier_process = None
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5000"))
    url = f"http://127.0.0.1:{port}/"
    # Try to open the default browser automatically when the server starts.
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="0.0.0.0", port=port, debug=True)

