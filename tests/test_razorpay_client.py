import json

import httpx
import pytest

from revrecover.actuators.razorpay_client import PaymentLink, RazorpayClient, RazorpayError


def make_client(handler) -> RazorpayClient:
    return RazorpayClient(
        key_id="rzp_test_key",
        key_secret="secret",
        transport=httpx.MockTransport(handler),
    )


def test_create_payment_link_sends_paise_and_returns_link():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization", "")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"id": "plink_001", "short_url": "https://rzp.io/i/abc", "status": "created"},
        )

    link = make_client(handler).create_payment_link(
        amount_inr=2499, description="Subscription renewal", reference_id="case_0001:2"
    )

    assert captured["path"] == "/v1/payment_links"
    assert captured["auth"].startswith("Basic ")
    assert captured["body"]["amount"] == 249900  # INR -> paise
    assert captured["body"]["currency"] == "INR"
    assert captured["body"]["reference_id"] == "case_0001:2"  # idempotency handle
    assert link == PaymentLink(id="plink_001", short_url="https://rzp.io/i/abc", status="created")


def test_api_error_raises_razorpay_error_with_description():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"description": "reference_id already exists"}}
        )

    with pytest.raises(RazorpayError, match="reference_id already exists"):
        make_client(handler).create_payment_link(
            amount_inr=100, description="x", reference_id="dup"
        )


def test_fetch_payment_gets_the_entity():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payments/pay_ABC123"
        return httpx.Response(200, json={"id": "pay_ABC123", "status": "failed"})

    payment = make_client(handler).fetch_payment("pay_ABC123")
    assert payment["status"] == "failed"
