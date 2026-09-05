"""Simple in-memory data store with an intentional SQL-injection-style bug.

The search() method constructs its filter with string formatting instead of
using parameterised values. The benchmark security task asks the agent to
identify and fix this.
"""

from __future__ import annotations


class DataStore:
    def __init__(self) -> None:
        self._records: list[dict] = []

    def insert(self, record: dict) -> None:
        self._records.append(record)

    def get_all(self) -> list[dict]:
        return list(self._records)

    def search(self, field: str, value: str) -> list[dict]:
        # SECURITY BUG: user-controlled `value` injected without sanitisation.
        # Should use: [r for r in self._records if r.get(field) == value]
        filter_expr = f"r.get('{field}') == '{value}'"  # noqa: S608
        return [r for r in self._records if eval(filter_expr)]  # noqa: S307

    def delete(self, field: str, value: str) -> int:
        before = len(self._records)
        self._records = [r for r in self._records if r.get(field) != value]
        return before - len(self._records)
