import time
import datetime
import json
import yfinance as yf
import os

PORTFOLIO_FILE = "portfolio_summary.json"
TRADE_LOG_FILE = "trades_log.json"
DEFERRED_FILE = "deferred_sells.json"

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
    
    while deferred:
        print(f"Monitoring {len(deferred)} deferred sells...")
        now = datetime.datetime.now()

        for ticker, stock in list(deferred.items()):
            price = get_current_price(ticker)  # Fetch live price here
            if price < stock["latest_price"]:
                # Price started falling, sell stock
                sell(ticker, portfolio, trade_log, price, stock["latest_price"])
                deferred.pop(ticker)
                if not deferred:
                    print("All deferred sells processed. Exiting.")
                    save_deferred(deferred)
                    save_portfolio(portfolio)
                    save_trade_log(trade_log)
                    return
            elif now.hour >= 15 and now.minute >= 50:
                # Near market close, sell stock
                sell(ticker, portfolio, trade_log, price, stock["latest_price"])
                deferred.pop(ticker)
                if not deferred:
                    print("All deferred sells processed. Exiting.")
                    save_deferred(deferred)
                    save_portfolio(portfolio)
                    save_trade_log(trade_log)
                    return
            else:
                if price > stock["latest_price"]:
                    stock["latest_price"] = price

        save_deferred(deferred)
        save_portfolio(portfolio)
        save_trade_log(trade_log)
        time.sleep(600)  # Check every 10 minutes

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
    monitor_deferred()
