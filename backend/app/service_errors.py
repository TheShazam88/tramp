from __future__ import annotations


class ConflictError(Exception):
    """Raised when an operation conflicts with existing state."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "conflict",
        safe_to_retry: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_to_retry = safe_to_retry


class AuthenticationError(Exception):
    """Raised when step-up verification fails."""
