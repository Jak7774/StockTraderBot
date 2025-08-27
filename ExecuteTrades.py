# ExecuteTrades.py
import time
import json
import os
from datetime import date, datetime, time
#import yfinance as yf
from DataManager import get_current_price, get_closes, get_intraday_prices 
import tempfile # Writing JSON files (avoid issues when run multiple instances of script)
from sklearn.linear_model import LinearRegression
import numpy as np

# ─── 1) SETTINGS ────────────────────────────────────────────────────────────────
PORTFOLIO_FILE = "portfolio_summary.json"
TRADES_LOG     = "trades_log.json"
SIGNALS_FILE   = "trade_signals.json"
SCREEN_FILE    = "daily_screen.json"
DEFERRED_SELLS_FILE = "deferred_sells.json"
CLEAN_THRESHOLD_DAYS = 5  # How many days before we remove old deferred sells?
INITIAL_CASH   = 10_000
MAX_ALLOC      = 0.30  # 30% cap per ticker
MIN_ALLOC      = 0.01  # 1% floor per ticker
ALLOW_FRACTIONAL = True  # Toggle for fractional share buying
TREND_SLOPE_THRESHOLD = 0.05  # Change to suit trends
INTRADAY_VALID_FROM = time(8, 30)  # 08:30 AM

