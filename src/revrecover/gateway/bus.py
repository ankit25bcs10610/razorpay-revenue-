"""Event bus with Redis-Streams semantics: ordered entries, consumer
groups, at-least-once delivery with per-entry ack.

The in-memory implementation is contract-compatible with a Redis Streams
backend (XADD/XREADGROUP/XACK): a group's entry stays pending until its
handler returns, and a crashed handler means redelivery on the next
consume. Swapping in Redis changes this module only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from revrecover.domain.models import Case, CaseType


@dataclass
class _Group:
    cursor: int = 0          # next un-fetched entry index
    pending: list[int] = field(default_factory=list)  # delivered, not acked


@dataclass
class InMemoryBus:
    _streams: dict[str, list[dict]] = field(default_factory=dict)
    _groups: dict[tuple[str, str], _Group] = field(default_factory=dict)

    def publish(self, stream: str, payload: dict) -> str:
        entries = self._streams.setdefault(stream, [])
        entries.append(payload)
        return f"{stream}-{len(entries) - 1}"

    def consume(
        self, stream: str, *, group: str, handler: Callable[[dict], Any]
    ) -> int:
        entries = self._streams.get(stream, [])
        state = self._groups.setdefault((stream, group), _Group())
        # claim new entries into the pending list, then work pending in order
        while state.cursor < len(entries):
            state.pending.append(state.cursor)
            state.cursor += 1
        processed = 0
        while state.pending:
            index = state.pending[0]
            handler(entries[index])  # an exception leaves the entry pending
            state.pending.pop(0)     # ack
            processed += 1
        return processed

    def pending(self, stream: str, *, group: str) -> int:
        return len(self._groups.get((stream, group), _Group()).pending)


def case_to_payload(case: Case) -> dict:
    return {
        "case_id": case.case_id,
        "case_type": case.case_type.value,
        "customer_id": case.customer_id,
        "amount_inr": case.amount_inr,
        "error_code": case.error_code,
        "detected_at": case.detected_at.isoformat(),
    }


def case_from_payload(payload: dict) -> Case:
    return Case(
        case_id=payload["case_id"],
        case_type=CaseType(payload["case_type"]),
        customer_id=payload["customer_id"],
        amount_inr=payload["amount_inr"],
        error_code=payload["error_code"],
        detected_at=datetime.fromisoformat(payload["detected_at"]),
    )
