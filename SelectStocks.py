# SelectStocks.py

import yfinance as yf
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
end_date = datetime.today()
start_date = end_date - timedelta(days=LOOKBACK_DAYS + 20)

price_data = yf.download(
    tickers=TICKERS,
    start=start_date.strftime("%Y-%m-%d"),
    end=end_date.strftime("%Y-%m-%d"),
    progress=True,
    auto_adjust=True,
    group_by="ticker"
)

# ─── 4) COMPUTE MOMENTUM ────────────────────────────────────────────────────────
momentum = {}
skipped = []

for t in TICKERS:
    try:
        if t not in price_data.columns.levels[0]:
            raise ValueError("No data downloaded")

        close = price_data[t]["Close"].dropna()

        if len(close) < LOOKBACK_DAYS + 1:
            raise ValueError("Not enough data")

        ref_price = close.iloc[-(LOOKBACK_DAYS + 1)].item()
        final_price = close.iloc[-1].item()
        mom_pct = (final_price / ref_price - 1) * 100

        momentum[t] = {
            "momentum_pct": round(mom_pct, 2),
            "window_used": f"{LOOKBACK_DAYS} trading days"
        }
    except Exception as e:
        skipped.append((t, str(e)))

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
