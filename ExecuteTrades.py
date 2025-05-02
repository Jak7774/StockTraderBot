# ExecuteTrades.py

import json
import os
from datetime import date, datetime
import yfinance as yf

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

# ─── 2) LOAD OR INIT PORTFOLIO ──────────────────────────────────────────────────
if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE) as f:
        summary = json.load(f)
    cash     = summary.get("cash", INITIAL_CASH)
    holdings = summary.get("holdings", {})
    history  = summary.get("history", [])
else:
    cash     = INITIAL_CASH
    holdings = {}
    history  = []

# ─── 3) LOAD SIGNALS & SCREEN ───────────────────────────────────────────────────
with open(SIGNALS_FILE) as f:
    sigs = json.load(f)
buy_sigs  = sigs.get("buy_signals", {})
sell_sigs = sigs.get("sell_signals", {})

with open(SCREEN_FILE) as f:
    screen = json.load(f)
momentum_map = screen.get("momentum", {})

# ─── 4) LOAD OR INIT TRADE LOG ──────────────────────────────────────────────────
if os.path.exists(TRADES_LOG):
    with open(TRADES_LOG) as f:
        trade_log = json.load(f)
else:
    trade_log = []

# ─── 5) EXECUTE SELLS (WITH DEFERRED IF MOMENTUM POSITIVE) ──────────────────────

# Load existing deferred sells (if any)
if os.path.exists(DEFERRED_SELLS_FILE):
    with open(DEFERRED_SELLS_FILE) as f:
        deferred_sells = json.load(f)
else:
    deferred_sells = {}

for tkr, info in sell_sigs.items():
    momentum = momentum_map.get(tkr, 0)

    if momentum > 0:
        # Defer selling stocks still trending upward
        deferred_sells[tkr] = {
            "latest_price": info["latest_price"],
            "momentum": momentum,
            "date_flagged": str(date.today())
        }
        print(f"⏩ Deferred selling {tkr}: positive momentum ({momentum:.2f})")
        continue

    # Otherwise, sell normally
    if tkr in holdings:
        shares = holdings.pop(tkr)
        price  = info["latest_price"]
        cash  += shares * price
        trade_log.append({
            "ticker": tkr,
            "action": "SELL",
            "date":   str(datetime.date.today()),
            "price":  price,
            "shares": shares
        })
        print(f"Sold {shares} of {tkr} @ ${price:.2f}")

