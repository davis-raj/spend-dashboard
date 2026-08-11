"""Data transformations — filtering, transfer detection, refund handling, categorization."""
import pandas as pd

from config import (
    INCLUDE_ACCOUNTS, INCLUDE_YEARS,
    CATEGORY_OVERRIDES, TRANSFER_CATEGORIES,
    INTERNAL_CC_PAYMENT_KEYWORDS, TRANSFER_MERCHANT_NAMES,
    TRANSFER_STATEMENT_KEYWORDS, INCOME_RULES,
    INCOME_TRANSFER_CATEGORIES,
)


def filter_accounts_and_years(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to tracked accounts and included years."""
    # Warn if a tracked account isn't in the data
    available = set(df['Account'].dropna().astype(str))
    for acct in INCLUDE_ACCOUNTS:
        if acct not in available:
            print(f"WARNING: tracked account '{acct}' not found in data — "
                  f"was it renamed? Available: {sorted(available)}")

    mask = df['Date'].dt.year.isin(INCLUDE_YEARS) & df['Account'].isin(INCLUDE_ACCOUNTS)
    filtered = df[mask].copy()

    if filtered.empty:
        print(f"WARNING: no rows after filtering to {INCLUDE_YEARS} + {INCLUDE_ACCOUNTS}. "
              "Dashboard will be empty.")
    else:
        print(f"Filtered to {INCLUDE_YEARS} + {INCLUDE_ACCOUNTS}: {len(filtered)} rows")

    return filtered


def apply_category_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Fix Monarch miscategorizations using rules from config."""
    for rule in CATEGORY_OVERRIDES:
        mask = (
            df['Merchant'].isin(rule['merchants']) &
            (df['Category'] == rule['from_category'])
        )
        count = mask.sum()
        if count > 0:
            df.loc[mask, 'Category'] = rule['to_category']
            print(f"  Recategorized {count} '{rule['from_category']}' -> '{rule['to_category']}'")
    return df


def is_internal_transfer(row) -> bool:
    """Determine if a transaction is an internal transfer (not real spending)."""
    cat = str(row.get('Category', ''))
    merchant = str(row.get('Merchant', ''))
    stmt = str(row.get('Original Statement', '')).upper()

    # Category-based
    if cat in TRANSFER_CATEGORIES:
        return True

    # Apple Card payment from debit (card is already tracked)
    if cat == 'Credit Card Payment':
        if any(kw in merchant.lower() for kw in INTERNAL_CC_PAYMENT_KEYWORDS):
            return True

    # Transfer category with known internal patterns
    if cat == 'Transfer':
        if merchant in TRANSFER_MERCHANT_NAMES:
            return True
        if any(kw in stmt for kw in TRANSFER_STATEMENT_KEYWORDS):
            return True

    return False


def split_expenses_and_income(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into expenses (Amount < 0) and income (Amount > 0).

    Expenses have internal transfers removed and a 'Spend' column (absolute value).
    """
    expenses = df[df['Amount'] < 0].copy()
    expenses = expenses[~expenses.apply(is_internal_transfer, axis=1)]
    expenses['Spend'] = expenses['Amount'].abs()

    income = df[df['Amount'] > 0].copy()
    return expenses, income


def label_income_sources(income: pd.DataFrame, expense_categories: set) -> pd.DataFrame:
    """Label each income row with its source (paycheck, rental, refund, transfer).

    Returns income DataFrame with 'IncomeSource' column.
    """
    def _label(row):
        stmt = str(row.get('Original Statement', ''))
        merchant = str(row.get('Merchant', ''))
        category = str(row.get('Category', ''))

        # Rule-based matching (from config)
        for rule in INCOME_RULES:
            if 'statement_contains' in rule:
                if any(kw in stmt for kw in rule['statement_contains']):
                    return rule['label']
            if 'merchant_contains' in rule:
                if rule['merchant_contains'] in merchant:
                    return rule['label']
            if 'merchant_exact' in rule:
                if merchant == rule['merchant_exact']:
                    return rule['label']

        # Internal transfers
        if category in INCOME_TRANSFER_CATEGORIES:
            return '_transfer'

        # Refund detection: positive amount in a spending category
        if category in expense_categories:
            return '_refund'

        # Genuine income — label by category name
        return category

    income = income.copy()
    income['IncomeSource'] = income.apply(_label, axis=1)
    return income


def apply_refunds(expenses: pd.DataFrame, income: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separate income into true income, transfers, and refunds.

    Refunds are netted against spending (negative Spend entries).
    Returns (expenses_with_refunds, true_income, transfers_in).
    """
    true_income = income[~income['IncomeSource'].isin(['_transfer', '_refund'])].copy()
    transfers_in = income[income['IncomeSource'] == '_transfer'].copy()
    refunds = income[income['IncomeSource'] == '_refund'].copy()

    if not refunds.empty:
        refunds = refunds.copy()
        refunds['Spend'] = -refunds['Amount']  # positive refund -> negative spend
        # Only keep columns that exist in expenses
        common_cols = [c for c in expenses.columns if c in refunds.columns]
        expenses = pd.concat([expenses, refunds[common_cols]], ignore_index=True)

    return expenses, true_income, transfers_in
