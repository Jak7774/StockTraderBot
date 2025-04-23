import yfinance as yf
import pandas as pd
import json

# ─── 1) LOAD CURRENT HOLDINGS ───────────────────────────────────────────────────
try:
    with open("portfolio_summary.json") as f:
        holdings = set(json.load(f).get("holdings", {}).keys())
except FileNotFoundError:
    holdings = set()

# ─── 2) LOAD TODAY'S SCREEN ────────────────────────────────────────────────────
with open("daily_screen.json", "r") as f:
    screen = json.load(f)
to_buy  = screen.get("to_buy", [])
to_sell = screen.get("to_sell", [])

print(f"Candidates to BUY : {to_buy}")
print(f"Candidates to SELL: {to_sell}\n")

# ─── 3) PARAMETERS ──────────────────────────────────────────────────────────────
SHORT_W = 5 
LONG_W  = 20

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
    #     interval = FAST_INTERVAL
    #     period   = FAST_PERIOD
    # else:
    interval = "1d"
    period   = "60d"

    if ticker not in price_data_cache:
        data = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
        price_data_cache[ticker] = data
    else:
        data = price_data_cache[ticker]

    if data.empty or len(data) < LONG_W:
        return None, None

    data["Short_MA"] = data["Close"].rolling(window=SHORT_W).mean()
    data["Long_MA"]  = data["Close"].rolling(window=LONG_W).mean()
    data["Signal"]   = 0
    data.loc[data.index[SHORT_W:], "Signal"] = (
        data["Short_MA"].iloc[SHORT_W:] > data["Long_MA"].iloc[SHORT_W:]
    ).astype(int)
    data["Position"] = data["Signal"].diff()

    recent = data[data["Position"].isin([1, -1])]
    if recent.empty:
        return "HOLD", data["Close"].iloc[-1].item()
    last = recent.iloc[-1]
    sig  = "BUY" if last["Position"].item() == 1 else "SELL"
    return sig, last["Close"].item()

# ─── 5) CHECK BUY CANDIDATES ────────────────────────────────────────────────────
for t in to_buy:
    sig, price = last_signal(t)
    if sig == "BUY":
        buy_signals[t] = {"latest_price": round(price, 2), "signal": sig}

# ─── 6) CHECK SELL CANDIDATES ───────────────────────────────────────────────────
for t in to_sell:
    if t not in holdings:
        continue
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
