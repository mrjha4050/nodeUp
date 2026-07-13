"""LinkedIn browser provider exceptions.

Caught inside the provider and never exposed to the rest of
the application. External callers only see ProviderResponse
with success=False.
"""


class LinkedInBrowserError(Exception):
    """Base exception for all LinkedIn browser provider errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class LinkedInAuthRequiredError(LinkedInBrowserError):
    """Raised when the browser session is not authenticated."""

    def __init__(self) -> None:
        super().__init__(
            "LinkedIn login required. Run with --login to authenticate.",
            status_code=401,
        )


class LinkedInPageLoadError(LinkedInBrowserError):
    """Raised when a LinkedIn page fails to load."""

    def __init__(self, url: str, reason: str = "") -> None:
        msg = f"Failed to load {url}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, status_code=500)
