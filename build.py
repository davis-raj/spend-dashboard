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
expenses['Spend'] = expenses['Amount'].abs()
income = df[df['Amount'] > 0].copy()

# Separate true income from internal transfers
TRANSFER_CATEGORIES = ['Transfer', 'Credit Card Payment', 'Balance Adjustments']
# 'Transfer From Checking' is paycheck/salary — treat as income
is_transfer = (income['Category'].isin(TRANSFER_CATEGORIES)) & (income['Merchant'] != 'Transfer From Checking')
true_income = income[~is_transfer].copy()
transfers_in = income[is_transfer].copy()

data = {}

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

# Transactions
txns = expenses[['Date','Merchant','Category','Account','Spend','Month']].copy()
txns['Date'] = txns['Date'].dt.strftime('%Y-%m-%d')
data['transactions'] = txns.to_dict('records')
for t in data['transactions']:
    t['Spend'] = round(t['Spend'], 2)

os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
with open(OUT_FILE, 'w') as f:
    json.dump(data, f)

print(f"Built {OUT_FILE}: {len(data['transactions'])} transactions, {len(all_months)} months")
