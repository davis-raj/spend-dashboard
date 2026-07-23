#!/usr/bin/env python3
"""Reads the single YTD transactions CSV in data/ and builds docs/data.json."""
import pandas as pd
import glob
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(os.path.dirname(__file__), "docs", "data.json")

# Find the freshest transactions CSV (case-insensitive match, newest by mtime).
# The auto-downloader saves 'transactions.csv'; manual exports may be 'Transactions_*.csv'.
candidates = [f for f in glob.glob(os.path.join(DATA_DIR, "*.csv"))
              if "transaction" in os.path.basename(f).lower()]
if not candidates:
    print("No transactions CSV found in data/")
    exit(1)
files = sorted(candidates, key=os.path.getmtime)

df = pd.read_csv(files[-1])
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=False)
df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
# Dedup true re-imports (all fields identical) without collapsing genuinely
# distinct same-day/same-merchant/same-amount purchases (different statements).
_dedup_keys = ['Date', 'Merchant', 'Amount', 'Account']
if 'Original Statement' in df.columns:
    _dedup_keys.append('Original Statement')
df = df.drop_duplicates(subset=_dedup_keys, keep='first')
df['Month'] = df['Date'].dt.strftime('%Y-%m')

# --- Filters: current year + only the two accounts we actively track ---
INCLUDE_ACCOUNTS = ['Apple Card', 'CASHBACK DEBIT (...3359)']
CURRENT_YEAR = pd.Timestamp.now().year
# Guard: warn loudly if a tracked account matched nothing (likely renamed in Monarch)
_available = set(df['Account'].dropna().astype(str))
for _acct in INCLUDE_ACCOUNTS:
    if _acct not in _available:
        print(f"WARNING: tracked account '{_acct}' not found in data — "
              f"was it renamed in Monarch? Available: {sorted(_available)}")
df = df[df['Date'].dt.year == CURRENT_YEAR]
df = df[df['Account'].isin(INCLUDE_ACCOUNTS)]
if df.empty:
    print(f"WARNING: no rows after filtering to {CURRENT_YEAR} + {INCLUDE_ACCOUNTS}. "
          "Dashboard will be empty — check account names / year.")
print(f"Filtered to {CURRENT_YEAR} + {INCLUDE_ACCOUNTS}: {len(df)} rows")

# Apple Card purchases are itemized (that account is included), so the "Apple"
# Credit Card Payment from the debit account is just the payoff — dropping it
# avoids double-counting. Payments to OTHER cards (Chase, Citi, Best Buy, etc.)
# are kept, since those cards are NOT included and the payment is the only record.
def is_internal_transfer(row):
    cat = str(row['Category'])
    if cat == 'Balance Adjustments':
        return True
    if cat == 'Credit Card Payment' and 'apple' in str(row['Merchant']).lower():
        return True
    if cat == 'Transfer':
        merch = str(row['Merchant'])
        stmt = str(row.get('Original Statement', '')).upper()
        # Moves between the family's own accounts (savings / Apple Cash)
        if merch == 'Discover' or 'SAVINGS' in stmt or 'APPLE CASH SENT' in stmt or 'APPLE CASH SE' in stmt:
            return True
    return False

expenses = df[df['Amount'] < 0].copy()
expenses = expenses[~expenses.apply(is_internal_transfer, axis=1)]
expenses['Spend'] = expenses['Amount'].abs()
income = df[df['Amount'] > 0].copy()

# A positive amount is a REFUND only if its category is ALSO used for spending
# (e.g. a Shopping return). Categories that only ever appear as income (Paychecks,
# Other Income, Check Deposit, Interest, ...) are genuine income. Self-maintaining:
# new income categories in Monarch just work, no code change needed.
expense_categories = set(df[df['Amount'] < 0]['Category'].dropna().astype(str))

