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
        'Close': data['close'],
        'High': data['high'],     
        'Low': data['low']       
    }, index=pd.to_datetime(data['dates']))
    return df

def calculate_macd(df):
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    return df

def calculate_rsi(close, period=14): # Relative Strength Index = momentum of how fast/far price has moved (0-100) 
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_adx(df, period=14): # Average Directional Index = Indicator of Trend (strong/weak) - but not direction (up/down)
    high = df['High']
    low = df['Low']
    close = df['Close']

    plus_dm = high.diff()
    minus_dm = low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = -minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(window=period).mean()

    return adx

def last_signal(ticker, cost_basis_map=None):
    """Compute the Cost Basis for ticker."""
    if cost_basis_map is None:
        try:
            with open("trades_log.json") as f:
                trades = json.load(f)
            data_trades = pd.DataFrame(trades)
            cost_basis_map = {}
            if not data_trades.empty and "ticker" in data_trades.columns:
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
        return None, None, None, None

    # ----  EMA Signals
    df['Short_EMA'] = df['Close'].ewm(span=SHORT_W, adjust=False).mean()
    df['Long_EMA'] = df['Close'].ewm(span=LONG_W, adjust=False).mean()
    df['Signal_EMA'] = 0
    df.loc[df.index[SHORT_W]:, 'Signal_EMA'] = (
        df['Short_EMA'].iloc[SHORT_W:] > df['Long_EMA'].iloc[SHORT_W:]
    ).astype(int)
    df['Position'] = df['Signal_EMA'].diff()

    # ---- MACD
    df = calculate_macd(df)
    last_macd = df.iloc[-2]['MACD_Hist']
    curr_macd = df.iloc[-1]['MACD_Hist']
    macd_cross_up = curr_macd > 0 and last_macd <= 0
    macd_cross_down = curr_macd < 0 and last_macd >= 0

    # Calculate RSI
    df['RSI'] = calculate_rsi(df['Close'])

    # Bollinger Bands 
    ma = df['Close'].rolling(window=20).mean()
    std = df['Close'].rolling(window=20).std()
    df['BB_upper'] = ma + (2 * std)
    df['BB_lower'] = ma - (2 * std)

    # Decide Market Type
    df['ADX'] = calculate_adx(df)
    market_type = "TRENDING" if df['ADX'].iloc[-1] >= 20 else "SIDEWAYS" # threshold of <20 for Sideways Market
    
    # use current live price for signals
    current_price = get_current_price(ticker)
    cb = cost_basis_map.get(ticker)

    # ─── SELL LOGIC ─────────────────────────────────────
    # Dynamnic Stop Percentages
    df['TR'] = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)
    # Dynamic Period based on last 5 days - if not volatile use base (14 days) - else adjust
    recent_volatility = df['TR'].rolling(window=5).std().iloc[-1]
    base_window = 14
    adj_window = max(10, min(30, int(base_window * (1 + recent_volatility / df['TR'].mean()))))
    df['ATR'] = df['TR'].rolling(window=adj_window).mean()

    atr = df['ATR'].iloc[-1]
    if atr is None or pd.isna(atr):
        atr = 0  # fallback

    if cb is not None:
        peak = df['Close'].max()

        # Dynamic Trailing Stop
        if peak - current_price >= 2 * atr:
            return 'SELL', current_price, market_type, "trailing_stop"
        #if current_price <= peak * (1 - TRAIL_STOP_PCT):
        #    return 'SELL', current_price, market_type
        
        # Dynamic Stop Loss
        if cb - current_price >= 3 * atr:
            return 'SELL', current_price, market_type, "stop_loss"
        #if current_price <= cb * (1 - STOP_LOSS_PCT):
        #    return 'SELL', current_price, market_type
        
        if current_price >= cb * (1 + TAKE_PROFIT_PCT):
            return 'SELL', current_price, market_type, "take_profit"

    # ─── STRATEGY SWITCHING ──────────────────────────────────

    if market_type == "TRENDING": # Continual Trend Up - Reliable MACD/EMA signals
        # Trend-Based Sell
        if df['Position'].iloc[-1] == -1 and macd_cross_down:
            return 'SELL', current_price, market_type, "ema_macd_crossover"
        # Trend-Based Buy
        recent = df[df['Position'].isin([1, -1])]
        if not recent.empty:
            last = recent.iloc[-1]
            if last['Position'] == 1 and macd_cross_up:
                # Check RSI not overbrought 
                if df['RSI'].iloc[-1] > 65:
                    #print(f"{ticker}: Skipping TRENDING BUY — RSI too high")
                    return None, current_price, market_type, "rsi_overbrought"
                # Price not >5% than short EMA - as likely indicates a peak
                if current_price > df['Short_EMA'].iloc[-1] * 1.05:
                    #print(f"{ticker}: Skipping TRENDING BUY — price extended above EMA")
                    return None, current_price, market_type, "extended_over_ema"
                # Skip if price is >5% above yesterday’s close
                if df['Close'].iloc[-1] > df['Close'].iloc[-2] * 1.05:
                    #print(f"{ticker}: Skipping — large daily gain, wait for pullback")
                    return None, current_price, market_type, "extended_over_close"
                return 'BUY', current_price, market_type, "trend_buy"
            
    elif market_type == "SIDEWAYS": # Market Bouncing Around - Need RSI/Bollinger bands to buy low sell high
        last_rsi = df['RSI'].iloc[-1]
        last_close = df['Close'].iloc[-1]
        upper_band = df['BB_upper'].iloc[-1]
        lower_band = df['BB_lower'].iloc[-1]

        # Sideways Buy: Oversold + below lower band
        if last_rsi < 30 and last_close < lower_band:
            return 'BUY', current_price, market_type, "rsi_below_band"

        # Sideways Sell: Overbought + above upper band
        if last_rsi > 70 and last_close > upper_band:
            return 'SELL', current_price, market_type, "rsi_above_band"

    # Print Out Positions to see which are close    
    #print(f"{ticker}: Position={last['Position']} | MACD hist: {last_macd:.4f} → {curr_macd:.4f}")
        
    return None, current_price, market_type, None


