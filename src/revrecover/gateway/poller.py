"""Reconciliation poller: sweep the Payments API for failures the webhook
channel missed.

Webhooks are a notification channel, not a source of truth — deliveries
drop. The poller and the gateway share one EventLedger keyed by case_id,
so a payment seen on either path is processed exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from revrecover.actuators.razorpay_client import RazorpayClient
from revrecover.domain.models import Case
from revrecover.gateway.events import EventLedger, case_from_payment_entity


@dataclass
class ReconciliationPoller:
    client: RazorpayClient
    ledger: EventLedger
    intake: Callable[[Case], None]

    def sweep(self, *, from_ts: int, to_ts: int, at: datetime) -> int:
        ingested = 0
        for entity in self.client.list_payments(from_ts=from_ts, to_ts=to_ts):
            if entity.get("status") != "failed":
                continue
            case = case_from_payment_entity(entity, at=at)
            if not self.ledger.register(case.case_id):
                continue
            self.intake(case)
            ingested += 1
        return ingested
