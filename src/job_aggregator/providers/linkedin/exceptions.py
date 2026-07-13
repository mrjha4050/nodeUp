"""LinkedIn-specific exceptions.

These are caught inside the provider and never leak
out to the rest of the application. External callers
only see ProviderResponse with success=False.
"""


class LinkedInError(Exception):
    """Base exception for all LinkedIn provider errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class LinkedInAuthError(LinkedInError):
    """Raised when authentication with LinkedIn fails."""


class LinkedInRateLimitError(LinkedInError):
    """Raised when LinkedIn returns a 429 rate-limit response."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Rate limited by LinkedIn. Retry after {retry_after}s",
            status_code=429,
        )


class LinkedInNotFoundError(LinkedInError):
    """Raised when a requested job is not found on LinkedIn."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job '{job_id}' not found on LinkedIn", status_code=404)
