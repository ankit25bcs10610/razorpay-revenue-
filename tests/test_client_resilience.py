import httpx
import pytest

from revrecover.actuators.razorpay_client import (
    CircuitOpenError,
    RazorpayClient,
    RazorpayError,
)


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self):
        return self.now


def make_client(handler, *, fake: FakeTime, **kwargs) -> RazorpayClient:
    return RazorpayClient(
        key_id="k", key_secret="s",
        transport=httpx.MockTransport(handler),
        sleeper=fake.sleep, clock=fake.monotonic, jitter=lambda: 0.0,
        **kwargs,
    )


def test_transient_5xx_is_retried_with_growing_backoff():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(502, json={"error": {"description": "bad gateway"}})
        return httpx.Response(200, json={"id": "pay_1", "status": "captured"})

    fake = FakeTime()
    payment = make_client(handler, fake=fake).fetch_payment("pay_1")
    assert payment["status"] == "captured"
    assert len(calls) == 3
    assert len(fake.sleeps) == 2
    assert fake.sleeps[1] > fake.sleeps[0]  # exponential


def test_client_errors_are_never_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": {"description": "bad request"}})

    fake = FakeTime()
    with pytest.raises(RazorpayError, match="bad request"):
        make_client(handler, fake=fake).fetch_payment("pay_1")
    assert len(calls) == 1


def test_persistent_5xx_exhausts_retries():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"error": {"description": "down"}})

    fake = FakeTime()
    with pytest.raises(RazorpayError, match="down"):
        make_client(handler, fake=fake, max_retries=2).fetch_payment("pay_1")
    assert len(calls) == 3  # initial + 2 retries


def test_breaker_opens_after_consecutive_failures_and_recovers_after_cooldown():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) <= 9:
            return httpx.Response(503, json={"error": {"description": "down"}})
        return httpx.Response(200, json={"id": "pay_1", "status": "captured"})

    fake = FakeTime()
    client = make_client(
        handler, fake=fake, max_retries=2, breaker_threshold=3, breaker_cooldown_s=30.0
    )
    # three requests that exhaust retries = three consecutive failures -> open
    for _ in range(3):
        with pytest.raises(RazorpayError):
            client.fetch_payment("pay_1")
    transport_calls = len(calls)

    with pytest.raises(CircuitOpenError):
        client.fetch_payment("pay_1")
    assert len(calls) == transport_calls  # open circuit never hit the wire

    fake.now += 31.0  # cooldown elapses -> half-open probe allowed
    payment = client.fetch_payment("pay_1")
    assert payment["status"] == "captured"
    payment = client.fetch_payment("pay_1")  # closed again, normal traffic
    assert payment["status"] == "captured"
