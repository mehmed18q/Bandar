"""When and how soon a failed forward is retried (a strategy object, no Qt)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from bandar.core.diagnostics import Problem


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter: 1s, 2s, 4s … capped at ``max_delay``.

    ``max_attempts`` of 0 means "keep trying"; problems that need the user's
    attention (a wrong context, a busy port) are never retried automatically.
    """

    enabled: bool = True
    max_attempts: int = 0
    max_delay: float = 30.0
    base_delay: float = 1.0
    jitter: float = 0.15

    @classmethod
    def from_settings(cls, settings: dict) -> RetryPolicy:
        return cls(
            enabled=settings["autoRetry"],
            max_attempts=settings["maxRetries"],
            max_delay=float(settings["retryMaxDelay"]),
        )

    def allows(self, attempt: int, problem: Problem) -> bool:
        """May ``attempt`` (1-based, the one about to be scheduled) run?"""
        if not (self.enabled and problem.retryable):
            return False
        return self.max_attempts == 0 or attempt <= self.max_attempts

    def delay(self, attempt: int, rng=random.random) -> float:
        exponent = min(max(attempt - 1, 0), 16)
        delay = min(self.max_delay, self.base_delay * 2**exponent)
        return max(0.5, delay * (1 + self.jitter * (rng() * 2 - 1)))
