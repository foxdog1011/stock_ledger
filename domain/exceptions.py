"""Unified domain exception hierarchy for Stock Ledger.

All domain-specific errors inherit from DomainError so that
API-layer exception handlers can catch them with a single base class
while still dispatching on concrete subtypes for appropriate HTTP status codes.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base for all domain errors."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class EntityNotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, identifier: str) -> None:
        super().__init__(
            f"{entity} '{identifier}' not found",
            "NOT_FOUND",
        )


class PriceFetchError(DomainError):
    """Raised when a price provider fails to return data."""

    def __init__(self, symbol: str, provider: str, reason: str = "") -> None:
        super().__init__(
            f"Failed to fetch price for {symbol} from {provider}: {reason}",
            "PRICE_FETCH_ERROR",
        )


class InsufficientPositionError(DomainError):
    """Raised when a sell exceeds the available position."""

    def __init__(self, symbol: str, requested: int, available: int) -> None:
        super().__init__(
            f"Insufficient position for {symbol}: requested {requested}, available {available}",
            "INSUFFICIENT_POSITION",
        )


class ValidationError(DomainError):
    """Raised for invalid business-rule inputs."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "VALIDATION_ERROR")


class ExternalServiceError(DomainError):
    """Raised when an external API or service call fails."""

    def __init__(self, service: str, reason: str = "") -> None:
        super().__init__(
            f"External service error ({service}): {reason}",
            "EXTERNAL_SERVICE_ERROR",
        )


class RateLimitError(DomainError):
    """Raised when an external service rate-limits us."""

    def __init__(self, service: str) -> None:
        super().__init__(
            f"Rate limited by {service}",
            "RATE_LIMITED",
        )


class DatabaseError(DomainError):
    """Raised on unexpected database failures."""

    def __init__(self, operation: str, reason: str = "") -> None:
        super().__init__(
            f"Database error during {operation}: {reason}",
            "DATABASE_ERROR",
        )
