import json
from collections import defaultdict
import matplotlib.pyplot as plt
from datetime import datetime, date

# ── Load portfolio summary ──────────────────────────────────────────
with open('portfolio_summary.json') as f:
    portfolio_data = json.load(f)

# ── Derive initial state from the first history entry ──────────────
cash = 10000
holdings = defaultdict(float)

violations = []
cash_history = []
date_history = []
violation_counts = defaultdict(int)

# ── Load trades and sort ────────────────────────────────────────────
with open('trades_log.json') as f:
    trades = json.load(f)
trades.sort(key=lambda x: datetime.fromisoformat(x['date']))

# ── Process trades (with rounding) ─────────────────────────────────
for trade in trades:
    trade_date = trade['date']
    # Date is mix of date and datetime
    dt = datetime.fromisoformat(trade_date)
    action = trade['action']
    ticker = trade['ticker']
    quantity = trade['shares']
    price = trade['price']
    total_cost = quantity * price

    if action == 'BUY':
        if cash >= total_cost:
            holdings[ticker] += quantity
            cash -= total_cost
            cash = round(cash, 2)
        else:
            violations.append({
                'type': 'BUY WITHOUT SUFFICIENT CASH',
                'date': trade_date,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'cash_available': cash
            })
            violation_counts['BUY WITHOUT SUFFICIENT CASH'] += 1
    elif action == 'SELL':
        if holdings[ticker] >= quantity:
            holdings[ticker] -= quantity
            cash += total_cost
            cash = round(cash, 2)
        else:
            violations.append({
                'type': 'SELL WITHOUT HOLDING',
                'date': trade_date,
                'ticker': ticker,
                'quantity': quantity,
                'held': holdings[ticker]
            })
            violation_counts['SELL WITHOUT HOLDING'] += 1

    date_history.append(dt)
    cash_history.append(cash)

# ── Additional QC Checks ────────────────────────────────────────────

# Field presence & type
required_keys = {"date": str, "ticker": str, "action": str, "shares": (int, float), "price": (int, float)}
for i, trade in enumerate(trades):
    for key, typ in required_keys.items():
        if key not in trade or not isinstance(trade[key], typ):
            violations.append({
                'type': 'BAD RECORD',
                'date': trade.get('date', 'unknown'),
                'detail': f"Record #{i} missing/invalid {key} → {trade}"
            })
            violation_counts['BAD RECORD'] += 1

# Future trades
today_dt = datetime.today()
for trade in trades:
    dt = datetime.fromisoformat(trade_date)
    if dt > today_dt:
        violations.append({
            'type': 'FUTURE TRADE',
            'date': trade['date'],
            'detail': f"{trade}"
        })
        violation_counts['FUTURE TRADE'] += 1

# Portfolio reconciliation
if round(cash, 5) != round(portfolio_data['cash'], 5):
    violations.append({
        'type': 'CASH MISMATCH',
        'date': portfolio_data['date'],
        'detail': f"simulated={cash}, summary={portfolio_data['cash']}"
    })
    violation_counts['CASH MISMATCH'] += 1

for ticker, qty in portfolio_data['holdings'].items():
    simulated_qty = holdings.get(ticker, 0)
    if abs(simulated_qty - qty) > 1e-6:
        violations.append({
            'type': 'HOLDING MISMATCH',
            'date': portfolio_data['date'],
            'ticker': ticker,
            'detail': f"simulated={simulated_qty}, summary={qty}"
        })
        violation_counts['HOLDING MISMATCH'] += 1

# Extra holdings not in summary
for ticker in holdings:
    if ticker not in portfolio_data['holdings'] and abs(holdings[ticker]) > 1e-6:
        violations.append({
            'type': 'EXTRA HOLDING',
            'date': portfolio_data['date'],
            'ticker': ticker,
            'detail': f"{holdings[ticker]} shares not in summary"
        })
        violation_counts['EXTRA HOLDING'] += 1

# ── Write violations to JSON ─────────────────────────────────────────
with open('violations_log.json', 'w') as vf:
    json.dump(violations, vf, indent=2)
print(f"🔍 Logged {len(violations)} violations to violations_log.json")

# ── Summary print ─────────────────────────────────────────────────────
print(f"\n✅ Total Violations: {len(violations)}")
for v in violations[:10]:
    line = f"{v['type']} on {v.get('date', 'unknown')}"
    if 'ticker' in v:
        line += f" for {v['ticker']}"
    print(f"{line}: {v.get('detail', '')}")

# ── Violation breakdown by type and date range ────────────────────────
type_dates = defaultdict(list)
for v in violations:
    t = v['type']
    d = v.get('date')
    if d:
        type_dates[t].append(d)

print("\n📋 Violation Summary by Type and Date Range:")
for t, count in violation_counts.items():
    dates = sorted(type_dates.get(t, []))
    if dates:
        print(f"- {t}: {count} violations from {dates[0]} to {dates[-1]}")
    else:
        print(f"- {t}: {count} violations")

# ── Plot cash over time ────────────────────────────────────────────────
plt.figure(figsize=(12, 6))
plt.plot(date_history, cash_history, label='Cash Over Time')
plt.xlabel('Date')
plt.ylabel('Cash (£)')
plt.title('Cash Balance Over Time')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

# ── Plot violation counts ─────────────────────────────────────────────
if violation_counts == 0:
    print("🎉 No violations detected.")