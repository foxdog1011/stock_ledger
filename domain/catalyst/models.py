"""Catalyst domain constants."""
from __future__ import annotations

EVENT_TYPES = frozenset({"company", "macro", "sector"})
STATUS_VALUES = frozenset({"pending", "passed", "cancelled"})
UPDATABLE_CATALYST_FIELDS = frozenset({"title", "event_date", "status", "notes"})