# Load File - Check if currently being written to
def load_json_with_retry(filepath, retries=5, delay=5):
    """Attempt to load JSON from a file, retrying on failure."""
    for attempt in range(retries):
        try:
            with open(filepath) as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
            print(f"⚠️ Error reading {filepath}: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"❌ Failed to load {filepath} after {retries} attempts.")

# Tempfile Writing (save issues with concurrency)
def atomic_write_json(data, filepath):
    """Write JSON to a temporary file, then replace the original file atomically."""
    dir_name = os.path.dirname(os.path.abspath(filepath)) or "."
    with tempfile.NamedTemporaryFile('w', delete=False, dir=dir_name, suffix=".tmp") as tmp:
        json.dump(data, tmp, indent=2)
        tempname = tmp.name
    os.replace(tempname, filepath)

# ─── 2) LOAD OR INIT PORTFOLIO ──────────────────────────────────────────────────
if os.path.exists(PORTFOLIO_FILE):
    summary = load_json_with_retry(PORTFOLIO_FILE)
    cash     = summary.get("cash", INITIAL_CASH)
    holdings = summary.get("holdings", {})
    history  = summary.get("history", [])
else:
    cash     = INITIAL_CASH
    holdings = {}
    history  = []

# ─── 3) LOAD SIGNALS & SCREEN ───────────────────────────────────────────────────
sigs = load_json_with_retry(SIGNALS_FILE)
buy_sigs  = sigs.get("buy_signals", {})
sell_sigs = sigs.get("sell_signals", {})

screen = load_json_with_retry(SCREEN_FILE)
momentum_map = screen.get("momentum", {})

# ─── 3B) CREATE PRICE CACHE ─────────────────────────────────────────────────────
tickers_needed = set(buy_sigs) | set(sell_sigs) | set(holdings)
price_cache = {t: get_current_price(t) for t in tickers_needed}

# ─── 4) LOAD OR INIT TRADE LOG ──────────────────────────────────────────────────
if os.path.exists(TRADES_LOG):
    trade_log = load_json_with_retry(TRADES_LOG)
else:
    trade_log = []

# ─── 5) EXECUTE SELLS (WITH DEFERRED IF MOMENTUM POSITIVE) ──────────────────────

def is_trending_up(intraday_prices):
    """
    Estimate trend using linear regression.
    intraday_prices: list of (timestamp, price) tuples
    Returns True if the slope indicates upward trend.
    """
    if len(intraday_prices) < 5:
        return False  # not enough data

    # Convert times to numeric values (minutes since open)
    times = np.array([(dt - intraday_prices[0][0]).total_seconds() / 60 for dt, _ in intraday_prices]).reshape(-1, 1)
    prices = np.array([p for _, p in intraday_prices])

    # Linear regression
    model = LinearRegression()
    model.fit(times, prices)
    slope = model.coef_[0]

    return slope >= TREND_SLOPE_THRESHOLD


# Load existing deferred sells (if any)
if os.path.exists(DEFERRED_SELLS_FILE):
    deferred_sells = load_json_with_retry(DEFERRED_SELLS_FILE)
else:
    deferred_sells = {}


now = datetime.now().time()

for tkr, info in sell_sigs.items():
    
    # Momentum Only Updated Daily
    momentum = momentum_map.get(tkr, 0)

    # Reason for Sell
    trigger = info.get("trigger", "unspecified")  

    # Get today's current and last close price
    current_price = get_current_price(tkr)
    closes = get_closes(tkr)
    last_close_price = closes[-1] if closes else 0

    if now >= INTRADAY_VALID_FROM:

        # Optional: Load intraday price data
        try:
            intraday_prices = get_intraday_prices(tkr)  # List of (datetime, price)
        except Exception as e:
            print(f"Skipping {tkr}: failed to load intraday prices ({e})")
            continue

        # Skip if intraday_prices is missing or invalid
        if not intraday_prices or not all(len(p) == 2 for p in intraday_prices):
            print(f"Skipping {tkr}: intraday data is missing or invalid")
            continue

        try:
            if current_price > last_close_price * 1.01 and is_trending_up(intraday_prices): # Delay if >1% threshold increase and slope trending up
                percent_change = ((current_price - last_close_price) / last_close_price) * 100
                # Defer selling stocks still trending upward
                deferred_sells[tkr] = {
                    "latest_price": current_price,
                    "momentum": momentum,
                    "date_flagged": str(date.today())
                }
                print(f"⏩ Deferred selling {tkr}: positive momentum ({momentum:.2f})")
                continue
        except Exception as e:
            print(f"Error processing {tkr}: {e}")
    else:
        print(f"⏳ Skipping - Intraday Logic ({tkr} (market just opened)")

    # Otherwise, sell normally
    if tkr in holdings:
        shares = holdings.pop(tkr)
        price  = current_price
        cash  += shares * price
        trade_log.append({
            "ticker": tkr,
            "action": "SELL",
            "trigger": trigger,
            "date":   datetime.now().isoformat(),
            "price":  price,
            "shares": shares
        })
        print(f"Sold {shares} of {tkr} @ ${price:.2f}")
    else:
        print(f"⚠️ Tried to sell {tkr}, but it's not in holdings.")

# Save updated deferred sells
atomic_write_json(deferred_sells, DEFERRED_SELLS_FILE)
print(f"\n📄 Deferred sells updated in {DEFERRED_SELLS_FILE} ({len(deferred_sells)} tickers)")

# ─── 5B) AUTO-CLEAN OLD OR INVALID DEFERRED SELLS ───────────────────────────────
cleaned_deferred_sells = {}
today = date.today()

for tkr, record in deferred_sells.items():
    try:
        flagged_date = datetime.strptime(record["date_flagged"], "%Y-%m-%d").date()
    except Exception as e:
        print(f"⚠️ Skipping {tkr} due to invalid date format: {e}")
        continue

    age_days = (today - flagged_date).days

    # Only keep deferred sells if:
    # 1) Ticker is still in holdings
    # 2) Flagged within CLEAN_THRESHOLD_DAYS
    if tkr in holdings and age_days <= CLEAN_THRESHOLD_DAYS:
        cleaned_deferred_sells[tkr] = record
    else:
        reason = []
        if tkr not in holdings:
            reason.append("not in holdings")
        if age_days > CLEAN_THRESHOLD_DAYS:
            reason.append(f"deferred {age_days} days ago")
        print(f"🧹 Removing {tkr} from deferred sells ({' and '.join(reason)})")

# Save cleaned deferred sells
atomic_write_json(cleaned_deferred_sells, DEFERRED_SELLS_FILE)
print(f"\n🧽 Deferred sells cleaned: {len(cleaned_deferred_sells)} active tickers remain")

# ─── 6) EXECUTE BUYS (MOMENTUM WEIGHTED + CAP + MIN + GREEDY) ──────────────────
buy_list = [t for t in buy_sigs if t in momentum_map and momentum_map[t] > 0]
start_cash = cash

summary = {
    "bought": [],
    "skipped": [],
    "opportunistic": [],
    "no_alloc": False,
    "no_signals": False,
}

if buy_list:
    m_vals = {t: momentum_map[t] for t in buy_list}
    total_m = sum(m_vals.values())
    raw_w = {t: m_vals[t] / total_m for t in buy_list}

    # Cap weights at MAX_ALLOC
    capped, overflow = {}, 0.0
    for t, w in raw_w.items():
        if w > MAX_ALLOC:
            capped[t] = MAX_ALLOC
            overflow += w - MAX_ALLOC
        else:
            capped[t] = w

    # Redistribute overflow
    uncapped = {t: w for t, w in capped.items() if w < MAX_ALLOC}
    unc_total = sum(uncapped.values())
    if uncapped and overflow > 0:
        for t in uncapped:
            capped[t] += (capped[t] / unc_total) * overflow

    # Normalize and apply MIN_ALLOC
    tot_w = sum(capped.values())
    final_w = {t: w / tot_w for t, w in capped.items()}
    alloc_univ = {t: w for t, w in final_w.items() if w >= MIN_ALLOC}

    if alloc_univ:
        s = sum(alloc_univ.values())
        final_w = {t: w / s for t, w in alloc_univ.items()}

        for t, w in final_w.items():
            info = buy_sigs[t]
            trigger = info.get("trigger", "unspecified") # Reason for Buy
            alloc = w * start_cash
            price = info["latest_price"]

            if ALLOW_FRACTIONAL:
                shares = round(alloc/price,6)
                shares = round(shares,3) if shares>=0.001 else 0
            else:
                shares = int(alloc//price)
            if shares<=0 or shares*price>cash:
                summary['skipped'].append((t,alloc,price))
                continue

            cash -= shares*price
            holdings[t] = round(holdings.get(t, 0) + shares, 3)
            trade_log.append({
                "ticker": t,
                "action": "BUY",
                "trigger": trigger,
                "date": datetime.now().isoformat(),
                "price": price,
                "shares": shares
            })
            print(f"Bought {shares} of {t} @ ${price:.2f}")
            summary["bought"].append((t, shares, price))

        # Opportunistic buys
        price_map = {t:price_cache[t] for t in set(holdings)|set(buy_list)}

        while True:
            total_val = cash + sum(get_current_price(t)*s for t,s in holdings.items())
            viable = {t:p for t,p in price_map.items() if p>0 and cash>=(0.01 if ALLOW_FRACTIONAL else p)}
            if not viable: break
            pick,price = min(viable.items(),key=lambda kv:kv[1])
            if ALLOW_FRACTIONAL:
                max_inv = min(cash,(MAX_ALLOC*total_val)-holdings.get(pick,0)*price)
                shares = round(max_inv/price,3) if max_inv/price>=0.001 else 0
            else:
                shares = 1 if price<=cash else 0
            if shares<=0 or shares*price>cash: break
            cash-=shares*price
            holdings[pick]=round(holdings.get(pick,0)+shares,3)
            trade_log.append({
                "ticker":pick,
                "action":"BUY",
                "trigger": "opportunistic",
                "date": datetime.now().isoformat(),
                "price":price,
                "shares":shares
            })
            print(f"Bought {shares} of {pick} @ ${price:.2f} (opportunistic)")
            summary['opportunistic'].append((pick,price,shares))
    else:
        summary['no_alloc'] = True
else:
    summary['no_signals'] = True

# ─── PRINT SUMMARY ──────────────────────────────────────────────────────────────
# print("\n=== Buy Summary ===")
# if summary["no_signals"]:
#     print("No positive-momentum buy signals to execute.")
# elif summary["no_alloc"]:
#     print("⚠️ No tickers met the 1% min allocation threshold.")
# else:
#     if summary["bought"]:
#         print(f"✅ Bought: {len(summary['bought'])} tickers")
#         for t, s, p in summary["bought"]:
#             print(f"  - {t}: {s} shares @ ${p:.2f}")
#     if summary["skipped"]:
#         print(f"⚠️ Skipped (alloc < price): {len(summary['skipped'])}")
#         for t, alloc, price in summary["skipped"]:
#             print(f"  - {t}: alloc ${alloc:.2f} < price ${price:.2f}")
#     if summary["opportunistic"]:
#         print(f"💡 Opportunistic buys: {len(summary['opportunistic'])}")
#         for t, p, s in summary["opportunistic"]:
#             print(f"  - {t}: {s:.3f} shares @ ${p:.2f}")


# ─── 7) SAVE TRADE LOG ──────────────────────────────────────────────────────────
atomic_write_json(trade_log, TRADES_LOG)

# ─── 8) UPDATE PORTFOLIO VALUE & HISTORY ───────────────────────────────────────
# Fetch live price via fast_info for current holdings
total_val = cash + sum(price_cache[t]*s for t,s in holdings.items())

history.append({
    "datetime":    datetime.now().isoformat(),
    "cash":        round(cash, 2),
    "total_value": round(total_val, 2),
    "holdings":    holdings
})

# ─── 9) SAVE UPDATED PORTFOLIO SUMMARY ─────────────────────────────────────────
new_summary = {
    "date":     datetime.now().isoformat(),
    "cash":     round(cash, 2),
    "holdings": holdings,
    "history":  history
}

atomic_write_json(new_summary, PORTFOLIO_FILE)

# ─── 10) PRINT STATUS ───────────────────────────────────────────────────────────
print("\n✅ Trades executed.")
print(f"Cash: ${new_summary['cash']:.2f}")
# print("Holdings:")
# for t, s in holdings.items():
#     print(f" • {t}: {s} shares  (live @ ${get_current_price(t):.2f})")
print(f"Portfolio total value: ${total_val:.2f}")
print(f"History entries: {len(history)}")