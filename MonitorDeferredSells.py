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

        for stock in deferred.copy():
            price = get_current_price(stock["ticker"])  # Fetch live price here
            if price < stock["last_price"]:
                # Price started falling, sell stock
                sell(stock["ticker"], portfolio, trade_log, price, stock["last_price"])
                deferred.remove(stock)
            elif now.hour >= 15 and now.minute >= 50:
                # Near market close, sell stock
                sell(stock["ticker"], portfolio, trade_log, price, stock["last_price"])
                deferred.remove(stock)
            else:
                # Update last price if price is still increasing
                if price > stock["last_price"]:
                    stock["last_price"] = price

        save_deferred(deferred)
        save_portfolio(portfolio)
        save_trade_log(trade_log)
        time.sleep(600)  # Check every 10 minutes

def sell(ticker, portfolio, trade_log, price, last_price):
    shares = portfolio["holdings"].pop(ticker, 0)
    if shares > 0:
        cash = portfolio["cash"]
        portfolio["cash"] += shares * price
        trade_log.append({
            "ticker": ticker,
            "action": "SELL",
            "date": str(datetime.date.today()),
            "price": price,
            "shares": shares
        })
        print(f"Sold {shares} of {ticker} @ ${price:.2f}")
        
        # Update portfolio history
        portfolio["history"].append({
            "datetime": str(datetime.datetime.now()),
            "cash": portfolio["cash"],
            "total_value": portfolio["cash"] + sum(
                get_current_price(tkr) * qty for tkr, qty in portfolio["holdings"].items()
            ),
            "holdings": [{"ticker": tkr, "shares": qty} for tkr, qty in portfolio["holdings"].items()]
        })

def get_current_price(ticker):
    stock = yf.Ticker(ticker)
    price = stock.fast_info.get('last_price', 0)  # Use 0 if price is not available
    return price

if __name__ == "__main__":
    monitor_deferred()
