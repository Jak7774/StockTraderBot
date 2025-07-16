import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import num2date
import matplotlib.dates as mdates
from collections import defaultdict, deque
from datetime import datetime
from GenerateSignals import df_from_cache, SHORT_W, LONG_W, calculate_macd  # <-- import shared logic

BUFFER = LONG_W

# Load data
with open("portfolio_summary.json", "r") as f:
    portfolio = json.load(f)

with open("price_cache.json", "r") as f:
    price_data = json.load(f)

with open("trades_log.json", "r") as f:
    trades = json.load(f)

# Ask user what to visualise
mode = input("Would you like to view (1) Current Holdings or (2) Recent Sells? Enter 1 or 2: ").strip()

if mode == "1":
    # ── CURRENT HOLDINGS ──
    owned_tickers = [tkr for tkr, qty in portfolio["holdings"].items() if qty > 0]
    if not owned_tickers:
        print("You currently don't own any stocks.")
        exit()

    # First buy date per ticker
    buy_dates = {}
    for entry in portfolio["history"]:
        dt = pd.to_datetime(entry["datetime"])
        for tkr in entry["holdings"]:
            if tkr in owned_tickers:
                if tkr not in buy_dates or dt < buy_dates[tkr]:
                    buy_dates[tkr] = dt

    print("Stocks you currently own:\n")
    for i, tkr in enumerate(owned_tickers):
        print(f"{i+1}. {tkr} (since {buy_dates[tkr].date()})")

    choice = int(input("\nSelect a stock to view MA crossover plot (enter number): ")) - 1
    ticker = owned_tickers[choice]
    start_date = buy_dates[ticker]

    df = df_from_cache(ticker)
    if df.empty:
        print("No price data available.")
        exit()

    BUFFER_DAYS = 4 * LONG_W
    raw_buffered_start = start_date - pd.Timedelta(days=BUFFER_DAYS)
    available_start = df.index[df.index.get_indexer([raw_buffered_start], method="bfill")[0]]
    df_ma = df[df.index >= available_start].copy()


    df_ma = calculate_macd(df_ma)
    df_ma["Short_EMA"] = df_ma["Close"].ewm(span=SHORT_W, adjust=False).mean()
    df_ma["Long_EMA"] = df_ma["Close"].ewm(span=LONG_W, adjust=False).mean()

    start_plot_date = df_ma.index[df_ma.index.get_indexer([start_date], method='ffill')[0]]
    df_plot = df_ma[df_ma.index >= start_plot_date]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    # Plot price and EMAs on primary y-axis
    ax1.plot(df_plot["Close"], label="Stock Price (£)", color="gray", alpha=0.6)
    ax1.plot(df_plot["Short_EMA"], label=f"Short EMA ({SHORT_W}-day)", color="blue")
    ax1.plot(df_plot["Long_EMA"], label=f"Long EMA ({LONG_W}-day)", color="red")
    ax1.set_ylabel("Price (£)")
    ax1.grid(True)

    ax1.axvline(start_date, color='green', linestyle='--', alpha=0.5, label="Buy Date")

    # Create secondary y-axis for MACD
    ax2 = ax1.twinx()
    ax2.plot(df_plot["MACD"], label="MACD Line", color="purple", linestyle="--")
    ax2.plot(df_plot["Signal"], label="Signal Line (MACD)", color="orange", linestyle=":")
    ax2.set_ylabel("MACD")
    ax2.axhline(0, color="black", linestyle="--", linewidth=0.5)

    # Combine legends from both axes
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines_1 + lines_2,
        labels_1 + labels_2,
        loc='upper left',
        bbox_to_anchor=(1.05, 1),
        borderaxespad=0.,
        fontsize='small'
    )

    plt.title(f"{ticker} Price, EMA & MACD (since {start_date.date()})")
    plt.xlabel("Date")

    left_padding = pd.Timedelta(days=0.5)
    right_padding = pd.Timedelta(days=1)
    plt.xlim(start_date - left_padding, df_plot.index[-1] + right_padding)

    plt.tight_layout()
    plt.show()

