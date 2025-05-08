# run_bot.py

import os
import json
import time
import subprocess
from datetime import date, datetime
from DataManager import fetch_and_cache_prices
import pandas as pd

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
PORTFOLIO_FILE   = "portfolio_summary.json"
TRADE_LOG        = "trades_log.json"
DAILY_SCREEN     = "daily_screen.json"
LAST_SELECT_RUN  = "selectstocks_last_run.txt"
INITIAL_CASH     = 10_000

# ─── PRE-FETCH HISTORICAL DATA ─────────────────────────────────────────────────
# Load universe same as SelectStocks
ftse100 = pd.read_csv("ftse100_constituents.csv")
UNIVERSE = [f"{s}.L" for s in ftse100["Symbol"].dropna().unique()]
# Cache 60 days daily history for all symbols
fetch_and_cache_prices(UNIVERSE, period="60d", interval="1d", force=True) # Force = Ensure Latest values downloaded

# ────────────────────────────────────────────────────────────────────────────────
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
    today_str = str(date.today())
    sells = set()
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG) as f:
            logs = json.load(f)
        sells.update({e["ticker"] for e in logs if e["action"]=="SELL" and e["date"]==today_str})
    if os.path.exists("deferred_sells.json"):
        with open("deferred_sells.json") as f:
            deferred = json.load(f)
        sells.update({t for t,d in deferred.items() if d.get("date_flagged")==today_str})
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
    print(f"\n=== Bot run at {datetime.now().isoformat()} ===")
    init_portfolio()

    # 1) Daily screen once
    if not ran_select_today():
        run_script("SelectStocks.py")
        mark_select_ran()
    else:
        print("Skipping SelectStocks.py (already ran today)")

    # 2) How many sells have happened already today?
    sells_before = get_todays_sells()

    # 3) Run generate+execute
    run_script("GenerateSignals.py")
    run_script("ExecuteTrades.py")

    # 4) Handle new sells
    new_sells = get_todays_sells() - sells_before
    if new_sells:
        print(f"New sells detected: {new_sells}")
        prune_sold_from_screen(new_sells)
        run_script("GenerateSignals.py")
        run_script("ExecuteTrades.py")
        run_script("MonitorDeferredSells.py")
    else:
        print("No new sells this run.")

    # 5) Summarize trades
    run_script("TradeSummary.py")
    print("=== Run complete ===")


if __name__ == "__main__":
    job()
    # Uncomment to schedule periodic runs
    # while True:
    #     time.sleep(600)
    #     job()
