#import yfinance as yf
from DataManager import load_cached_prices, get_current_price
import pandas as pd
import json
from datetime import datetime, timedelta

# ─── 0) Global Parameters & Functions ───────────────────────────────────────────
# Added outside main() function to be used by other scripts

SHORT_W = 5 
LONG_W  = 20
REQUIRED_LOOKBACK = max(LONG_W, 35) # MACD Logic needs at least 26 days + 9 days = 35

# Parameters to Sell if Rapid changes (not detected by Moving Averages)
TRAIL_STOP_PCT = 0.05  # sell if price falls 5% from peak
STOP_LOSS_PCT   = 0.10   # e.g. 10% drop
TAKE_PROFIT_PCT= 0.15   # e.g. 15% gain

price_cache = load_cached_prices(data_type="daily")

def df_from_cache(ticker):
    data = price_cache.get(ticker)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame({
        'Close': data['close']
    }, index=pd.to_datetime(data['dates']))
    return df

def calculate_macd(df):
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    return df

def last_signal(ticker, cost_basis_map=None):
    """Compute the Cost Basis for ticker."""
    if cost_basis_map is None:
        try:
            with open("trades_log.json") as f:
                trades = json.load(f)
            data_trades = pd.DataFrame(trades)
            cost_basis_map = {}
            for ticker_name, sub in data_trades.groupby("ticker"):
                buys = sub[sub["action"] == "BUY"]
                sells = sub[sub["action"] == "SELL"]
                net_shares = buys["shares"].sum() - sells["shares"].sum()
                net_cost = (buys["shares"] * buys["price"]).sum() - (sells["shares"] * sells["price"]).sum()
                if net_shares > 0:
                    cost_basis_map[ticker_name] = net_cost / net_shares
        except (FileNotFoundError, ValueError):
            cost_basis_map = {}

    """Compute the Signlas for ticker."""
    df = df_from_cache(ticker)
    if df.empty or len(df) < REQUIRED_LOOKBACK:
        print(f"{ticker}: Insufficient data ({len(df)} rows)")
        return None, None

    df['Short_EMA'] = df['Close'].ewm(span=SHORT_W, adjust=False).mean()
    df['Long_EMA'] = df['Close'].ewm(span=LONG_W, adjust=False).mean()
    df['Signal_EMA'] = 0
    df.loc[df.index[SHORT_W]:, 'Signal_EMA'] = (
        df['Short_EMA'].iloc[SHORT_W:] > df['Long_EMA'].iloc[SHORT_W:]
    ).astype(int)
    df['Position'] = df['Signal_EMA'].diff()

    # MACD
    df = calculate_macd(df)
    last_macd = df.iloc[-2]['MACD_Hist']
    curr_macd = df.iloc[-1]['MACD_Hist']
    macd_cross = curr_macd > 0 and last_macd <= 0

    # use current live price for signals
    current_price = get_current_price(ticker)

    # stop-loss / take-profit based on cost basis
    cb = cost_basis_map.get(ticker)
    if cb is not None:
        # Trailing Stop-Loss (ratchets up as price increases)
        peak = df['Close'].max()
        if current_price <= peak * (1 - TRAIL_STOP_PCT):
            return 'SELL', current_price

        # Stop-loss or take-profit        
        if current_price <= cb * (1 - STOP_LOSS_PCT) or \
           current_price >= cb * (1 + TAKE_PROFIT_PCT):
            return 'SELL', current_price

    # print(f"{t}: signal={ma_sig}, price={current_price}") # For Debugging - Check if Signals

    # Buy if crossover + MACD confirms
    recent = df[df['Position'].isin([1, -1])]
    if not recent.empty:
        last = recent.iloc[-1]
        if last['Position'] == 1 and macd_cross:
            return 'BUY', current_price
        
    return None, current_price


def main():

    # ─── 1) LOAD CURRENT HOLDINGS ───────────────────────────────────────────────────
    try:
        with open("portfolio_summary.json") as f:
            holdings = set(json.load(f).get("holdings", {}).keys())
    except FileNotFoundError:
        holdings = set()

    # ─── 2) LOAD TRADES AND BUILD COST BASIS MAP ────────────────────────────────────
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

    # ─── 3) LOAD TODAY'S SCREEN & SELLS ─────────────────────────────────────────────────
        # Track buys and sells
    today = datetime.today().date()
    buys_today = {}
    recent_sells = {}

    try:
        with open("trades_log.json") as f:
            trades = json.load(f)
            for trade in trades:
                trade_date = datetime.fromisoformat(trade["date"]).date()
                ticker = trade["ticker"]
                if trade["action"] == "BUY" and trade_date == today:
                    buys_today[ticker] = trade["price"]
                elif trade["action"] == "SELL" and (today - trade_date).days <= 3:
                    if ticker not in recent_sells:
                        recent_sells[ticker] = []
                    recent_sells[ticker].append(trade["price"])
    except (FileNotFoundError, ValueError):
        pass

    with open("daily_screen.json", "r") as f:
        screen = json.load(f)

    to_buy = screen.get("to_buy", [])
    to_sell = list(holdings) # Use Current Holdings (not daily_screen)

    print(f"Candidates to BUY : {to_buy}")
    print(f"Candidates to SELL (from current holdings): {to_sell}\n")

    # ─── 4) SCRIPT PARAMETERS ───────────────────────────────────────────────────────
    buy_signals  = {}
    sell_signals = {}

    # ─── 5) CHECK BUY CANDIDATES ────────────────────────────────────────────────────
    for t in to_buy:
        sig, price = last_signal(t)

        if price is None:
            continue

        # Rule 1: Positive momentum > 2%
        momentum_pct = screen["momentum"].get(t, 0)
        if momentum_pct <= 2:
            print(f"Skipping {t}: momentum {momentum_pct:.2f}% not > 2%")
            continue

        # Rule 2: Price jump can't be more than 10% from today's open
        closes = price_cache.get(t, {}).get("close", [])
        if len(closes) < 2:
            print(f"Skipping {t}: not enough price history")
            continue
        todays_open = closes[-1]  # assume today's open = today's close (no real open price)
        if price > todays_open * 1.10: # if > 10% then missed price increase so don't bother buy (too late)
            print(f"Skipping {t}: current price {price:.2f} is more than 10% above today's open {todays_open:.2f}")
            continue

        # Rule 3: At least 5% lower than recent sell price (last 3 days)
        if t in recent_sells:
            if all(price >= s * 0.95 for s in recent_sells[t]):
                print(f"Skipping {t}: not at least 5% cheaper than recent sells")
                continue

        if sig == "BUY":
            buy_signals[t] = {"latest_price": round(price, 2), "signal": sig}


    # ─── 6) CHECK ALL CURRENT HOLDINGS FOR SELL SIGNALS ─────────────────────────────
    for t in holdings:
        if t in buys_today:
            print(f"Skipping {t}: bought today → 1-day cooldown in effect")
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


# ─── 8) RUN FUNCTION  ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()