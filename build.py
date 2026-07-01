#!/usr/bin/env python3
"""Reads the single YTD transactions CSV in data/ and builds docs/data.json."""
import pandas as pd
import glob
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(os.path.dirname(__file__), "docs", "data.json")

# Find the latest Transactions CSV (just pick the newest one if multiple exist)
files = sorted(glob.glob(os.path.join(DATA_DIR, "Transactions*.csv")))
if not files:
    print("No CSV file found in data/")
    exit(1)

df = pd.read_csv(files[-1])
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=False)
df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
df = df.drop_duplicates(subset=['Date','Merchant','Amount','Account'], keep='first')
df['Month'] = df['Date'].dt.strftime('%Y-%m')

expenses = df[df['Amount'] < 0].copy()
# Exclude internal transfers between Discover accounts (e.g., checking → savings)
expenses = expenses[~((expenses['Merchant'] == 'Discover') & (expenses['Category'] == 'Transfer'))]
expenses['Spend'] = expenses['Amount'].abs()
income = df[df['Amount'] > 0].copy()

# Label income sources
def label_income(row):
    stmt = str(row.get('Original Statement', ''))
    if '6079' in stmt or '4287' in stmt: return 'Davis Paycheck'
    if '2481' in stmt: return 'Esther Paycheck'
    if row['Merchant'] == 'Transfer From Checking': return 'Paycheck (Other)'
    if 'Real Property' in str(row['Merchant']): return 'Rental Income'
    if 'Internal Revenue' in str(row['Merchant']): return 'Tax Refund'
    if row['Category'] in ['Transfer', 'Credit Card Payment', 'Balance Adjustments']:
        return '_transfer'
    return 'Other Income'

income['IncomeSource'] = income.apply(label_income, axis=1)

# Separate true income from internal transfers
true_income = income[income['IncomeSource'] != '_transfer'].copy()
transfers_in = income[income['IncomeSource'] == '_transfer'].copy()

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

# Merchants
merch = expenses.groupby('Merchant')['Spend'].agg(['sum','count']).sort_values('sum', ascending=False).head(15)
data['merchants'] = [{'name': m, 'total': round(r['sum'], 2), 'count': int(r['count'])} for m, r in merch.iterrows()]

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
