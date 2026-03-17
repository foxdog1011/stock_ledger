"""Domain layer.

Pure business logic with no HTTP or framework dependencies.
Modules here accept ``StockLedger`` as a parameter and return
plain Python dicts / dataclasses – no FastAPI, no Pydantic responses.

Sub-packages
------------
portfolio/
    P&L computation (WAC), lot-level analysis (FIFO/LIFO/WAC),
    and position detail with cost-impact breakdown.
"""
