"""Aggregations — monthly totals, category breakdowns, merchant rankings."""
import pandas as pd

from config import TOP_CATEGORIES


def monthly_summary(
    expenses: pd.DataFrame,
    true_income: pd.DataFrame,
    transfers_in: pd.DataFrame,
) -> list[dict]:
    """Monthly expenses, income, and transfers."""
    monthly_exp = expenses.groupby('Month')['Spend'].sum().to_dict()
    monthly_inc = true_income.groupby('Month')['Amount'].sum().to_dict()
    monthly_xfer = transfers_in.groupby('Month')['Amount'].sum().to_dict()

    all_months = sorted(set(
        list(monthly_exp.keys()) + list(monthly_inc.keys()) + list(monthly_xfer.keys())
    ))

    return [
        {
            'month': m,
            'expenses': round(monthly_exp.get(m, 0), 2),
            'income': round(monthly_inc.get(m, 0), 2),
            'transfers': round(monthly_xfer.get(m, 0), 2),
        }
        for m in all_months
    ]


def category_totals(expenses: pd.DataFrame) -> list[dict]:
    """Top N categories by total spend."""
    cat = (expenses.groupby('Category')['Spend']
           .agg(['sum', 'count'])
           .sort_values('sum', ascending=False)
           .head(TOP_CATEGORIES))
    return [
        {'name': c, 'total': round(r['sum'], 2), 'count': int(r['count'])}
        for c, r in cat.iterrows()
    ]


def category_by_month(expenses: pd.DataFrame, top_categories: list[dict], all_months: list[str]) -> dict:
    """Category × Month pivot for trend charts."""
    pivot = expenses.pivot_table(
        index='Category', columns='Month', values='Spend', aggfunc='sum', fill_value=0
    )
    result = {}
    for cat_info in top_categories:
        c = cat_info['name']
        if c in pivot.index:
            result[c] = {
                m: round(pivot.loc[c, m], 2)
                for m in all_months if m in pivot.columns
            }
    return result


def income_by_category(true_income: pd.DataFrame) -> list[dict]:
    """Income grouped by source."""
    inc = (true_income.groupby('IncomeSource')['Amount']
           .agg(['sum', 'count'])
           .sort_values('sum', ascending=False))
    return [
        {'name': c, 'total': round(r['sum'], 2), 'count': int(r['count'])}
        for c, r in inc.iterrows()
    ]


def income_by_month(true_income: pd.DataFrame, income_categories: list[dict], all_months: list[str]) -> dict:
    """Income source × Month pivot for trend charts."""
    pivot = true_income.pivot_table(
        index='IncomeSource', columns='Month', values='Amount', aggfunc='sum', fill_value=0
    )
    result = {}
    for inc_info in income_categories:
        src = inc_info['name']
        if src in pivot.index:
            result[src] = {
                m: round(pivot.loc[src, m], 2)
                for m in all_months if m in pivot.columns
            }
    return result


def transaction_list(expenses: pd.DataFrame) -> list[dict]:
    """Expense transactions formatted for the frontend."""
    txns = expenses[['Date', 'Merchant', 'Category', 'Account', 'Spend', 'Month']].copy()
    txns['Date'] = txns['Date'].dt.strftime('%Y-%m-%d')
    records = txns.to_dict('records')
    for t in records:
        t['Spend'] = round(t['Spend'], 2)
    return records


def income_transaction_list(true_income: pd.DataFrame) -> list[dict]:
    """Income transactions formatted for the frontend."""
    txns = true_income[['Date', 'IncomeSource', 'Amount', 'Account', 'Month']].copy()
    txns['Date'] = txns['Date'].dt.strftime('%Y-%m-%d')
    records = txns.to_dict('records')
    for t in records:
        t['Amount'] = round(t['Amount'], 2)
    return records
