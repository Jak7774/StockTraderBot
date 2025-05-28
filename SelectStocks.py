# SelectStocks.py

#import yfinance as yf # One Cached Call in DataManager (reduce requests)
from DataManager import load_cached_prices, get_current_price
import pandas as pd
import json
from datetime import datetime, timedelta, date

# ─── 1) YOUR UNIVERSE ───────────────────────────────────────────────────────────
ftse100 = pd.read_csv("ftse100_constituents.csv")  
TICKERS = ftse100["Symbol"].dropna().unique().tolist()
TICKERS = [f"{symbol}.L" for symbol in TICKERS] # Add .L for the UK version only stocks (some might throw errors)

#sp500 = pd.read_csv("sp500_constituents.csv")  
#TICKERS = sp500["Symbol"].dropna().unique().tolist()

LOOKBACK_DAYS = 30
TOP_N = 100
OUTPUT_JSON = "daily_screen.json"

# ─── 2) LOAD CURRENT HOLDINGS ───────────────────────────────────────────────────
try:
    with open("portfolio_summary.json") as f:
        holdings = set(json.load(f).get("holdings", {}).keys())
except FileNotFoundError:
    holdings = set()

# ─── 3) DOWNLOAD HISTORICAL DATA ────────────────────────────────────────────────
price_cache = load_cached_prices(data_type="daily") # From DataManager

# ─── 4) COMPUTE MOMENTUM ────────────────────────────────────────────────────────
momentum = {}
skipped = []

for t in TICKERS:
    # pull the list of daily closes from our JSON cache
    closes = price_cache.get(t, {}).get("close", [])
    # need at least LOOKBACK_DAYS+1 closes to compute momentum
    if len(closes) < LOOKBACK_DAYS + 1:
        skipped.append((t, "not enough history"))
        continue

    # oldest reference price is LOOKBACK_DAYS+1 ago
    ref_price   = closes[-(LOOKBACK_DAYS + 1)]
    final_price = closes[-1]
    mom_pct     = (final_price / ref_price - 1) * 100

    momentum[t] = {
        "momentum_pct": round(mom_pct, 2),
        "window_used": f"{LOOKBACK_DAYS} trading days"
    }

# ─── 5) RANK AND PICK TOP N ─────────────────────────────────────────────────────
ranked = sorted(momentum.items(), key=lambda x: x[1]["momentum_pct"], reverse=True)
top100 = [ticker for ticker, _ in ranked[:TOP_N]]

# ─── 6) DECIDE BUY / SELL ───────────────────────────────────────────────────────
to_buy = [t for t in top100 if t not in holdings and momentum[t]["momentum_pct"] > 0]
to_sell = [
    t for t in holdings
    if (t not in top100) or (momentum.get(t, {"momentum_pct": 0})["momentum_pct"] < 0)
]

# ─── 7) SAVE DAILY SCREEN ──────────────────────────────────────────────────────
out = {
    "date": datetime.today().strftime("%Y-%m-%d"),
    "top_100": ranked[:TOP_N],
    "to_buy": to_buy,
    "to_sell": to_sell,
    "momentum": {t: momentum[t]["momentum_pct"] for t in top100},
    "skipped": skipped
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(out, f, indent=2)

print(f"Screened {len(TICKERS)} tickers → buy {len(to_buy)}, sell {len(to_sell)}.")

# Save today's date so we know when this was last run
with open("selectstocks_last_run.txt", "w") as f:
    f.write(str(date.today()))
