"""
Dashboard configuration — single source of truth for all business rules.

Edit this file to:
- Add/remove tracked accounts
- Change year filters
- Fix Monarch miscategorizations
- Update income source detection rules
- Add internal transfer patterns
"""

# =============================================================================
# ACCOUNT & YEAR FILTERS
# =============================================================================
INCLUDE_ACCOUNTS = ['Apple Card', 'CASHBACK DEBIT (...3359)']
INCLUDE_YEARS = [2025, 2026]

# =============================================================================
# CATEGORY OVERRIDES (fix Monarch miscategorizations)
# =============================================================================
# {merchant: corrected_category} — applied when Monarch assigns the wrong category
MORTGAGE_MERCHANTS = {
    'ServiceMac', 'Flagstar Bank', 'Mr. Cooper', 'Rocket Mortgage',
    'Mortgage Company Mtge Pay', 'Upper Palmetto',
}
# These merchants get force-recategorized from "Loan Repayment" -> "Mortgage"
CATEGORY_OVERRIDES = [
    {"merchants": MORTGAGE_MERCHANTS, "from_category": "Loan Repayment", "to_category": "Mortgage"},
]

# =============================================================================
# INTERNAL TRANSFER DETECTION
# =============================================================================
# Transactions matching these rules are excluded from spending (they're just
# money moving between accounts, not real expenses).

# Categories that are always transfers
TRANSFER_CATEGORIES = {'Balance Adjustments'}

# Credit card payments that are internal (the card itself is tracked)
INTERNAL_CC_PAYMENT_KEYWORDS = {'apple'}  # Apple Card payment from debit = internal

# Transfer merchant/statement patterns to exclude
TRANSFER_MERCHANT_NAMES = {'Discover'}
TRANSFER_STATEMENT_KEYWORDS = {'SAVINGS', 'APPLE CASH SENT', 'APPLE CASH SE'}

# =============================================================================
# INCOME SOURCE LABELING
# =============================================================================
# Rules to identify income sources from statement text and merchants.
# Evaluated in order; first match wins.
INCOME_RULES = [
    # Paycheck detection by account number in statement
    {"statement_contains": ["6079", "4287"], "label": "Davis Paycheck"},
    {"statement_contains": ["2481", "2649"], "label": "Esther Paycheck"},
    # Merchant-based detection
    {"merchant_contains": "Bank of America", "label": "Esther Paycheck"},
    {"merchant_exact": "Transfer From Checking", "label": "Paycheck (Other)"},
    {"merchant_contains": "Real Property", "label": "Rental Income"},
]

# Categories that signal transfers, not income (positive amounts in these = internal)
INCOME_TRANSFER_CATEGORIES = {'Transfer', 'Credit Card Payment', 'Balance Adjustments'}

# =============================================================================
# AGGREGATION SETTINGS
# =============================================================================
TOP_CATEGORIES = 15
TOP_MERCHANTS = 12
