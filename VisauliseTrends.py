import json
import pandas as pd
import matplotlib.pyplot as plt

# MA window sizes
SHORT_W = 5
LONG_W = 20

# Load portfolio summary
with open("portfolio_summary.json", "r") as f:
    portfolio = json.load(f)

# Load price cache
with open("price_cache.json", "r") as f:
    price_data = json.load(f)

# 1. Get tickers with positive holdings
owned_tickers = [tkr for tkr, qty in portfolio["holdings"].items() if qty > 0]

if not owned_tickers:
    print("You currently don't own any stocks.")
    exit()

# 2. Find first purchase date for each ticker
buy_dates = {}
for entry in portfolio["history"]:
    dt = pd.to_datetime(entry["datetime"])
    for tkr in entry["holdings"]:
        if tkr in owned_tickers:
            if tkr not in buy_dates or dt < buy_dates[tkr]:
                buy_dates[tkr] = dt

# 3. Show menu
print("Stocks you currently own:\n")
for i, tkr in enumerate(owned_tickers):
    print(f"{i+1}. {tkr} (since {buy_dates[tkr].date()})")

# 4. Choose ticker
choice = int(input("\nSelect a stock to view MA crossover plot (enter number): ")) - 1
ticker = owned_tickers[choice]
start_date = buy_dates[ticker]

# 5. Extract price data
daily_data = price_data[ticker]["daily"]
dates = pd.to_datetime(daily_data["dates"])
close_prices = daily_data["close"]

df = pd.DataFrame({"Close": close_prices}, index=dates)
df.index.name = "Date"
df.sort_index(inplace=True)

# 6. Filter to show only since you purchased it
BUFFER = LONG_W  # extra buffer for MA stability
ma_start_date = start_date - pd.Timedelta(days=LONG_W + BUFFER)
df = df[df.index >= ma_start_date]

# 7. Calculate moving averagesma_start_date = buy_date - pd.Timedelta(days=LONG_W)
df["Short_MA"] = df["Close"].rolling(SHORT_W).mean()
df["Long_MA"] = df["Close"].rolling(LONG_W).mean()

df_plot = df[df.index >= start_date]

# 8. Plot
plt.figure(figsize=(12, 6))
plt.plot(df_plot["Close"], label="Stock Price (£)", color="gray", alpha=0.6)
plt.plot(df_plot["Short_MA"], label=f"Short MA ({SHORT_W}-day)", color="blue")
plt.plot(df_plot["Long_MA"], label=f"Long MA ({LONG_W}-day)", color="red")
plt.axvline(start_date, color='green', linestyle='--', alpha=0.5, label="Buy Date")
plt.title(f"{ticker} Price & MA Crossover (since {start_date.date()})")
plt.xlabel("Date")
plt.ylabel("Price (£)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
