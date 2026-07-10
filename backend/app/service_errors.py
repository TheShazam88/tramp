from __future__ import annotations


class ConflictError(Exception):
    """Raised when an operation conflicts with existing state."""


class AuthenticationError(Exception):
    """Raised when step-up verification fails."""
