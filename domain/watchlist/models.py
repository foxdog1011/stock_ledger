"""Watchlist domain — schema constants."""

STATUS_VALUES: frozenset[str] = frozenset({
    "watching",
    "monitoring",
    "archived",
})

# Fields allowed in update_watchlist_item(); id / watchlist_id / symbol /
# added_at / updated_at are excluded.
UPDATABLE_ITEM_FIELDS: frozenset[str] = frozenset({
    "industry_position",
    "operation_focus",
    "thesis_summary",
    "primary_catalyst",
    "status",
})
