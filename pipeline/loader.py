"""Load and deduplicate transaction CSV data."""
import os
import glob
import pandas as pd


def find_latest_csv(data_dir: str) -> str:
    """Find the freshest transactions CSV in data_dir (by mtime).

    Matches both 'transactions.csv' (auto-download) and 'Transactions_*.csv' (manual export).
    """
    candidates = [
        f for f in glob.glob(os.path.join(data_dir, "*.csv"))
        if "transaction" in os.path.basename(f).lower()
    ]
    if not candidates:
        raise FileNotFoundError(f"No transactions CSV found in {data_dir}")
    return sorted(candidates, key=os.path.getmtime)[-1]


def load_transactions(csv_path: str) -> pd.DataFrame:
    """Load transactions CSV and parse dates/amounts.

    Returns DataFrame with columns: Date, Merchant, Category, Account, Amount,
    Original Statement, Month, plus any other columns in the CSV.
    """
    df = pd.read_csv(csv_path)
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=False)
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    df['Month'] = df['Date'].dt.strftime('%Y-%m')
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove true re-imports (all fields identical) without collapsing
    genuinely distinct same-day/same-merchant/same-amount purchases.

    Uses Date + Merchant + Amount + Account (+ Original Statement if available)
    as the dedup key.
    """
    dedup_keys = ['Date', 'Merchant', 'Amount', 'Account']
    if 'Original Statement' in df.columns:
        dedup_keys.append('Original Statement')
    return df.drop_duplicates(subset=dedup_keys, keep='first')
