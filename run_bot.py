# run_bot.py

import os
import sys
import json
import time
import subprocess
from datetime import date, datetime
from DataManager import fetch_and_cache_prices
import pandas as pd

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
RUN_LOG_FILE = "run_log.json"
PORTFOLIO_FILE   = "portfolio_summary.json"
TRADE_LOG        = "trades_log.json"
DAILY_SCREEN     = "daily_screen.json"
LAST_SELECT_RUN  = "selectstocks_last_run.txt"
LAST_STOCKTICKERS_RUN = "stocktickers_last_run.txt"
MONITOR_FLAG = "monitor_started.txt"
DEFERRED_SELLS_FILE = "deferred_sells.json"
INITIAL_CASH     = 10_000

# Set the working directory to the folder where run_bot.py is located
os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

# ─── PRE-FETCH HISTORICAL DATA ─────────────────────────────────────────────────
# Load tickers from ftse100_stocks.json
with open("ftse100_stocks.json", "r", encoding="utf-8") as f:
    ftse100 = json.load(f)

UNIVERSE = list({
    f"{stock['code'].rstrip('.').replace('.', '-')}.L"
    for stock in ftse100
    if stock.get("code")
})

# Cache 60 days daily history for all symbols
fetch_and_cache_prices(UNIVERSE, period="60d", interval="1d", force=True, intraday=True) # Force = Ensure Latest values downloaded

# ────────────────────────────────────────────────────────────────────────────────

# The current quater
def current_quarter(dt):
    return (dt.month - 1) // 3 + 1  # 1-based: Jan-Mar = Q1, etc.

# Log each time bot runs
def log_run(run_data):
    """Append a run log entry to run_log.json."""
    if os.path.exists(RUN_LOG_FILE):
        with open(RUN_LOG_FILE) as f:
            logs = json.load(f)
    else:
        logs = []

    logs.append(run_data)

    with open(RUN_LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def init_portfolio():
    """Ensure portfolio_summary.json exists."""
    if not os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump({
                "date":     str(date.today()),
                "cash":     INITIAL_CASH,
                "holdings": {},
                "history":  []
            }, f, indent=2)
        print("Initialized portfolio_summary.json with $10,000 cash.")

def ran_select_today():
    """Has SelectStocks.py already run today?"""
    if not os.path.exists(LAST_SELECT_RUN):
        return False
    return open(LAST_SELECT_RUN).read().strip() == str(date.today())

def mark_select_ran():
    """Mark that SelectStocks.py ran today."""
    with open(LAST_SELECT_RUN, "w") as f:
        f.write(str(date.today()))

def get_todays_sells():
    """Return set of tickers sold or deferred today."""
    today = date.today()
    sells = set()
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG) as f:
            logs = json.load(f)
        for entry in logs:
            if entry["action"] == "SELL":
                try:
                    entry_date = datetime.fromisoformat(entry["date"]).date()
                except ValueError:
                    # Fallback if the date is not ISO format
                    entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                if entry_date == today:
                    sells.add(entry["ticker"])
    return sells

def prune_sold_from_screen(sold_set):
    """Remove sold tickers from daily_screen.json (top_100, to_buy, momentum)."""
    if not sold_set:
        return
    with open(DAILY_SCREEN) as f:
        screen = json.load(f)
    screen["top_100"] = [item for item in screen["top_100"] if item[0] not in sold_set]
    screen["to_buy"]  = [t for t in screen["to_buy"] if t not in sold_set]
    for t in list(screen.get("momentum", {})):
        if t in sold_set:
            del screen["momentum"][t]
    with open(DAILY_SCREEN, "w") as f:
        json.dump(screen, f, indent=2)
    print(f"Pruned sold tickers from screen: {sold_set}")

def run_script(name):
    """Helper to run a python script in subprocess."""
    print(f">>> Running {name}")
    subprocess.run(["python", name], check=True)

