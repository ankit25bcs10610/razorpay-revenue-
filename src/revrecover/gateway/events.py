"""Translate Razorpay webhook events into domain Cases, with dedupe.

Webhooks are a notification channel, not a source of truth — Razorpay
retries undelivered events, so duplicates are normal and the ledger makes
processing idempotent. Amounts arrive in paise and are stored as INR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from revrecover.domain.models import Case, CaseType


def _paise_to_inr(paise: int) -> int:
    return paise // 100


def _error_code(entity: dict) -> str:
    return str(entity.get("error_reason") or entity.get("error_code") or "UNKNOWN").upper()


def case_from_payment_entity(entity: dict, *, at: datetime) -> Case:
    return Case(
        case_id=f"case_{entity['id']}",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id=entity.get("customer_id", "unknown"),
        amount_inr=_paise_to_inr(entity["amount"]),
        error_code=_error_code(entity),
        detected_at=at,
    )


def parse_event(payload: dict, *, at: datetime) -> Case | None:
    event = payload.get("event")
    entities = payload.get("payload", {})

    if event == "payment.failed":
        return case_from_payment_entity(entities["payment"]["entity"], at=at)

    if event == "subscription.halted":
        subscription = entities["subscription"]["entity"]
        payment = entities.get("payment", {}).get("entity", {})
        return Case(
            case_id=f"case_{subscription['id']}",
            case_type=CaseType.SUBSCRIPTION_FAILURE,
            customer_id=subscription.get("customer_id", "unknown"),
            amount_inr=_paise_to_inr(payment.get("amount", 0)),
            error_code=_error_code(payment),
            detected_at=at,
        )

    if event == "invoice.expired":
        entity = entities["invoice"]["entity"]
        return Case(
            case_id=f"case_{entity['id']}",
            case_type=CaseType.OVERDUE_INVOICE,
            customer_id=entity.get("customer_id", "unknown"),
            amount_inr=_paise_to_inr(entity["amount"]),
            error_code="OVERDUE",
            detected_at=at,
        )

    return None


@dataclass
class EventLedger:
    _seen: set[str] = field(default_factory=set)

    def register(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        return True
