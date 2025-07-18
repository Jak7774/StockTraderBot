# 📊 Stock Trading Bot

A lightweight Python bot for screening stocks, generating buy/sell signals using EMA crossovers and MACD, and summarizing trade activity. Built using the `yfinance` package for market data and simple JSON files for state tracking.

## 🚀 Features

- **Daily Screening** — Load daily screen data and evaluate stocks for potential action.
- **Signal Generation** — Uses Exponential Moving Average (EMA) crossovers and MACD to identify trade signals.
- **Trade Logging** — Keep a record of executed trades and current holdings.
- **Portfolio Summary** — Calculate market value, portfolio total, and track performance over time.
- **Modular Structure** — Separated scripts for signal generation, execution, and summary.
- **Supports Expansion** — Structure supports faster trading logic (e.g., every 10 minutes), with commented code for future upgrades.
- **Data Caching** — Market data is fetched once per day and cached to reduce API calls.

## 🗂️ File Overview

### Python Scripts
| File | Description |
|------|-------------|
| `DataManager.py` | Handles price caching and efficient yfinance data retrieval. |
| `StockTickers.py` | Once per Quarter, run script to download latest Stocks in FTSE100 and Codes |
| `StockSelect.py` | Once Per Day, The code will assess all stocks in the FTSE100 and choose good candidates to buy/sell. |
| `GenerateSignals.py` | Analyzes recent stock trends and generates trade signals. |
| `ExectuteTrades.py` | Based on signals stocks are either brought or sold. |
| `MonitorDeferredSells.py` | Monitors deferred sell candidates with positive momentum. |
| `TradeSummary.py` | Builds a trade and portfolio summary, with performance comparison. |
| `run_bot.py` | Main bot file that loads signals and executes trades. |

### JSON Files
| File | Description |
|------|-------------|
| `run_log.json`| Record each time `run_bot.py` or `MonitorDeferredSells.py` is executed, useful log when schedule task. |
| `violations_log.json` | List of any recorded violations that have occured (e.g. funds available lower than expected) |
| `ftse100_stocks.json` | List of all stocks and their codes from most recent FTSE100 list. |
| `daily_screen.json` | Input file specifying tickers to consider buying or selling today. |
| `deferred_sells.json` | List of any stocks deferred to sell later in the day based on momentum. |
| `trade_signals.json` | Output from `GenerateSignals.py`, listing current BUY/SELL candidates. |
| `trades_log.json` | Persistent record of all executed trades. |
| `portfolio_summary.json` | Tracks portfolio holdings, cash, and history over time. |
| `trade_summary.json` | Latest portfolio valuation and trade summary. |
| `price_cache.json` | Cached price history used to avoid repeat calls to yfinance. |

### Text Files
| File | Description |
|------|-------------|
| `selectstocks_last_run.txt` | Tracks the last run date of the screening process. |
| `stocktickers_last_run.txt` | Check when `StockTickers.py` last run, and update if new quarter |

## 📈 Strategy Overview

This bot uses a **momentum-driven strategy based on EMAs and MACD**:
- **Signal Generation** for Exponential Moving Averages (EMA):
   - **BUY**: When 5-day EMA crosses above 20-day EMA.
   - **SELL**: When 5-day EMA crosses below 20-day EMA.

- **MACD Confirmation**:
   - MACD and its signal line are calculated and plotted, helping visualize momentum shifts.
   - Signals are more reliable when MACD supports the EMA crossover.

- **Trade Rules**:
   - **Stop-loss**: If price drops ≥10% below cost basis, trigger a SELL.
   - **Take-profit**: If price rises ≥15% above cost basis, trigger a SELL.

- Parameters:
  - `SHORT_W = 5` days
  - `LONG_W = 20` days

Additional logic:
- **Stop-loss**: Triggered if price drops 10% below cost basis.
- **Take-profit**: Triggered if price rises 15% above cost basis.
- **Deferred Selling**: If a stock is flagged for sell but still shows positive momentum, it's deferred and monitored for the rest of the day (sold either at first drop or at latest end of day). 

## 🔧 Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/stock-trading-bot.git
   cd stock-trading-bot
   ```

2. Install requirements (if applicable):
   ```bash
   pip install yfinance pandas matplotlib portalocker
   ```

3. Run the bot:
   ```bash
   python run_bot.py
   ```

## 🙌 Credits

- Developed by Jack Elkes.
- Trading strategy inspired by EMA crossovers and MACD indicators.
- Built with insights and coding support from [ChatGPT](https://openai.com/chatgpt).