# Save updated deferred sells
with open(DEFERRED_SELLS_FILE, "w") as f:
    json.dump(deferred_sells, f, indent=2)
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
with open(DEFERRED_SELLS_FILE, "w") as f:
    json.dump(cleaned_deferred_sells, f, indent=2)

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
            alloc = w * start_cash
            price = info["latest_price"]

            if ALLOW_FRACTIONAL:
                shares = round(alloc / price, 6)
                if shares < 0.001:
                    summary["skipped"].append((t, alloc, price))
                    continue
                shares = round(shares, 3)
                cost = shares * price
            else:
                shares = int(alloc // price)
                if shares == 0:
                    summary["skipped"].append((t, alloc, price))
                    continue
                cost = shares * price

            if cost > cash:
                summary["skipped"].append((t, alloc, price))
                continue

            cash -= cost
            holdings[t] = round(holdings.get(t, 0) + shares, 3)
            trade_log.append({
                "ticker": t,
                "action": "BUY",
                "date": str(date.today()),
                "price": price,
                "shares": shares
            })
            summary["bought"].append((t, shares, price))

        # Opportunistic buys
        price_map = {}
        for t in holdings.keys() | set(buy_list):
            tk = yf.Ticker(t)
            lp = tk.fast_info.last_price
            if lp and lp > 0:
                price_map[t] = lp

        while True:
            # Recompute total portfolio value before each iteration
            total_val = cash
            prices = {}
            for t, shares in holdings.items():
                lp = price_map.get(t)
                if not lp:
                    lp = yf.Ticker(t).fast_info.last_price or 0
                    price_map[t] = lp
                total_val += shares * lp

            # Filter viable stocks by price and allocation constraint
            viable = {}
            for t, p in price_map.items():
                if p == 0 or cash < (p if not ALLOW_FRACTIONAL else 0.01):
                    continue
                current_shares = holdings.get(t, 0)
                current_val = current_shares * p
                future_val = current_val + (p if not ALLOW_FRACTIONAL else cash)
                future_alloc = future_val / total_val if total_val > 0 else 0
                if future_alloc <= MAX_ALLOC:
                    viable[t] = p

            if not viable:
                break

            # Pick the stock with the best (lowest) price
            pick, price = min(viable.items(), key=lambda kv: kv[1])

            if ALLOW_FRACTIONAL:
                max_invest = min(cash, (MAX_ALLOC * total_val) - holdings.get(pick, 0) * price)
                shares = round(max_invest / price, 6)
                if shares < 0.001:
                    break
                shares = round(shares, 3)
                cost = shares * price
            else:
                if price > cash:
                    break
                shares = 1
                cost = price

            if cost > cash:
                break

            cash -= cost
            holdings[pick] = round(holdings.get(pick, 0) + shares, 3)
            trade_log.append({
                "ticker": pick,
                "action": "BUY",
                "date": str(datetime.date.today()),
                "price": price,
                "shares": shares
            })
            summary["opportunistic"].append((pick, price, shares))


    else:
        summary["no_alloc"] = True
else:
    summary["no_signals"] = True

# ─── PRINT SUMMARY ──────────────────────────────────────────────────────────────
print("\n=== Buy Summary ===")
if summary["no_signals"]:
    print("No positive-momentum buy signals to execute.")
elif summary["no_alloc"]:
    print("⚠️ No tickers met the 1% min allocation threshold.")
else:
    if summary["bought"]:
        print(f"✅ Bought: {len(summary['bought'])} tickers")
        for t, s, p in summary["bought"]:
            print(f"  - {t}: {s} shares @ ${p:.2f}")
    if summary["skipped"]:
        print(f"⚠️ Skipped (alloc < price): {len(summary['skipped'])}")
        for t, alloc, price in summary["skipped"]:
            print(f"  - {t}: alloc ${alloc:.2f} < price ${price:.2f}")
    if summary["opportunistic"]:
        print(f"💡 Opportunistic buys: {len(summary['opportunistic'])}")
        for t, p, s in summary["opportunistic"]:
            print(f"  - {t}: {s:.3f} shares @ ${p:.2f}")


# ─── 7) SAVE TRADE LOG ──────────────────────────────────────────────────────────
with open(TRADES_LOG, "w") as f:
    json.dump(trade_log, f, indent=2)

# ─── 8) UPDATE PORTFOLIO VALUE & HISTORY ───────────────────────────────────────
# Fetch live price via fast_info for current holdings
total_val = cash
for t, shares in holdings.items():
    tk = yf.Ticker(t)
    lp = tk.fast_info.last_price or 0
    total_val += shares * lp

history.append({
    "datetime":    datetime.now().isoformat(),
    "cash":        round(cash, 2),
    "total_value": round(total_val, 2),
    "holdings":    holdings
})

# ─── 9) SAVE UPDATED PORTFOLIO SUMMARY ─────────────────────────────────────────
new_summary = {
    "date":     str(date.today()),
    "cash":     round(cash, 2),
    "holdings": holdings,
    "history":  history
}
with open(PORTFOLIO_FILE, "w") as f:
    json.dump(new_summary, f, indent=2)

# ─── 10) PRINT STATUS ───────────────────────────────────────────────────────────
print("\n✅ Trades executed.")
print(f"Cash: ${new_summary['cash']:.2f}")
print("Holdings:")
for t, s in holdings.items():
    print(f" • {t}: {s} shares  (live @ ${yf.Ticker(t).fast_info.last_price:.2f})")
print(f"Portfolio total value: ${total_val:.2f}")
print(f"History entries: {len(history)}")