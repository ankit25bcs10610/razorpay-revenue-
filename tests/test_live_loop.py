import json

import httpx

from revrecover.actuators.live_loop import LiveRecoveryLoop
from revrecover.actuators.razorpay_client import RazorpayClient
from revrecover.audit.chain import AuditChain
from revrecover.domain.models import CaseState


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self):
        return self.now


def make_client(handler, fake) -> RazorpayClient:
    return RazorpayClient(
        key_id="rzp_test_k", key_secret="s",
        transport=httpx.MockTransport(handler),
        sleeper=fake.sleep, clock=fake.monotonic, jitter=lambda: 0.0,
    )


def paying_handler(pays_after_polls: int):
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/payment_links":
            body = json.loads(request.content)
            assert body["amount"] == 9900  # paise on the wire
            return httpx.Response(
                200, json={"id": "plink_L1", "short_url": "https://rzp.io/i/live1", "status": "created"},
            )
        if request.method == "GET" and request.url.path == "/v1/payment_links/plink_L1":
            state["polls"] += 1
            if state["polls"] >= pays_after_polls:
                return httpx.Response(
                    200,
                    json={"id": "plink_L1", "status": "paid",
                          "payments": [{"payment_id": "pay_LIVE1", "status": "captured"}]},
                )
            return httpx.Response(200, json={"id": "plink_L1", "status": "created", "payments": []})
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    return handler


def test_fetch_payment_link_gets_the_entity():
    fake = FakeTime()
    client = make_client(paying_handler(pays_after_polls=1), fake)
    link = client.fetch_payment_link("plink_L1")
    assert link["status"] == "paid"


def test_live_loop_recovers_when_the_link_is_paid():
    fake = FakeTime()
    audit = AuditChain()
    loop = LiveRecoveryLoop(
        client=make_client(paying_handler(pays_after_polls=3), fake),
        audit=audit, sleeper=fake.sleep, clock=fake.monotonic,
        poll_interval_s=5.0, timeout_s=600.0,
    )
    outcome = loop.run(amount_inr=99, description="Live demo recovery", customer_id="cust_live")

    assert outcome.case.state is CaseState.RECOVERED
    assert outcome.recovered_inr == 99
    assert outcome.payment_id == "pay_LIVE1"
    assert outcome.short_url == "https://rzp.io/i/live1"
    assert fake.sleeps.count(5.0) == 2  # slept between the three polls
    stages = [r.stage for r in audit.records_for_case(outcome.case.case_id)]
    assert stages == ["DETECT", "ACT", "OUTCOME"]
    assert audit.verify() == (True, None)


def test_live_loop_times_out_gracefully():
    fake = FakeTime()
    audit = AuditChain()
    loop = LiveRecoveryLoop(
        client=make_client(paying_handler(pays_after_polls=10_000), fake),
        audit=audit, sleeper=fake.sleep, clock=fake.monotonic,
        poll_interval_s=10.0, timeout_s=30.0,
    )
    outcome = loop.run(amount_inr=99, description="x", customer_id="cust_live")
    assert outcome.case.state is CaseState.ABANDONED
    assert "not paid" in outcome.case.history[-1].reason
    assert outcome.recovered_inr == 0
