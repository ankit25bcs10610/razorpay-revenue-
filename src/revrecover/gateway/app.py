"""Webhook gateway: verify, dedupe, translate, hand off — then ACK fast.

The intake callable is the seam to the rest of the system: in-process case
runner today, Redis Streams producer later, with no change here. Signature
failure is the only rejection; everything else returns 200 so Razorpay
stops retrying events we have already seen or don't care about.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Request, Response

from revrecover.domain.models import Case
from revrecover.gateway.events import EventLedger, parse_event
from revrecover.gateway.signature import verify_signature


def create_app(
    *,
    webhook_secret: str,
    intake: Callable[[Case], None],
    ledger: EventLedger | None = None,
) -> FastAPI:
    app = FastAPI(title="RevRecover Webhook Gateway")
    event_ledger = ledger or EventLedger()

    @app.post("/webhooks/razorpay")
    async def razorpay_webhook(request: Request, response: Response) -> dict:
        body = await request.body()
        signature = request.headers.get("x-razorpay-signature", "")
        if not verify_signature(body, signature, webhook_secret):
            response.status_code = 401
            return {"status": "invalid signature"}

        event_id = request.headers.get("x-razorpay-event-id", "")
        if event_id and not event_ledger.register(event_id):
            return {"status": "duplicate"}

        case = parse_event(await request.json(), at=datetime.now(timezone.utc))
        if case is None:
            return {"status": "ignored"}
        # Case-level dedupe shared with the reconciliation poller: the same
        # payment seen on both paths is processed exactly once.
        if not event_ledger.register(case.case_id):
            return {"status": "duplicate"}

        intake(case)
        return {"status": "accepted", "case_id": case.case_id}

    return app
