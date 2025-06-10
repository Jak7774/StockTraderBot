import json
import os
import yfinance as yf
from datetime import datetime, time
import pandas as pd

CACHE_FILE = "price_cache.json"
INTRADAY_VALID_FROM = time(8, 30)  # 08:30 AM

def fetch_and_cache_prices(tickers, period="60d", interval="1d", intraday=False, intraday_interval="5m", force=False): # force=True to force update to cahce
    """
    Downloads price history for given tickers in batches, caches into JSON.
    Handles MultiIndex DataFrame and retries on rate limits.
    Optional Intraday Download for assessing trends (defer sells)
    """
    # Load existing cache if present
    if os.path.exists(CACHE_FILE) and not force:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
            return cache

    # Fetch historical data in a single call to yfinance
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        group_by='ticker'
    )

    # Determine which tickers returned data
    if hasattr(raw.columns, 'levels') and raw.columns.nlevels == 2:
        # MultiIndex case
        present = list(raw.columns.get_level_values(0).unique())
    else:
        # Flat-index: assume all tickers share this one DataFrame
        present = tickers

    cache = {}
    for t in tickers:
        if t not in present:
            # no data returned for this ticker
            cache[t] = {field: [] for field in ['dates','close','high','low','open','volume']}
            print(f"[Warning] No data for ticker {t}")
            continue
        # Extract DataFrame slice for ticker
        if hasattr(raw.columns, 'levels') and raw.columns.nlevels == 2:
            df = raw.xs(t, axis=1, level=0).dropna()
        else:
            df = raw.dropna()

        # Serialize
        cache[t] = {
            'daily': {
                'dates':  [str(idx.date()) for idx in df.index],
                'close':  df['Close'].round(2).tolist(),
                'high':   df['High'].round(2).tolist(),
                'low':    df['Low'].round(2).tolist(),
                'open':   df['Open'].round(2).tolist(),
                'volume': df['Volume'].astype(int).tolist()
            }
        }

        # Fetch intraday data if requested
        now = datetime.now().time()
        timeflag = False
        if intraday & (now >= INTRADAY_VALID_FROM):
            timeflag = True
            try:
                df_intra = yf.download(
                    tickers=t,
                    period="1d",
                    interval=intraday_interval,
                    auto_adjust=True,
                    progress=False
                )

                if not df_intra.empty:
                    close_prices = df_intra[('Close', t)]
                    intraday_data = [
                        (str(ts), round(float(close), 2))
                        for ts, close in zip(df_intra.index, close_prices)
                        if not pd.isna(close)
                    ]

                    cache[t]['intraday'] = {
                        'datetime': [entry[0] for entry in intraday_data],
                        'price':    [entry[1] for entry in intraday_data]
                    }
            except Exception as e:
                print(f"[Warning] Could not fetch intraday for {t}: {e}")
        
    if timeflag == False:
        print(f"⏳ Skipping - Intraday Logic (market opened recently)")

    # Write cache file
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    return cache

# To assess trends in the day (if requested in cache)
def get_intraday_prices(ticker, cache=None):
    """
    Returns intraday prices [(datetime, close)] from cache.
    """
    if cache is None:
        data = load_cached_prices(data_type="intraday")
        if ticker in data:
            inner_data = data[ticker]
            if 'datetime' in inner_data and 'price' in inner_data:
                return [(datetime.fromisoformat(ts), price) for ts, price in zip(inner_data['datetime'], inner_data['price'])]
            else:
                print("Missing keys in inner data:", inner_data)
        else:
            print(f"Ticker '{ticker}' not found in data:", data)

        return []

def load_cached_prices(data_type="both"):
    """
    Loads cached price data from JSON.
    
    Parameters:
    - data_type: "daily", "intraday", or "both"
    
    Returns:
    - A filtered dictionary containing only the requested data type(s)
    """
    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError("Cache file not found. Call fetch_and_cache_prices first.")
    
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)

    if data_type == "both":
        return cache
    
    if data_type not in {"daily", "intraday"}:
        raise ValueError("data_type must be 'daily', 'intraday', or 'both'")
    
    # Return only the requested part
    filtered = {}
    for ticker, data in cache.items():
        filtered[ticker] = data.get(data_type, {})
    
    return filtered


def get_closes(ticker, cache=None):
    """
    Returns list of closing prices for a ticker from cache.
    """
    if cache is None:
        cache = load_cached_prices(data_type="daily")
    return cache.get(ticker, {}).get('close', [])

def get_current_price(ticker):
    t = yf.Ticker(ticker)
    try:
        return t.fast_info.last_price
    except Exception:
        return t.info.get('regularMarketPrice')

# For Debugging
#ftse100 = pd.read_csv("ftse100_constituents.csv")
#UNIVERSE = [f"{s}.L" for s in ftse100["Symbol"].dropna().unique()]
# Cache 60 days daily history for all symbols
#fetch_and_cache_prices(UNIVERSE, period="60d", interval="1d")
#fetch_and_cache_prices(UNIVERSE, period="60d", interval="1d", force=True, intraday=True) # Force = Ensure Latest values downloaded