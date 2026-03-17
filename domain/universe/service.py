"""Universe service layer: operations that combine multiple repository calls."""
from __future__ import annotations

from pathlib import Path

from .repository import get_company, list_relationships, list_thesis


def get_company_detail(db_path: Path, symbol: str) -> dict | None:
    """
    Return full company detail: master fields + relationships + active thesis.

    segments is an empty list in the first version (table exists, CRUD deferred).
    Returns None if the symbol is not found in company_master.
    """
    sym = symbol.strip().upper()
    company = get_company(db_path, sym)
    if company is None:
        return None
    return {
        **company,
        "segments":      [],                                        # deferred
        "relationships": list_relationships(db_path, sym),
        "thesis":        list_thesis(db_path, sym, active_only=True),
    }
