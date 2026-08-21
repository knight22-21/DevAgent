"""Token budget tracker for a single agent session.

Tracks token usage across LLM calls. Supports an optional hard cap
(max_tokens) and a warning threshold (warn_at_percent from config).
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(Exception):
    """Raised when an LLM call would exceed the session token budget."""


@dataclass
class TokenBudget:
    """Lightweight budget tracker -- no Pydantic dependency."""
    max_tokens: int | None = None       # None = unlimited
    warn_at_percent: int = 80           # emit BudgetWarningEvent above this %

    def __post_init__(self) -> None:
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._call_count: int = 0

    @property
    def total_used(self) -> int:
        return self._input_tokens + self._output_tokens

    @property
    def input_tokens(self) -> int:
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        return self._output_tokens

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def remaining(self) -> int | None:
        if self.max_tokens is None:
            return None
        return max(0, self.max_tokens - self.total_used)

    @property
    def is_exhausted(self) -> bool:
        if self.max_tokens is None:
            return False
        return self.total_used >= self.max_tokens

    @property
    def warn_threshold(self) -> float | None:
        if self.max_tokens is None:
            return None
        return self.warn_at_percent / 100.0

    def check(self, estimated_prompt_tokens: int = 0) -> None:
        """Raise BudgetExceeded if adding estimated tokens would exceed limit."""
        if self.max_tokens is None:
            return
        if self.total_used + estimated_prompt_tokens > self.max_tokens:
            raise BudgetExceeded(
                f"Token budget exceeded: {self.total_used} used of {self.max_tokens}"
            )

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from one LLM response."""
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._call_count += 1

    def summary(self) -> dict:
        return {
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens": self.total_used,
            "llm_calls": self._call_count,
            "max_tokens": self.max_tokens,
            "remaining": self.remaining,
        }