# Label income sources
def label_income(row):
    stmt = str(row.get('Original Statement', ''))
    if '6079' in stmt or '4287' in stmt: return 'Davis Paycheck'
    if '2481' in stmt: return 'Esther Paycheck'
    if row['Merchant'] == 'Transfer From Checking': return 'Paycheck (Other)'
    if 'Real Property' in str(row['Merchant']): return 'Rental Income'
    if row['Category'] in ['Transfer', 'Credit Card Payment', 'Balance Adjustments']:
        return '_transfer'
    # Positive amount in a spending category = refund/return, not income
    if str(row['Category']) in expense_categories:
        return '_refund'
    # Genuine income — label by its category name (e.g. Check Deposit, Interest)
    return str(row['Category'])

income['IncomeSource'] = income.apply(label_income, axis=1)

# Separate true income from internal transfers and refunds
true_income = income[~income['IncomeSource'].isin(['_transfer', '_refund'])].copy()
transfers_in = income[income['IncomeSource'] == '_transfer'].copy()

# Refunds/returns: net against spending in their original category (negative spend)
refunds = income[income['IncomeSource'] == '_refund'].copy()
if not refunds.empty:
    refunds['Spend'] = -refunds['Amount']  # positive refund -> negative spend
    expenses = pd.concat([expenses, refunds[expenses.columns]], ignore_index=True)

data = {}

# Income by category
inc_by_source = true_income.groupby('IncomeSource')['Amount'].agg(['sum','count']).sort_values('sum', ascending=False)
data['incomeCategories'] = [{'name': c, 'total': round(r['sum'], 2), 'count': int(r['count'])} for c, r in inc_by_source.iterrows()]

# Monthly
monthly_exp = expenses.groupby('Month')['Spend'].sum().to_dict()
monthly_inc = true_income.groupby('Month')['Amount'].sum().to_dict()
monthly_xfer = transfers_in.groupby('Month')['Amount'].sum().to_dict()
all_months = sorted(set(list(monthly_exp.keys()) + list(monthly_inc.keys()) + list(monthly_xfer.keys())))
data['monthly'] = [{'month': m, 'expenses': round(monthly_exp.get(m, 0), 2),
                    'income': round(monthly_inc.get(m, 0), 2),
                    'transfers': round(monthly_xfer.get(m, 0), 2)} for m in all_months]

# Categories
cat = expenses.groupby('Category')['Spend'].agg(['sum','count']).sort_values('sum', ascending=False).head(15)
data['categories'] = [{'name': c, 'total': round(r['sum'], 2), 'count': int(r['count'])} for c, r in cat.iterrows()]

# Category x Month
pivot = expenses.pivot_table(index='Category', columns='Month', values='Spend', aggfunc='sum', fill_value=0)
data['catByMonth'] = {}
for c in cat.index:
    if c in pivot.index:
        data['catByMonth'][c] = {m: round(pivot.loc[c, m], 2) for m in all_months if m in pivot.columns}

# Income by source x Month
inc_pivot = true_income.pivot_table(index='IncomeSource', columns='Month', values='Amount', aggfunc='sum', fill_value=0)
data['incByMonth'] = {}
for src in inc_by_source.index:
    if src in inc_pivot.index:
        data['incByMonth'][src] = {m: round(inc_pivot.loc[src, m], 2) for m in all_months if m in inc_pivot.columns}

# Transactions
txns = expenses[['Date','Merchant','Category','Account','Spend','Month']].copy()
txns['Date'] = txns['Date'].dt.strftime('%Y-%m-%d')
data['transactions'] = txns.to_dict('records')
for t in data['transactions']:
    t['Spend'] = round(t['Spend'], 2)

# Income transactions (for month filtering)
inc_txns = true_income[['Date','IncomeSource','Amount','Month']].copy()
inc_txns['Date'] = inc_txns['Date'].dt.strftime('%Y-%m-%d')
data['incomeTransactions'] = inc_txns.to_dict('records')
for t in data['incomeTransactions']:
    t['Amount'] = round(t['Amount'], 2)

os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
with open(OUT_FILE, 'w') as f:
    json.dump(data, f)

print(f"Built {OUT_FILE}: {len(data['transactions'])} transactions, {len(all_months)} months")
