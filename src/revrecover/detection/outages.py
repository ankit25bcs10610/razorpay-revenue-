"""Outage registry: the bridge from the degradation monitor to the flow.

When the monitor fires a DegradationAlert for a (method × issuer) cell,
mark it here; the flow defers retries for cases in that cell until the
mark expires — no point burning representments into a down issuer. Marks
expire by TTL, so recovery is automatic and time-deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class OutageRegistry:
    ttl_hours: float = 6.0
    _marked_at: dict[tuple, datetime] = field(default_factory=dict)

    def mark(self, cell: tuple, *, at: datetime) -> None:
        self._marked_at[cell] = at

    def clear(self, cell: tuple) -> None:
        self._marked_at.pop(cell, None)

    def active(self, cell: tuple, *, at: datetime) -> bool:
        marked = self._marked_at.get(cell)
        if marked is None:
            return False
        return at - marked < timedelta(hours=self.ttl_hours)