elif mode == "2":
    # ── RECENT SELLS ──
    transactions = defaultdict(list)
    for entry in trades:
        entry["date"] = pd.to_datetime(entry["date"])
        transactions[entry["ticker"]].append(entry)

    fully_closed = {}
    sell_ranges = {}

    for tkr, txns in transactions.items():
        txns.sort(key=lambda x: x["date"])
        buy_queue = deque()
        shares_held = 0
        matched_ranges = []

        for txn in txns:
            if txn["action"] == "BUY":
                buy_queue.append({"date": txn["date"], "shares": txn["shares"]})
                shares_held += txn["shares"]
            elif txn["action"] == "SELL":
                sell_date = txn["date"]
                shares_to_sell = txn["shares"]
                shares_held -= shares_to_sell

                while shares_to_sell > 0 and buy_queue:
                    buy = buy_queue[0]
                    matched = min(buy["shares"], shares_to_sell)
                    matched_ranges.append((buy["date"], sell_date, matched))

                    buy["shares"] -= matched
                    shares_to_sell -= matched

                    if buy["shares"] == 0:
                        buy_queue.popleft()

        if shares_held == 0 and matched_ranges:
            first_buy = min(d for d, _, _ in matched_ranges)
            last_sell = max(s for _, s, _ in matched_ranges)
            fully_closed[tkr] = (first_buy, last_sell)

    if not fully_closed:
        print("No fully closed positions found.")
        exit()

    print("Fully closed tickers:\n")
    for i, (tkr, (buy, sell)) in enumerate(fully_closed.items()):
        print(f"{i+1}. {tkr} (Bought: {buy.date()}, Sold: {sell.date()})")

    choice = int(input("\nSelect a ticker to view trend plot (enter number): ")) - 1
    ticker = list(fully_closed.keys())[choice]
    start_date, end_date = fully_closed[ticker]

    if start_date == end_date:
        print(f"⛔ Cannot plot {ticker} — Buy and Sell occurred on the same day ({start_date.date()}). Skipping.")
        exit()

    # Step 1: Calculate full buffered range for MA
    BUFFER_DAYS = 2 * LONG_W  # Give enough margin for market gaps, holidays, etc.
    raw_buffered_start = start_date - pd.Timedelta(days=BUFFER_DAYS)

    # Step 2: Load full data before slicing
    daily_data = price_data[ticker]["daily"]
    dates = pd.to_datetime(daily_data["dates"])
    close_prices = daily_data["close"]
    df = pd.DataFrame({"Close": close_prices}, index=dates)
    df.index.name = "Date"
    df.sort_index(inplace=True)

    # Step 3: Find the actual buffered start in data
    available_start = df.index[df.index.get_indexer([raw_buffered_start], method="bfill")[0]]
    df_ma = df[df.index >= available_start].copy()

    # Step 4: Calculate moving averages on full data
    df_ma["Short_MA"] = df_ma["Close"].rolling(SHORT_W).mean()
    df_ma["Long_MA"] = df_ma["Close"].rolling(LONG_W).mean()

    # Step 5: Slice only for the buy→sell window for display
    df_plot = df_ma[(df_ma.index >= start_date) & (df_ma.index <= end_date)]
    if df_plot.empty:
        print(f"⛔ No price data available between {start_date.date()} and {end_date.date()} for {ticker}. Skipping.")
        exit()

    # Step 6: Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df_plot["Close"], label="Stock Price (£)", color="gray", alpha=0.6)
    plt.plot(df_plot["Short_MA"], label=f"Short MA ({SHORT_W}-day)", color="blue")
    plt.plot(df_plot["Long_MA"], label=f"Long MA ({LONG_W}-day)", color="red")
    
    # Add Buy/Sell lines
    aligned_start_date = df_plot.index[df_plot.index.get_indexer([start_date], method="nearest")[0]]
    plt.axvline(aligned_start_date, color='green', linestyle='--', alpha=0.5, label="Buy Date")
    aligned_end_date = df_plot.index[df_plot.index.get_indexer([end_date], method="nearest")[0]]
    plt.axvline(aligned_end_date, color='red', linestyle='--', alpha=0.5, label="Sell Date")

    # Annotate Buy and Sell Dates
    plt.text(aligned_start_date, df_plot["Close"].max(), " Buy", color='green', va='bottom', ha='left', fontweight='bold')
    plt.text(aligned_end_date, df_plot["Close"].max(), " Sell", color='red', va='bottom', ha='left', fontweight='bold')

    # BUY / SELL Price
    buy_prices = []
    sell_prices = []

    for txn in trades:
        if txn["ticker"] == ticker:
            txn_date = pd.to_datetime(txn["date"])
            if start_date <= txn_date <= end_date:
                if txn["action"] == "BUY":
                    buy_prices.append(txn["price"])
                elif txn["action"] == "SELL":
                    sell_prices.append(txn["price"])

    # Calculate weighted average prices if multiple trades
    avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else None
    avg_sell_price = sum(sell_prices) / len(sell_prices) if sell_prices else None

    offset_x = 0.01
    ax = plt.gca()
    xlim = ax.get_xlim()
    line_start = xlim[0] + 0.95 * (xlim[1] - xlim[0])
    line_end = xlim[1]

    if avg_buy_price is not None:
        plt.hlines(avg_buy_price, xmin=line_start, xmax=line_end, colors='green', linewidth=2, label='Avg Buy Price')
        plt.text(1 + offset_x, avg_buy_price, f'Buy Price £{avg_buy_price:.2f}', color='green',
                va='center', ha='left', fontweight='bold', fontsize=9,
                transform=ax.get_yaxis_transform())

    if avg_sell_price is not None:
        plt.hlines(avg_sell_price, xmin=line_start, xmax=line_end, colors='red', linewidth=2, label='Avg Sell Price')
        plt.text(1 + offset_x, avg_sell_price, f'Sell Price £{avg_sell_price:.2f}', color='red',
                va='center', ha='left', fontweight='bold', fontsize=9,
                transform=ax.get_yaxis_transform())



    plt.title(f"{ticker} Price & MA Crossover (BUY → SELL: {start_date.date()} → {end_date.date()})")
    plt.xlabel("Date")
    plt.ylabel("Price (£)")
    plt.grid(True)
    plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0.)
    plt.tight_layout()

    # Force x-axis ticks to include Buy and Sell dates
    tick_positions = list(df_plot.index[::max(1, len(df_plot)//8)])

    if aligned_start_date not in tick_positions:
        tick_positions.insert(0, aligned_start_date)
    if aligned_end_date not in tick_positions:
        tick_positions.append(aligned_end_date)
    
    tick_positions = sorted(set(tick_positions)) # Make sure unique

    plt.gca().set_xticks(tick_positions)
    plt.gca().set_xticklabels([
        num2date(tick).strftime('%Y-%m-%d') if not isinstance(tick, pd.Timestamp) else tick.strftime('%Y-%m-%d')
        for tick in tick_positions
    ])
    plt.xticks(rotation=45, ha='right')
    
    left_padding = pd.Timedelta(days=0.3) 
    right_padding = pd.Timedelta(days=0.3)
    plt.xlim(df_plot.index.min() - left_padding, aligned_end_date + right_padding)

    plt.show()

else:
    print("Invalid selection.")
