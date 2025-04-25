import yfinance as yf
import pandas as pd
import json

# ─── 1) LOAD CURRENT HOLDINGS ───────────────────────────────────────────────────
try:
    with open("portfolio_summary.json") as f:
        holdings = set(json.load(f).get("holdings", {}).keys())
except FileNotFoundError:
    holdings = set()

# ─── 1b) LOAD TRADES AND BUILD COST BASIS MAP ────────────────────────────────────
# so we can apply stop-loss / take-profit - override MA logic
try:
    with open("trades_log.json") as f:
        trades = json.load(f)
    data_trades = pd.DataFrame(trades)
    cost_basis_map = {}
    for ticker, sub in data_trades.groupby("ticker"):
        buys  = sub[sub["action"] == "BUY"]
        sells = sub[sub["action"] == "SELL"]
        net_shares = buys["shares"].sum() - sells["shares"].sum()
        net_cost   = (buys["shares"] * buys["price"]).sum() - (sells["shares"] * sells["price"]).sum()
        if net_shares > 0:
            cost_basis_map[ticker] = net_cost / net_shares
except (FileNotFoundError, ValueError):
    cost_basis_map = {}

# ─── 2) LOAD TODAY'S SCREEN ────────────────────────────────────────────────────
with open("daily_screen.json", "r") as f:
    screen = json.load(f)
to_buy = screen.get("to_buy", [])

# Instead of using to_sell from daily_screen, use all current holdings
to_sell = list(holdings)

print(f"Candidates to BUY : {to_buy}")
print(f"Candidates to SELL (from current holdings): {to_sell}\n")

# ─── 3) PARAMETERS ──────────────────────────────────────────────────────────────
SHORT_W = 5 
LONG_W  = 20

# Parameters to Sell if Rapid changes (not detected by Moving Averages)
STOP_LOSS_PCT   = 0.10   # e.g. 10% drop
TAKE_PROFIT_PCT= 0.15   # e.g. 15% gain

# Optional fast trading mode parameters (commented out for now)
# USE_FAST_STRATEGY = True
# FAST_INTERVAL = "15m"
# FAST_PERIOD = "5d"

buy_signals  = {}
sell_signals = {}

# ─── 4) TICKER DATA CACHE ───────────────────────────────────────────────────────

price_data_cache = {} # So Call YFinance Fewer Timess

def last_signal(ticker):
    """Fetch data and compute the latest MA-crossover signal."""
    
    # Determine frequency to use
    # if USE_FAST_STRATEGY:
    #     interval, period = FAST_INTERVAL, FAST_PERIOD
    # else:

    # 1) Fetch & cache price series
    interval, period = "1d", "60d"
    if ticker not in price_data_cache:
        data = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        price_data_cache[ticker] = data
    else:
        data = price_data_cache[ticker]

    if data.empty or len(data) < LONG_W:
        return None, None

    # 3) Compute MAs & positions
    data["Short_MA"] = data["Close"].rolling(SHORT_W).mean()
    data["Long_MA"]  = data["Close"].rolling(LONG_W).mean()
    data["Signal"]   = 0
    data.loc[data.index[SHORT_W:], "Signal"] = (
        data["Short_MA"].iloc[SHORT_W:] > data["Long_MA"].iloc[SHORT_W:]
    ).astype(int)
    data["Position"] = data["Signal"].diff()

    recent = data[data["Position"].isin([1, -1])]
    if recent.empty:
        ma_sig = "HOLD"
        price  = data["Close"].iloc[-1]
    else:
        last    = recent.iloc[-1]
        ma_sig  = "BUY" if last["Position"].item() == 1 else "SELL"
        price   = last["Close"]

    # 4) Apply stop-loss / take-profit if we own the ticker
    cb = cost_basis_map.get(ticker)
    if cb is not None:
        if price.item() <= cb * (1 - STOP_LOSS_PCT):
            return "SELL", price
        if price.item() >= cb * (1 + TAKE_PROFIT_PCT):
            return "SELL", price

    # 5) Otherwise return the MA‐based signal
    return ma_sig, float(price.iloc[0])

# ─── 5) CHECK BUY CANDIDATES ────────────────────────────────────────────────────
for t in to_buy:
    sig, price = last_signal(t)
    if sig == "BUY":
        buy_signals[t] = {"latest_price": round(price, 2), "signal": sig}

# ─── 6) CHECK ALL CURRENT HOLDINGS FOR SELL SIGNALS ─────────────────────────────
for t in holdings:
    sig, price = last_signal(t)
    if sig == "SELL":
        sell_signals[t] = {"latest_price": round(price, 2), "signal": sig}


# ─── 7) SAVE TRADE SIGNALS ─────────────────────────────────────────────────────
out = {
    "buy_signals":  buy_signals,
    "sell_signals": sell_signals
}

with open("trade_signals.json", "w") as f:
    json.dump(out, f, indent=4)

print("\n✅ trade_signals.json written")
