"""Universe domain — schema constants.

No dataclasses or Pydantic models; all repository functions return plain dicts.
These constants are the single source of truth for allowed values and
updatable fields.
"""

RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "competitor",
    "supplier",
    "customer",
    "partner",
})

THESIS_TYPES: frozenset[str] = frozenset({
    "bull",
    "bear",
    "operation_focus",
    "risk_factor",
})

# Fields allowed in update_company(); symbol / created_at / updated_at are excluded.
UPDATABLE_COMPANY_FIELDS: frozenset[str] = frozenset({
    "name",
    "exchange",
    "sector",
    "industry",
    "business_model",
    "country",
    "currency",
    "note",
})
