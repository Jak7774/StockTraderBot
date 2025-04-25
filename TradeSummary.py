# summarize_trades.py

import json
from datetime import date, datetime, timedelta
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

LOG_FILE        = "trades_log.json"
PORTFOLIO_FILE  = "portfolio_summary.json"
OUTPUT_FILE     = "trade_summary.json"

# ─── 1) LOAD DATA ────────────────────────────────────────────────────────────────
with open(LOG_FILE) as f:
    trades = json.load(f)

with open(PORTFOLIO_FILE) as f:
    portfolio = json.load(f)
cash_remaining = portfolio.get("cash", 0)
initial_cash = 10_000

# ─── 2) BUILD TRADES DATAFRAME ──────────────────────────────────────────────────
df = pd.DataFrame(trades)
total_trades = len(df)

# ─── 3) AGGREGATE BUY/SELL BY TICKER ────────────────────────────────────────────
summary = {}
for ticker, sub in df.groupby("ticker"):
    buys  = sub[sub["action"] == "BUY"]
    sells = sub[sub["action"] == "SELL"]

    total_buy_shares   = buys["shares"].sum()
    total_buy_cost     = (buys["shares"] * buys["price"]).sum()
    total_sell_shares  = sells["shares"].sum()
    total_sell_proceed = (sells["shares"] * sells["price"]).sum()

    net_shares = total_buy_shares - total_sell_shares
    if net_shares > 0:
        # average cost basis, adjusted for proceeds of sells
        net_cost = total_buy_cost - total_sell_proceed
        cost_basis = net_cost / net_shares
    else:
        cost_basis = None

    summary[ticker] = {
        "shares":      round(net_shares, 3),
        "cost_basis":  round(cost_basis, 2) if cost_basis is not None else None
    }

# ─── 4) FETCH CURRENT PRICES ───────────────────────────────────────────────────
tickers = list(summary.keys())
if tickers:
    data = yf.download(tickers, period="1d", auto_adjust=True, progress=False)["Close"].iloc[-1]
    if isinstance(data, pd.Series):
        prices = data.to_dict()
    else:
        prices = {tickers[0]: float(data)}
else:
    prices = {}

# ─── 5) COMPUTE MARKET VALUES ───────────────────────────────────────────────────
total_market_value = 0
for tkr, info in summary.items():
    price = prices.get(tkr, 0)
    info["current_price"] = round(price, 2)
    info["market_value"]   = round(info["shares"] * price, 2)
    total_market_value    += info["market_value"]

# ─── 6) TOTAL PORTFOLIO VALUE ──────────────────────────────────────────────────
total_value = round(cash_remaining + total_market_value, 2)

# Compute change vs initial cash (e.g., starting portfolio value)
change_total = round(total_value - initial_cash, 2)

# Get the last snapshot from the previous calendar day
history = portfolio.get("history", [])
yesterday = date.today() - timedelta(days=1)

# Parse datetimes and filter for entries from yesterday
prev_day_snapshots = [
    h for h in history
    if "datetime" in h and datetime.fromisoformat(h["datetime"]).date() == yesterday
]

if prev_day_snapshots:
    # Use the last snapshot from the previous day
    last_prev_day = max(prev_day_snapshots, key=lambda h: h["datetime"])
    prev_day_value = last_prev_day.get("total_value", total_value)
    change_since_last = round(total_value - prev_day_value, 2)
else:
    change_since_last = 0.0

# ─── 7) BUILD OUTPUT DICT ──────────────────────────────────────────────────────
output = {
    "date":             str(date.today()),
    "total_trades":     total_trades,
    "cash_remaining":   round(cash_remaining, 2),
    "market_value":     round(total_market_value, 2),
    "total_value":      total_value,
    "total_change":     change_total,
    "change_since_last": change_since_last,
    "holdings":         summary
}

# ─── 8) SAVE TO JSON ────────────────────────────────────────────────────────────
with open(OUTPUT_FILE, "w") as f:
    json.dump(output, f, indent=2)

# ─── 9) PRINT A QUICK SUMMARY ──────────────────────────────────────────────────
if change_total > 0:
    total_color = "\033[92m"  # green
elif change_total < 0:
    total_color = "\033[91m"  # red
else:
    total_color = "\033[0m"
reset = "\033[0m"

delta_str = f"{change_total:+.2f}"
delta_last_str = f"{change_since_last:+.2f}"

print(f"Trade summary for {output['date']}:")
print(f" • Total trades executed: {output['total_trades']}")
print(f" • Cash remaining:        ${output['cash_remaining']:.2f}")
print(f" • Market value:          ${output['market_value']:.2f}")
print(f" • TOTAL portfolio value: {total_color}${output['total_value']:.2f} "
      f"({delta_str} | {delta_last_str} since yesterday){reset}")
print("Holdings:")
for tkr, info in output["holdings"].items():
    cost = info["cost_basis"]
    current = info["current_price"]
    if cost is None or current is None:
        color = "\033[0m"
    elif current > cost:
        color = "\033[92m"
    elif current < cost:
        color = "\033[91m"
    else:
        color = "\033[0m"
    reset = "\033[0m"
    print(f"{color}  {tkr:<6} = {info['shares']:.3f} shares, cost basis ${cost}, "
      f"current ${current} → ${info['market_value']}{reset}")

print(f"\n✅ Saved trade summary to {OUTPUT_FILE}")

# ─── 10) PLOT PROFIT/LOSS SUMMARY ──────────────────────────────────────────────────
# Extract the history section
history = portfolio['history']
df = pd.DataFrame(history)
df['datetime'] = pd.to_datetime(df['datetime'])
df.set_index('datetime', inplace=True)

# Plot total value over time
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['total_value'], marker='o')
plt.title('Portfolio Total Value Over Time')
plt.xlabel('Time')
plt.ylabel('Total Value (£)')
plt.grid(True)
plt.tight_layout()
plt.show()