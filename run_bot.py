# run_bot.py

import os
import json
import time
import subprocess
from datetime import date, datetime

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
PORTFOLIO_FILE   = "portfolio_summary.json"
TRADE_LOG        = "trades_log.json"
DAILY_SCREEN     = "daily_screen.json"
LAST_SELECT_RUN  = "selectstocks_last_run.txt"
INITIAL_CASH     = 10_000

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
    """Return set of tickers SELLed today by scanning trades_log.json."""
    if not os.path.exists(TRADE_LOG):
        return set()
    with open(TRADE_LOG) as f:
        logs = json.load(f)
    today_str = str(date.today())
    return {entry["ticker"] for entry in logs
            if entry["action"] == "SELL" and entry["date"] == today_str}

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

    # 4) Check new sells from this run
    sells_after = get_todays_sells()
    new_sells = sells_after - sells_before
    if new_sells:
        print(f"New sells detected this run: {new_sells}")

        # 5) Prune those from today's screen
        prune_sold_from_screen(new_sells)

        # 6) Rerun generate+execute on pruned universe
        run_script("GenerateSignals.py")
        run_script("ExecuteTrades.py")

        # 7) Monitor deferred sells (for trending up stocks)
        run_script("MonitorDeferredSells.py")
    else:
        print("No new sells this run.")

    # 7) Summarize trades
    run_script("TradeSummary.py")

    print("=== Run complete ===")

if __name__ == "__main__":
    # Initial run
    job()
    # Loop
    # print("Scheduler: will run every 10 mins. Press Ctrl+C to stop.")
    # while True:
    #     time.sleep(600)
    #     job()
