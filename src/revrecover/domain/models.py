"""Core domain model: a Case is one at-risk rupee item with an explicit lifecycle.

Lifecycle:
    DETECTED -> DIAGNOSED -> PLANNED -> INTERVENING <-> WAITING
        -> RECOVERED | PARTIALLY_RECOVERED | ESCALATED | ABANDONED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CaseType(str, Enum):
    PAYMENT_FAILURE = "payment_failure"
    SUBSCRIPTION_FAILURE = "subscription_failure"
    OVERDUE_INVOICE = "overdue_invoice"
    CHECKOUT_ABANDONED = "checkout_abandoned"


class CaseState(str, Enum):
    DETECTED = "detected"
    DIAGNOSED = "diagnosed"
    PLANNED = "planned"
    INTERVENING = "intervening"
    WAITING = "waiting"
    RECOVERED = "recovered"
    PARTIALLY_RECOVERED = "partially_recovered"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"


TERMINAL_STATES: frozenset[CaseState] = frozenset(
    {
        CaseState.RECOVERED,
        CaseState.PARTIALLY_RECOVERED,
        CaseState.ESCALATED,
        CaseState.ABANDONED,
    }
)

_LEGAL: dict[CaseState, frozenset[CaseState]] = {
    CaseState.DETECTED: frozenset({CaseState.DIAGNOSED}) | TERMINAL_STATES,
    CaseState.DIAGNOSED: frozenset({CaseState.PLANNED}) | TERMINAL_STATES,
    CaseState.PLANNED: frozenset({CaseState.INTERVENING}) | TERMINAL_STATES,
    CaseState.INTERVENING: frozenset({CaseState.WAITING}) | TERMINAL_STATES,
    CaseState.WAITING: frozenset({CaseState.INTERVENING}) | TERMINAL_STATES,
}


class IllegalTransition(Exception):
    pass


@dataclass(frozen=True)
class CaseEvent:
    from_state: CaseState
    to_state: CaseState
    at: datetime
    reason: str | None = None


@dataclass
class Case:
    case_id: str
    case_type: CaseType
    customer_id: str
    amount_inr: int
    error_code: str
    detected_at: datetime
    state: CaseState = CaseState.DETECTED
    attempts: int = 0
    history: list[CaseEvent] = field(default_factory=list)
    method: str | None = None  # e.g. "upi", "card"
    issuer: str | None = None  # e.g. "HDFC"

    @property
    def cell(self) -> tuple[str, str] | None:
        """The (method, issuer) monitoring cell, when both are known."""
        if self.method and self.issuer:
            return (self.method, self.issuer)
        return None

    def transition(
        self, to_state: CaseState, *, at: datetime, reason: str | None = None
    ) -> None:
        allowed = _LEGAL.get(self.state, frozenset())
        if to_state not in allowed:
            raise IllegalTransition(
                f"{self.case_id}: {self.state.value} -> {to_state.value} not allowed"
            )
        if to_state in TERMINAL_STATES and not reason:
            raise ValueError(
                f"{self.case_id}: terminal state {to_state.value} requires a reason"
            )
        self.history.append(
            CaseEvent(from_state=self.state, to_state=to_state, at=at, reason=reason)
        )
        self.state = to_state

    def record_attempt(self) -> None:
        self.attempts += 1
