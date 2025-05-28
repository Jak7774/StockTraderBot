import json
import os
import yfinance as yf
import datetime

CACHE_FILE = "price_cache.json"

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
        if intraday:
            try:
                df_intra = yf.download(
                    tickers=t,
                    period="1d",
                    interval=intraday_interval,
                    auto_adjust=True,
                    progress=False
                )
                if not df_intra.empty:
                    cache[t]['intraday'] = [
                        [ts.isoformat(), round(row['Close'], 2)]
                        for ts, row in df_intra.iterrows()
                    ]
            except Exception as e:
                print(f"[Warning] Could not fetch intraday for {t}: {e}")

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
        cache = load_cached_prices(data_type="intraday")
    data = cache.get(ticker, {}).get('intraday', [])
    return [(datetime.fromisoformat(ts), price) for ts, price in data]

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
    return cache.get(ticker, {}).get('daily', {}).get('close', [])

def get_current_price(ticker):
    t = yf.Ticker(ticker)
    try:
        return t.fast_info.last_price
    except Exception:
        return t.info.get('regularMarketPrice')

# For Debugging
# import pandas as pd
# ftse100 = pd.read_csv("ftse100_constituents.csv")
# UNIVERSE = [f"{s}.L" for s in ftse100["Symbol"].dropna().unique()]
# # Cache 60 days daily history for all symbols
# fetch_and_cache_prices(UNIVERSE, period="60d", interval="1d")