"""Indeed-specific exceptions.

Caught inside the provider and never exposed to the rest of
the application. External callers only see ProviderResponse
with success=False.
"""


class IndeedError(Exception):
    """Base exception for all Indeed provider errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class IndeedAuthError(IndeedError):
    """Raised when authentication with Indeed fails (invalid API key)."""


class IndeedRateLimitError(IndeedError):
    """Raised when Indeed returns a 429 rate-limit response."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Rate limited by Indeed. Retry after {retry_after}s",
            status_code=429,
        )


class IndeedNotFoundError(IndeedError):
    """Raised when a requested job is not found on Indeed."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job '{job_id}' not found on Indeed", status_code=404)
