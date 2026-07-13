"""Job deduplication service.

Uses a strategy pattern so the matching algorithm can be swapped.
The default strategy uses exact-match on (company, title, location).
An embedding-based strategy can be plugged in later without touching
any calling code.
"""

from abc import ABC, abstractmethod

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Strategy interface
# ------------------------------------------------------------------

class DedupStrategy(ABC):
    """Abstract interface for deduplication strategies.

    Each strategy receives a list of jobs and returns a deduplicated list.
    """

    @abstractmethod
    def deduplicate(self, jobs: list[Job]) -> list[Job]:
        """Remove duplicate jobs from the list.

        Args:
            jobs: Merged job list from all providers.

        Returns:
            Deduplicated list, preserving the order of first occurrence.
        """
        ...


# ------------------------------------------------------------------
# Exact-match strategy (company + title + location)
# ------------------------------------------------------------------

class ExactMatchStrategy(DedupStrategy):
    """Deduplicates by normalizing and comparing company, title, and location."""

    def deduplicate(self, jobs: list[Job]) -> list[Job]:
        seen: set[str] = set()
        unique: list[Job] = []

        for job in jobs:
            key = self._make_key(job)
            if key not in seen:
                seen.add(key)
                unique.append(job)
            else:
                logger.debug(
                    "dedup_duplicate_found",
                    kept=unique[-1].id if unique else "",
                    dropped=job.id,
                    key=key,
                )

        return unique

    @staticmethod
    def _make_key(job: Job) -> str:
        """Build a normalized dedup key from company + title + location."""
        company = job.company_info.name.strip().lower()
        title = job.title.strip().lower()
        location = job.location.strip().lower()
        return f"{company}::{title}::{location}"


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------

class DeduplicationService:
    """Runs deduplication over a list of jobs using a pluggable strategy.

    Default strategy is ExactMatchStrategy. Pass a different strategy
    (e.g. an embedding-based one) to the constructor to swap behavior.
    """

    def __init__(self, strategy: DedupStrategy | None = None) -> None:
        self._strategy = strategy or ExactMatchStrategy()

    @property
    def strategy_name(self) -> str:
        return type(self._strategy).__name__

    def deduplicate(self, jobs: list[Job]) -> list[Job]:
        """Deduplicate a list of jobs.

        Args:
            jobs: Raw merged list (may contain cross-provider duplicates).

        Returns:
            Deduplicated list, first occurrence wins.
        """
        before = len(jobs)
        result = self._strategy.deduplicate(jobs)
        after = len(result)

        logger.info(
            "dedup_complete",
            strategy=self.strategy_name,
            before=before,
            after=after,
            removed=before - after,
        )
        return result
