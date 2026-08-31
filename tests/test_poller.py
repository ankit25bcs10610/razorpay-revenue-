from datetime import UTC, datetime

import httpx

from revrecover.actuators.razorpay_client import RazorpayClient
from revrecover.gateway.events import EventLedger
from revrecover.gateway.poller import ReconciliationPoller

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)

PAYMENTS_PAGE = {
    "count": 3,
    "items": [
        {"id": "pay_A", "status": "failed", "amount": 249900,
         "customer_id": "cust_1", "error_reason": "insufficient_funds"},
        {"id": "pay_B", "status": "captured", "amount": 100000, "customer_id": "cust_2"},
        {"id": "pay_C", "status": "failed", "amount": 50000,
         "customer_id": "cust_3", "error_code": "GATEWAY_TIMEOUT"},
    ],
}


def make_client(captured: dict) -> RazorpayClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["path"] = request.url.path
        return httpx.Response(200, json=PAYMENTS_PAGE)

    return RazorpayClient(
        key_id="rzp_test", key_secret="s", transport=httpx.MockTransport(handler)
    )


def test_list_payments_queries_the_window():
    captured = {}
    items = make_client(captured).list_payments(from_ts=100, to_ts=200)
    assert captured["path"] == "/v1/payments"
    assert captured["params"] == {"from": "100", "to": "200", "count": "100"}
    assert len(items) == 3


def test_sweep_ingests_only_failed_payments():
    received = []
    poller = ReconciliationPoller(
        client=make_client({}), ledger=EventLedger(), intake=received.append
    )
    ingested = poller.sweep(from_ts=100, to_ts=200, at=NOW)
    assert ingested == 2
    assert [c.case_id for c in received] == ["case_pay_A", "case_pay_C"]
    assert received[0].error_code == "INSUFFICIENT_FUNDS"
    assert received[0].amount_inr == 2499


def test_sweep_is_idempotent():
    received = []
    poller = ReconciliationPoller(
        client=make_client({}), ledger=EventLedger(), intake=received.append
    )
    poller.sweep(from_ts=100, to_ts=200, at=NOW)
    second = poller.sweep(from_ts=100, to_ts=200, at=NOW)
    assert second == 0
    assert len(received) == 2


def test_poller_skips_payments_already_seen_via_webhook():
    received = []
    ledger = EventLedger()
    ledger.register("case_pay_A")  # the webhook path registered this case
    poller = ReconciliationPoller(client=make_client({}), ledger=ledger, intake=received.append)
    ingested = poller.sweep(from_ts=100, to_ts=200, at=NOW)
    assert ingested == 1
    assert [c.case_id for c in received] == ["case_pay_C"]