def main():

    # ─── 1) LOAD CURRENT HOLDINGS ───────────────────────────────────────────────────
    with open("ftse100_stocks.json", "r") as f:
        ftse100 = json.load(f)

    TICKERS = [
        f"{stock['code'].rstrip('.').replace('.', '-')}.L"
        for stock in ftse100
        if stock.get("code")
    ]
    
    try:
        with open("portfolio_summary.json") as f:
            holdings = set(json.load(f).get("holdings", {}).keys())
    except FileNotFoundError:
        holdings = set()

    # ─── 2) LOAD TRADES  ────────────────────────────────────
    market_type_count = {
        "BUY": {"TRENDING": 0, "SIDEWAYS": 0},
        "SELL": {"TRENDING": 0, "SIDEWAYS": 0}
    }

    today = datetime.today().date()
    buys_today = {}
    recent_sells = {}
    recent_losses = {}

    try:
        with open("trades_log.json") as f:
            trades = json.load(f)
            for trade in trades:
                trade_date = datetime.fromisoformat(trade["date"]).date()
                ticker = trade["ticker"]
                if trade["action"] == "BUY" and trade_date == today:
                    buys_today[ticker] = trade["price"]
                elif trade["action"] == "SELL":
                    # Track recent sells for price comparison
                    if (today - trade_date).days <= 3:
                        if ticker not in recent_sells:
                            recent_sells[ticker] = []
                        recent_sells[ticker].append(trade["price"])

                    # Identify if the SELL was at a loss 
                    all_buys = [
                        t for t in trades 
                        if t["ticker"] == ticker and t["action"] == "BUY" 
                        and datetime.fromisoformat(t["date"]).date() <= trade_date
                    ]
                    if all_buys:
                        last_buy = max(all_buys, key=lambda t: datetime.fromisoformat(t["date"]))
                        pnl = trade["price"] - last_buy["price"]
                        if pnl < 0:
                            # Save the loss date for cool-off logic
                            recent_losses[ticker] = trade_date
    except (FileNotFoundError, ValueError):
        pass

    # ─── 3) LOAD TODAY'S SCREEN & SELLS ─────────────────────────────────────────────────
    to_buy = [t for t in TICKERS if t not in holdings]
    to_sell = list(holdings) # Use Current Holdings (not daily_screen)

    print(f"Candidates to BUY : {to_buy}")
    print(f"Candidates to SELL (from current holdings): {to_sell}\n")

    # ─── 4) SCRIPT PARAMETERS ───────────────────────────────────────────────────────
    buy_signals  = {}
    sell_signals = {}

    # ─── 5) CHECK BUY CANDIDATES ────────────────────────────────────────────────────
    for t in to_buy:
        sig, price, market_type, trigger = last_signal(t)
        if market_type:
            market_type_count["BUY"][market_type] += 1

        if sig == "BUY":
            if price is None:
                continue

            # Rule 1: Dynamic cool-off period if recent loss
            if t in recent_losses:
                days_since_loss = (today - recent_losses[t]).days
                if days_since_loss < 5:  # You can customise this number
                    print(f"Skipping {t}: recent loss ({days_since_loss}d ago) → extended cool-off in effect")
                    continue
                else:
                    print(f"{t}: recent loss detected ({days_since_loss}d ago) → cool-off satisfied")

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

            buy_signals[t] = {"latest_price": round(price, 2), "signal": sig, "trigger": trigger}


    # ─── 6) CHECK ALL CURRENT HOLDINGS FOR SELL SIGNALS ─────────────────────────────
    if holdings:
        for t in holdings:
            sig, price, market_type, trigger = last_signal(t)
            if market_type:
                market_type_count["SELL"][market_type] += 1

            if t in buys_today:
                # Allow override if the sell is urgent (trailing stop / stop loss / take profit)
                if sig == "SELL":
                    print(f"⚠️ {t}: Bought today, but urgent SELL signal detected → overriding cooldown.")
                    sell_signals[t] = {"latest_price": round(price, 2), "signal": sig}
                else:
                    print(f"Skipping {t}: bought today → 1-day cooldown in effect")
                    continue
            elif sig == "SELL":
                sell_signals[t] = {"latest_price": round(price, 2), "signal": sig, "trigger": trigger}
    else:
        print("⚠️ No holdings found — skipping SELL signal logic.")

    # ─── 7) SAVE TRADE SIGNALS ─────────────────────────────────────────────────────
    out = {
        "buy_signals":  buy_signals,
        "sell_signals": sell_signals
    }

    print("\n📊 Market Type Summary:")
    for category in ["BUY", "SELL"]:
        print(f"  {category}:")
        for mtype in ["TRENDING", "SIDEWAYS"]:
            print(f"    {mtype}: {market_type_count[category][mtype]} stocks")

    with open("trade_signals.json", "w") as f:
        json.dump(out, f, indent=4)

    print("\n✅ trade_signals.json written")


# ─── 8) RUN FUNCTION  ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()