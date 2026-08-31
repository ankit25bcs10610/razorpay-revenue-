"""The live test-mode loop: one real rupee-cycle on real Razorpay rails.

Story: a payment failed; the agent issues a *real* Payment Link via the
test-mode API; the customer pays it in the browser with a test card; the
agent detects the capture by polling the link (no public webhook URL
needed) and closes the case RECOVERED — with real Razorpay object IDs in
the hash-chained audit trail.

Run it:  make live-demo   (requires RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET
test-mode credentials; everything is testable offline via MockTransport.)
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from revrecover.actuators.razorpay_client import RazorpayClient
from revrecover.domain.models import Case, CaseState, CaseType


@dataclass(frozen=True)
class LiveOutcome:
    case: Case
    recovered_inr: int
    short_url: str
    payment_id: str | None


@dataclass
class LiveRecoveryLoop:
    client: RazorpayClient
    audit: Any  # AuditChain-shaped
    sleeper: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    poll_interval_s: float = 5.0
    timeout_s: float = 600.0
    on_progress: Callable[[str], None] = lambda line: None

    def run(self, *, amount_inr: int, description: str, customer_id: str) -> LiveOutcome:
        now = datetime.now(UTC)
        link = self.client.create_payment_link(
            amount_inr=amount_inr,
            description=description,
            reference_id=f"revrecover:{customer_id}:{int(now.timestamp())}",
        )
        case = Case(
            case_id=f"case_live_{link.id}",
            case_type=CaseType.PAYMENT_FAILURE,
            customer_id=customer_id,
            amount_inr=amount_inr,
            error_code="LIVE_DEMO_FAILURE",
            detected_at=now,
        )
        self.audit.append(
            case_id=case.case_id, stage="DETECT",
            payload={"amount_inr": amount_inr, "scenario": "failed payment (live demo)"},
            at=now,
        )
        self.audit.append(
            case_id=case.case_id, stage="ACT",
            payload={"action": "payment_link_issued", "link_id": link.id, "short_url": link.short_url},
            at=now,
        )
        case.transition(CaseState.DIAGNOSED, at=now)
        case.transition(CaseState.PLANNED, at=now)
        case.transition(CaseState.INTERVENING, at=now)
        case.record_attempt()
        self.on_progress(f"payment link issued: {link.short_url}")

        deadline = self.clock() + self.timeout_s
        first = True
        while True:
            if not first:
                self.sleeper(self.poll_interval_s)
            first = False
            entity = self.client.fetch_payment_link(link.id)
            if entity.get("status") == "paid":
                payment_id = next(
                    (p.get("payment_id") for p in entity.get("payments", [])), None
                )
                paid_at = datetime.now(UTC)
                case.transition(CaseState.RECOVERED, at=paid_at, reason="payment captured (live)")
                self.audit.append(
                    case_id=case.case_id, stage="OUTCOME",
                    payload={"state": "recovered", "recovered_inr": amount_inr,
                             "payment_id": payment_id, "link_id": link.id},
                    at=paid_at,
                )
                return LiveOutcome(
                    case=case, recovered_inr=amount_inr,
                    short_url=link.short_url, payment_id=payment_id,
                )
            self.on_progress(f"waiting for payment… (status: {entity.get('status')})")
            if self.clock() >= deadline:
                timed_out_at = datetime.now(UTC)
                case.transition(
                    CaseState.ABANDONED, at=timed_out_at,
                    reason="payment link not paid within the demo window",
                )
                self.audit.append(
                    case_id=case.case_id, stage="OUTCOME",
                    payload={"state": "abandoned", "reason": "not paid within window",
                             "link_id": link.id},
                    at=timed_out_at,
                )
                return LiveOutcome(
                    case=case, recovered_inr=0, short_url=link.short_url, payment_id=None
                )


def main() -> None:
    from revrecover.audit.chain import AuditChain

    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id.startswith("rzp_test_") or not key_secret:
        raise SystemExit(
            "live demo needs TEST-MODE credentials:\n"
            "  export RAZORPAY_KEY_ID=rzp_test_...\n  export RAZORPAY_KEY_SECRET=...\n"
            "(live-mode keys are refused on purpose)"
        )

    audit = AuditChain()
    loop = LiveRecoveryLoop(
        client=RazorpayClient(key_id=key_id, key_secret=key_secret),
        audit=audit,
        on_progress=lambda line: print(f"  … {line}"),
    )
    print("RevRecover — LIVE test-mode recovery loop")
    print("=" * 56)
    amount = int(os.environ.get("LIVE_DEMO_AMOUNT_INR", 99))
    outcome = loop.run(
        amount_inr=amount, description="RevRecover live demo — recovery link",
        customer_id="cust_live_demo",
    )
    print(f"\n  Pay in a browser: {outcome.short_url}")
    print("  (test card 4111 1111 1111 1111, any future expiry, any CVV)\n")
    for record in audit.records_for_case(outcome.case.case_id):
        summary = ", ".join(f"{k}={v}" for k, v in record.payload.items())
        print(f"  [{record.at:%H:%M:%S}] {record.stage:<8} {summary}")
    print("=" * 56)
    print(
        f"outcome: {outcome.case.state.value} — recovered ₹{outcome.recovered_inr:,} "
        f"(payment {outcome.payment_id}) · chain intact={audit.verify()[0]}"
    )


if __name__ == "__main__":
    main()
