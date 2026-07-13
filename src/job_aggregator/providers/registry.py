
import asyncio

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.base import JobProvider

logger = get_logger(__name__)


class ProviderRegistry:
    """Registry for managing job providers."""

    def __init__(self) -> None:
        self.providers: dict[str, JobProvider] = {}

    def register(self, provider: JobProvider) -> None:
        """Register a new job provider."""
        if provider.provider_name in self.providers:
            logger.warning("provider_already_registered", provider=provider.provider_name)
        else:
            self.providers[provider.provider_name] = provider
            logger.info("provider_registered", provider=provider.provider_name)

    def get(self, name: str) -> JobProvider | None:
        """Retrieve a registered job provider by name."""
        return self.providers.get(name)

    def get_all(self) -> dict[str, JobProvider]:
        """Retrieve all registered job providers."""
        return self.providers

    def list_names(self) -> list[str]:
        """List the names of all registered job providers."""
        return list(self.providers.keys())

    async def health_check_all(self, timeout: float = 10.0) -> dict[str, bool]:
        """Check all providers concurrently with a per-provider timeout."""

        async def _check(name: str, provider: JobProvider) -> tuple[str, bool]:
            try:
                result = await asyncio.wait_for(provider.health_check(), timeout=timeout)
                return name, result
            except asyncio.TimeoutError:
                logger.warning("health_check_timeout", provider=name, timeout=timeout)
                return name, False
            except Exception:
                logger.exception("health_check_failed", provider=name)
                return name, False

        results = await asyncio.gather(
            *[_check(n, p) for n, p in self.providers.items()]
        )
        return dict(results)