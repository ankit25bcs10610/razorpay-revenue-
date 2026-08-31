import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from revrecover.evaluation.harness import Persona
from revrecover.gateway.app import create_app
from revrecover.gateway.pipeline import RecoveryService
from revrecover.policy.compliance import ComplianceEngine
from revrecover.storage.sqlite import SqliteAuditChain

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
SECRET = "whsec_test"
DAYTIME = datetime(2026, 8, 31, 8, 30, tzinfo=UTC)  # 14:00 IST


@pytest.fixture
def harness():
    service = RecoveryService(
        engine=ComplianceEngine.from_yaml(POLICY_PATH),
        audit=SqliteAuditChain(":memory:"),
        persona_for=lambda case: Persona.COOPERATIVE,
    )
    app = create_app(
        webhook_secret=SECRET,
        intake=service.enqueue,
        processor=service.process_pending,
        admin_token="tok",
        clock=lambda: DAYTIME,
        dashboard=service.render_dashboard,
    )
    return TestClient(app), service


def post_failed_payment(client, payment_id):
    body = json.dumps(
        {"event": "payment.failed",
         "payload": {"payment": {"entity": {
             "id": payment_id, "amount": 249900,
             "customer_id": "cust_ld", "error_reason": "insufficient_funds"}}}}
    ).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    client.post("/webhooks/razorpay", content=body,
                headers={"x-razorpay-signature": sig, "x-razorpay-event-id": payment_id})


def test_dashboard_route_serves_html_with_auto_refresh(harness):
    client, _ = harness
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'http-equiv="refresh"' in response.text
    assert "0 cases" in response.text


def test_processed_cases_appear_on_the_live_dashboard(harness):
    client, _ = harness
    post_failed_payment(client, "pay_LD1")
    client.post("/admin/process", headers={"x-admin-token": "tok"})
    page = client.get("/dashboard").text
    assert "case_pay_LD1" in page
    assert "₹2,499" in page
    assert "chain intact" in page


def test_live_dashboard_escapes_untrusted_content(harness):
    client, service = harness
    service.audit.append(
        case_id="case_pay_LD1", stage="DETECT",
        payload={"note": "<script>alert(1)</script>"}, at=DAYTIME,
    )
    post_failed_payment(client, "pay_LD1")
    client.post("/admin/process", headers={"x-admin-token": "tok"})
    page = client.get("/dashboard").text
    assert "<script>alert(1)</script>" not in page