def job():
    start_time = datetime.now()
    scripts_run = []
    
    print(f"\n=== Bot run at {datetime.now().isoformat()} ===")
    init_portfolio()

    try:
        # 0) ─── RUN STOCKTICKERS ON QUARTERLY REBALANCE DATES ─────────────────────
        today = date.today()
        this_q = current_quarter(today)
        last_q = 0

        if os.path.exists(LAST_STOCKTICKERS_RUN):
            with open(LAST_STOCKTICKERS_RUN) as f:
                last_run_date = datetime.strptime(f.read().strip(), "%Y-%m-%d").date()
                last_q = current_quarter(last_run_date)

        if this_q != last_q:
            print("New quarter detected – running StockTickers.py")
            run_script("StockTickers.py")
            scripts_run.append("StockTickers")
            with open(LAST_STOCKTICKERS_RUN, "w") as f:
                f.write(str(today))
        else:
            print("Skipping - StockTickers.py already ran this quarter")

        # 1) Daily screen once
        if not ran_select_today():
            run_script("SelectStocks.py")
            scripts_run.append("SelectStocks")
            mark_select_ran()
        else:
            print("Skipping - SelectStocks.py already ran today")

        # 2) How many sells have happened already today?
        sells_before = get_todays_sells()

        # 3) Run generate+execute
        run_script("GenerateSignals.py")
        scripts_run.append("GenerateSignals")
        run_script("ExecuteTrades.py")
        scripts_run.append("ExecuteTrades")

        # 4) Handle new sells
        new_sells = get_todays_sells() - sells_before
        monitor_already_started = (
                os.path.exists(MONITOR_FLAG) and
                open(MONITOR_FLAG).read().strip() == str(date.today())
            )
        
        # Check if deferred_sells.json is non-empty
        def is_deferred_sells_nonempty():
            if not os.path.exists(DEFERRED_SELLS_FILE):
                return False
            try:
                with open(DEFERRED_SELLS_FILE, 'r') as f:
                    data = json.load(f)
                    return bool(data)  # True if data is not empty (e.g., list or dict with content)
            except (json.JSONDecodeError, ValueError):
                return False  # File is invalid or empty

        monitor_started = False

        if not monitor_already_started and is_deferred_sells_nonempty():
            print("Launching MonitorDeferredSells.py...")
            subprocess.Popen(["python", "MonitorDeferredSells.py"])
            with open(MONITOR_FLAG, "w") as f:
                f.write(str(date.today()))
            scripts_run.append("DEFERRED - MonitorDeferredSells STARTED")
            monitor_started = True

        # CASE 1: Real sells today → proceed immediately
        if new_sells:
            print("Detected real sells for today.")
            run_script("GenerateSignals.py")
            scripts_run.append("NEW SELL - GenerateSignals")
            run_script("ExecuteTrades.py")
            scripts_run.append("NEW SELL - ExecuteTrades")

        # CASE 2: No real sells, but deferred monitor was started → wait, then act
        elif monitor_started:
            print("Waiting for MonitorDeferredSells.py to finish...")
            while os.path.exists(MONITOR_FLAG):
                time.sleep(60)
            print("MonitorDeferredSells.py has finished.")

            run_script("GenerateSignals.py")
            scripts_run.append("AFTER MONITOR - GenerateSignals")
            run_script("ExecuteTrades.py")
            scripts_run.append("AFTER MONITOR - ExecuteTrades")
        else:
            print("No new sells and no need to start MonitorDeferredSells.")

        # 5) Summarize trades
        run_script("TradeSummary.py")
        scripts_run.append("TradeSummary")
        end_time = datetime.now()
        print("=== Run complete ===")
        return scripts_run
    except Exception as e:
        raise e

if __name__ == "__main__":
    start_time = datetime.now()
    success = True
    error_message = None
    scripts_run = []

    try:
        scripts_run = job()
    except Exception as e:
        success = False
        error_message = str(e)
        print(f"ERROR: {error_message}")

    end_time = datetime.now()

    run_entry = {
        "initiator": os.path.basename(__file__),
        "timestamp": start_time.isoformat(),
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "success": success,
        "error_message": error_message,
        "scripts_run": scripts_run
    }

    log_run(run_entry)
