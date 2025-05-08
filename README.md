# 📊 Stock Trading Bot

A lightweight Python bot for screening stocks, generating buy/sell signals using moving average crossovers, and summarizing trade activity. Built using the `yfinance` package for market data and simple JSON files for state tracking.

## 🚀 Features

- **Daily Screening** — Load daily screen data and evaluate stocks for potential action.
- **Signal Generation** — Apply a simple Moving Average Crossover strategy to identify buy/sell signals.
- **Trade Logging** — Keep a record of executed trades and current holdings.
- **Portfolio Summary** — Calculate market value, portfolio total, and track performance over time.
- **Modular Structure** — Separated scripts for signal generation, execution, and summary.
- **Supports Expansion** — Structure supports faster trading logic (e.g., every 10 minutes), with commented code for future upgrades.
- **Data Caching** — Market data is fetched once per day and cached to reduce API calls.

## 🗂️ File Overview

| File | Description |
|------|-------------|
| `DataManager.py` | Handles price caching and efficient yfinance data retrieval. |
| `StockSelect.py` | Once Per Day, The code will assess all stocks in the FTSE100 and choose good candidates to buy/sell. |
| `GenerateSignals.py` | Analyzes recent stock trends and generates trade signals. |
| `ExectuteTrades.py` | Based on signals stocks are either brought or sold. |
| `MonitorDeferredSells.py` | Monitors deferred sell candidates with positive momentum. |
| `TradeSummary.py` | Builds a trade and portfolio summary, with performance comparison. |
| `run_bot.py` | Main bot file that loads signals and executes trades. |
| `daily_screen.json` | Input file specifying tickers to consider buying or selling today. |
| `trade_signals.json` | Output from `GenerateSignals.py`, listing current BUY/SELL candidates. |
| `trades_log.json` | Persistent record of all executed trades. |
| `portfolio_summary.json` | Tracks portfolio holdings, cash, and history over time. |
| `trade_summary.json` | Latest portfolio valuation and trade summary. |
| `price_cache.json` | Cached price history used to avoid repeat calls to yfinance. |
| `selectstocks_last_run.txt` | Tracks the last run date of the screening process. |

## 📈 Strategy Overview

This bot uses a **Moving Average Crossover** method:
- **BUY signal**: When the short-term moving average crosses above the long-term average.
- **SELL signal**: When the short-term average drops below the long-term average.
- Parameters:
  - `SHORT_W = 5` days
  - `LONG_W = 20` days

Additional logic:
- **Stop-loss**: Triggered if price drops 10% below cost basis.
- **Take-profit**: Triggered if price rises 15% above cost basis.
- **Deferred Selling**: If a stock is flagged for sell but still shows positive momentum, it's deferred.

## 🔧 Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/stock-trading-bot.git
   cd stock-trading-bot
   ```

2. Install requirements (if applicable):
   ```bash
   pip install yfinance pandas matplotlib
   ```

3. Run the bot:
   ```bash
   python run_bot.py
   ```

## 🙌 Credits

- Developed by Jack Elkes.
- Trading strategy inspired by moving average crossover techniques.
- Built with insights and coding support from [ChatGPT](https://openai.com/chatgpt).
