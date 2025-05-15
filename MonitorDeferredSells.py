import time
import datetime
import json
import yfinance as yf
import os
import sys
import portalocker # Lock File so only run one instance
import logging

# ───────── Script Variables ───────────────────────────────────────────────────────────────────
RUN_LOG_FILE = "run_log.json"
PORTFOLIO_FILE = "portfolio_summary.json"
TRADE_LOG_FILE = "trades_log.json"
DEFERRED_FILE = "deferred_sells.json"

# IF running on Windows and ANSI sequences don’t work, enable ANSI support like this
if os.name == 'nt':
    os.system('')

# ───────── Logging of Script Performance (meta-data) ─────────────────────────────────────────

def load_run_log():
    if not os.path.exists(RUN_LOG_FILE):
        return []
    with open(RUN_LOG_FILE) as f:
        return json.load(f)

def save_run_log(log):
    with open(RUN_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)

def log_run_entry(start_time, end_time, success=True, error_message=None, scripts_run=None):
    log = load_run_log()
    run_entry = {
        "initiator": os.path.basename(__file__),
        "timestamp": start_time.isoformat(),
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "success": success,
        "error_message": error_message,
        "scripts_run": scripts_run or []
    }
    log.append(run_entry)
    save_run_log(log)


# ───────── Lock Script (single dynamic instance) ──────────────────────────────────────────────

def is_already_running(lock_file_path="monitor.lock"):
    lock_file = open(lock_file_path, 'w')
    try:
        portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return False, lock_file
    except portalocker.LockException:
        return True, None

def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"cash": 0, "holdings": {}, "history": []}
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)

def load_deferred():
    if not os.path.exists(DEFERRED_FILE):
        return []
    with open(DEFERRED_FILE) as f:
        return json.load(f)

def save_deferred(deferred):
    with open(DEFERRED_FILE, "w") as f:
        json.dump(deferred, f, indent=2)

def load_trade_log():
    if not os.path.exists(TRADE_LOG_FILE):
        return []
    with open(TRADE_LOG_FILE) as f:
        return json.load(f)

def save_trade_log(trade_log):
    with open(TRADE_LOG_FILE, "w") as f:
        json.dump(trade_log, f, indent=2)

def monitor_deferred():
    portfolio = load_portfolio()
    deferred = load_deferred()
    trade_log = load_trade_log()

    seen_tickers = set(deferred.keys())
    
    print(f"Monitoring {len(deferred)} deferred sells...")
    
    # initial values for help function
    loop_count = 0
    countdown = 600  

    # helper function (print timer and loop number)
    def print_status_line():
        msg = f"Total Check = {loop_count} / Time to next check = {countdown}s"
        sys.stdout.write(f"\r{msg}{' ' * 10}")
        sys.stdout.flush()

    while deferred:
        loop_count += 1

        # Reload deferred list in case new tickers were added by run_bot.py
        updated_deferred = load_deferred()
        new_tickers = set(updated_deferred.keys()) - seen_tickers
        deferred = updated_deferred

        if new_tickers:
            seen_tickers.update(new_tickers)
            sys.stdout.write("\n")  # move to next line to not overwrite status
            print(f"New deferred tickers detected: {', '.join(sorted(new_tickers))}")
            print_status_line()  # reprint status line at bottom

        now = datetime.datetime.now()

        for ticker, stock in list(deferred.items()):
            price = get_current_price(ticker)  # Fetch live price here
            if price < stock["latest_price"] or (now.hour >= 15 and now.minute >= 50):
                sell(ticker, portfolio, trade_log, price)
                deferred.pop(ticker)

                if not deferred:
                    sys.stdout.write("\n")
                    print("All deferred sells processed. Exiting.")
                    save_deferred(deferred)
                    save_portfolio(portfolio)
                    save_trade_log(trade_log)
                    if os.path.exists("monitor_started.txt"):
                        os.remove("monitor_started.txt")
                    return

            elif price > stock["latest_price"]:
                stock["latest_price"] = price

        save_deferred(deferred)
        save_portfolio(portfolio)
        save_trade_log(trade_log)
        
        countdown = 600  # 10 minutes

        while countdown > 0:
            print_status_line()

            time.sleep(50)
            countdown -= 50

            # Check for new deferred tickers again
            updated_deferred = load_deferred()
            new_tickers = set(updated_deferred.keys()) - seen_tickers
            if new_tickers:
                seen_tickers.update(new_tickers)
                sys.stdout.write("\n")
                print(f"New deferred tickers detected: {', '.join(sorted(new_tickers))}")
                print_status_line()  # ensure the status line is reprinted at bottom

def sell(ticker, portfolio, trade_log, price):
    shares = portfolio["holdings"].pop(ticker, 0)
    if shares > 0:
        portfolio["cash"] += shares * price
        trade_log.append({
            "ticker": ticker,
            "action": "SELL",
            "date": str(datetime.date.today()),
            "price": price,
            "shares": shares
        })
        print(f"Sold {shares} of {ticker} @ ${price:.2f}")

        # Use the same logic as ExecuteTrades.py for updating total value
        total_val = portfolio["cash"]
        for t, shares in portfolio["holdings"].items():
            tk = yf.Ticker(t)
            lp = tk.fast_info.last_price or 0
            total_val += shares * lp

        # Update history
        portfolio["history"].append({
            "datetime":    datetime.datetime.now().isoformat(),
            "cash":        round(portfolio["cash"], 2),
            "total_value": round(total_val, 2),
            "holdings":    portfolio["holdings"]
        })

        # Save the updated portfolio summary
        new_summary = {
            "date":     str(datetime.date.today()),
            "cash":     round(portfolio["cash"], 2),
            "holdings": portfolio["holdings"],
            "history":  portfolio["history"]
        }
        save_portfolio(new_summary)

def get_current_price(ticker):
    stock = yf.Ticker(ticker)
    price = stock.fast_info.get("last_price", None)

    if price is None or price == 0:
        try:
            hist = stock.history(period="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
        except Exception as e:
            print(f"Error fetching historical price for {ticker}: {e}")
            price = 0

    return price or 0

if __name__ == "__main__":
    already_running, lock_file = is_already_running()
    if already_running:
        print("Another instance of MonitorDeferredSells is already running. Exiting.")
        sys.exit(0)

    start_time = datetime.datetime.now()
    scripts_run = ["MonitorDeferredSells - MONITOR"]
    error_message = None
    success = True

    try:
        monitor_deferred()
    except Exception as e:
        success = False
        error_message = str(e)
        logging.exception("An error occurred in MonitorDeferredSells")
        if os.path.exists("monitor_started.txt"):
            os.remove("monitor_started.txt")
    finally:
        scripts_run.append("MonitorDeferredSells - END")
        end_time = datetime.datetime.now()
        log_run_entry(start_time, end_time, success=success, error_message=error_message, scripts_run=scripts_run)
        lock_file.close()
        if os.path.exists("monitor_started.txt"):
            os.remove("monitor_started.txt")
