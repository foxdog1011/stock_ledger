"""Financial statements domain constants."""

STATEMENT_TYPES = frozenset({"income", "balance", "cashflow"})

# Key fields we extract from FinMind datasets
INCOME_FIELDS = frozenset({
    "revenue", "operating_expense", "operating_income",
    "net_income", "eps", "gross_profit",
})

BALANCE_FIELDS = frozenset({
    "total_assets", "total_liabilities", "equity",
    "current_assets", "current_liabilities",
    "cash_and_equivalents", "total_debt",
})

CASHFLOW_FIELDS = frozenset({
    "operating_cashflow", "investing_cashflow",
    "financing_cashflow", "free_cashflow", "capex",
})
