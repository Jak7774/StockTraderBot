import matplotlib.pyplot as plt
from collections import defaultdict, deque
import statistics
import json
import random
from datetime import datetime

# Load trade log
with open("trades_log.json", "r") as f:
    data = json.load(f)

# Group and sort trades by ticker
transactions = defaultdict(list)
for entry in data:
    entry["date"] = datetime.fromisoformat(entry["date"])
    transactions[entry["ticker"]].append(entry)

for txns in transactions.values():
    txns.sort(key=lambda x: x["date"])

# P&L and match logging
differences = {}
matched_trades_log = defaultdict(list)

for ticker, txns in transactions.items():
    buy_queue = deque()
    total_profit = 0
    shares_held = 0

    for txn in txns:
        if txn["action"] == "BUY":
            buy_queue.append({"price": txn["price"], "shares": txn["shares"], "date": txn["date"]})
            shares_held += txn["shares"]
        elif txn["action"] == "SELL":
            sell_price = txn["price"]
            shares_to_sell = txn["shares"]
            sell_date = txn["date"]
            shares_held -= shares_to_sell

            while shares_to_sell > 0 and buy_queue:
                buy = buy_queue[0]
                matched_shares = min(buy["shares"], shares_to_sell)
                profit = (sell_price - buy["price"]) * matched_shares
                total_profit += profit

                # Log the match
                matched_trades_log[ticker].append({
                    "buy_price": buy["price"],
                    "sell_price": sell_price,
                    "shares": matched_shares,
                    "buy_date": buy["date"].isoformat(),
                    "sell_date": sell_date.isoformat(),
                    "profit": profit
                })

                buy["shares"] -= matched_shares
                shares_to_sell -= matched_shares

                if buy["shares"] == 0:
                    buy_queue.popleft()

    if shares_held == 0:
        differences[ticker] = total_profit

# Print matched trades
print("=== Matched Trades ===")
for ticker, matches in matched_trades_log.items():
    print(f"\nTicker: {ticker}")
    for match in matches:
        print(f"  Bought {match['shares']:.3f} @ {match['buy_price']} on {match['buy_date']}, "
              f"Sold @ {match['sell_price']} on {match['sell_date']} → "
              f"Profit: £{match['profit']:.2f}")


# Prepare data for plot
tickers = list(differences.keys())
diffs = list(differences.values())
colors = ['green' if diff > 0 else 'red' for diff in diffs]
average = statistics.mean(diffs) if diffs else 0

# Plot
plt.figure(figsize=(10, 6))
plt.axhline(y=average, color='blue', linestyle='--', label=f'Average: {average:.2f}')

for i, (ticker, diff, color) in enumerate(zip(tickers, diffs, colors)):
    jitter = random.uniform(-0.2, 0.2)
    plt.scatter(jitter, diff, color=color, s=100)
    plt.text(jitter, diff, f" {ticker}", va='center', ha='left', fontsize=9)

plt.xlim(-1, 1)
plt.xticks([])
plt.ylabel("Profit/Loss (£)")
plt.title("Profit/Loss per Fully Closed Stock Position (FIFO Matching)")
plt.legend()
plt.tight_layout()
plt.show()
