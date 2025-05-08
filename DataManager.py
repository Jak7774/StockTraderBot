import json
import os
import yfinance as yf
from datetime import datetime, date

CACHE_FILE = "price_cache.json"

def fetch_and_cache_prices(tickers, period="60d", interval="1d", force=False): # force=True to force update to cahce
    """
    Downloads price history for given tickers in batches, caches into JSON.
    Handles MultiIndex DataFrame and retries on rate limits.
    """
    today_str = date.today().isoformat()
    # Load existing cache if present
    if os.path.exists(CACHE_FILE) and not force:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        # Check if cache has data updated today
        # Inspect first ticker's dates
        for t in tickers:
            dates = cache.get(t, {}).get('dates', [])
            if dates and dates[-1] == today_str:
                continue
            else:
                # stale or missing data, force refresh
                force = True
                break
        if not force:
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
            'dates':  [str(idx.date()) for idx in df.index],
            'close':  df['Close'].round(2).tolist(),
            'high':   df['High'].round(2).tolist(),
            'low':    df['Low'].round(2).tolist(),
            'open':   df['Open'].round(2).tolist(),
            'volume': df['Volume'].astype(int).tolist()
        }

    # Write cache file
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    return cache


def load_cached_prices():
    """Loads cached price data from JSON."""
    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError("Cache file not found. Call fetch_and_cache_prices first.")
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)

def get_closes(ticker, cache=None):
    """
    Returns list of closing prices for a ticker from cache.
    """
    if cache is None:
        cache = load_cached_prices()
    return cache.get(ticker, {}).get('close', [])

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