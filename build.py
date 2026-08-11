#!/usr/bin/env python3
"""
Build the spend dashboard data.json from transactions CSV.

Thin orchestrator — all logic lives in pipeline/ modules.
All business rules live in config.py.

Usage:
    python build.py              # Build docs/data.json from latest CSV
    python build.py --check      # Validate without overwriting
"""
import json
import os
import sys

from pipeline.loader import find_latest_csv, load_transactions, deduplicate
from pipeline.transforms import (
    filter_accounts_and_years,
    apply_category_overrides,
    split_expenses_and_income,
    label_income_sources,
    apply_refunds,
)
from pipeline.aggregations import (
    monthly_summary,
    category_totals,
    category_by_month,
    income_by_category,
    income_by_month,
    transaction_list,
    income_transaction_list,
)

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_FILE = os.path.join(BASE_DIR, "docs", "data.json")


def build() -> dict:
    """Run the full pipeline and return the dashboard data dict."""
    # 1. Load
    csv_path = find_latest_csv(DATA_DIR)
    print(f"Loading: {os.path.basename(csv_path)}")
    df = load_transactions(csv_path)
    df = deduplicate(df)
    print(f"  {len(df)} rows after dedup")

    # 2. Filter & transform
    df = filter_accounts_and_years(df)
    df = apply_category_overrides(df)

    # 3. Split expenses / income
    expenses, income = split_expenses_and_income(df)

    # 4. Label income and apply refunds
    expense_categories = set(df[df['Amount'] < 0]['Category'].dropna().astype(str))
    income = label_income_sources(income, expense_categories)
    expenses, true_income, transfers_in = apply_refunds(expenses, income)

    # 5. Aggregate
    monthly = monthly_summary(expenses, true_income, transfers_in)
    all_months = [m['month'] for m in monthly]

    categories = category_totals(expenses)
    cat_by_month = category_by_month(expenses, categories, all_months)

    inc_categories = income_by_category(true_income)
    inc_by_month = income_by_month(true_income, inc_categories, all_months)

    transactions = transaction_list(expenses)
    inc_transactions = income_transaction_list(true_income)

    # 6. Assemble output
    data = {
        'monthly': monthly,
        'categories': categories,
        'catByMonth': cat_by_month,
        'incomeCategories': inc_categories,
        'incByMonth': inc_by_month,
        'transactions': transactions,
        'incomeTransactions': inc_transactions,
    }

    print(f"Built: {len(transactions)} transactions, {len(all_months)} months, "
          f"{len(categories)} categories, {len(inc_categories)} income sources")
    return data


def main():
    data = build()

    if "--check" in sys.argv:
        print("✓ Build check passed (no output written)")
        return

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w') as f:
        json.dump(data, f)
    print(f"→ {OUT_FILE}")


if __name__ == "__main__":
    main()
