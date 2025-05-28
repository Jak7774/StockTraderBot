#import yfinance as yf
from DataManager import load_cached_prices, get_current_price
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
price_cache = load_cached_prices(data_type="daily")

def df_from_cache(ticker):
    data = price_cache.get(ticker)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame({
        'Close': data['close']
    }, index=pd.to_datetime(data['dates']))
    return df

def last_signal(ticker):
    """Compute the MA crossover and stop-loss/profit signals for ticker."""
    df = df_from_cache(ticker)
    if df.empty or len(df) < LONG_W:
        print(f"{ticker}: Insufficient data ({len(df)} rows)")
        return None, None

    df['Short_MA'] = df['Close'].rolling(SHORT_W).mean()
    df['Long_MA']  = df['Close'].rolling(LONG_W).mean()
    df['Signal']   = 0
    df.loc[df.index[SHORT_W]:, 'Signal'] = (
        df['Short_MA'].iloc[SHORT_W:] > df['Long_MA'].iloc[SHORT_W:]
    ).astype(int)
    df['Position'] = df['Signal'].diff()

    # find last crossover
    recent = df[df['Position'].isin([1, -1])]
    if recent.empty:
        ma_sig = 'HOLD'
    else:
        last = recent.iloc[-1]
        ma_sig = 'BUY' if last['Position'] == 1 else 'SELL'

    # use current live price for signals
    current_price = get_current_price(ticker)

    # stop-loss / take-profit based on cost basis
    cb = cost_basis_map.get(ticker)
    if cb is not None:
        if current_price <= cb * (1 - STOP_LOSS_PCT) or \
           current_price >= cb * (1 + TAKE_PROFIT_PCT):
            return 'SELL', current_price

    # print(f"{t}: signal={ma_sig}, price={current_price}") # For Debugging - Check if Signals

    # otherwise MA-based
    if ma_sig in ['BUY', 'SELL']:
        return ma_sig, current_price
    return None, current_price

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
