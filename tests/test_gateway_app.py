import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from revrecover.domain.models import CaseType
from revrecover.gateway.app import create_app

SECRET = "whsec_test_123"

PAYMENT_FAILED = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_ABC123",
                "amount": 249900,
                "customer_id": "cust_XYZ",
                "error_reason": "insufficient_funds",
            }
        }
    },
}


def signed_headers(body: bytes, event_id: str = "evt_001") -> dict:
    return {
        "x-razorpay-signature": hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
        "x-razorpay-event-id": event_id,
    }


@pytest.fixture
def harness():
    received = []
    app = create_app(webhook_secret=SECRET, intake=received.append)
    return TestClient(app), received


def test_valid_signed_event_is_accepted_and_becomes_a_case(harness):
    client, received = harness
    body = json.dumps(PAYMENT_FAILED).encode()
    response = client.post("/webhooks/razorpay", content=body, headers=signed_headers(body))
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert len(received) == 1
    assert received[0].case_type is CaseType.PAYMENT_FAILURE
    assert received[0].amount_inr == 2499


def test_bad_signature_is_rejected_and_nothing_is_processed(harness):
    client, received = harness
    body = json.dumps(PAYMENT_FAILED).encode()
    headers = signed_headers(body) | {"x-razorpay-signature": "0" * 64}
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 401
    assert received == []


def test_duplicate_event_id_is_processed_only_once(harness):
    client, received = harness
    body = json.dumps(PAYMENT_FAILED).encode()
    first = client.post("/webhooks/razorpay", content=body, headers=signed_headers(body, "evt_9"))
    second = client.post("/webhooks/razorpay", content=body, headers=signed_headers(body, "evt_9"))
    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert len(received) == 1


def test_irrelevant_event_is_acknowledged_but_ignored(harness):
    client, received = harness
    body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
    response = client.post("/webhooks/razorpay", content=body, headers=signed_headers(body))
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert received == []
