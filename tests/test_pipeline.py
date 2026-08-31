import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from revrecover.domain.models import CaseState
from revrecover.evaluation.harness import Persona
from revrecover.gateway.app import create_app
from revrecover.gateway.pipeline import RecoveryService
from revrecover.policy.compliance import ComplianceEngine
from revrecover.storage.sqlite import SqliteAuditChain

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
SECRET = "whsec_test"


def payment_failed(payment_id: str, customer_id: str, error="insufficient_funds") -> bytes:
    return json.dumps(
        {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": 249900,
                        "customer_id": customer_id,
                        "error_reason": error,
                    }
                }
            },
        }
    ).encode()


def signed(body: bytes, event_id: str) -> dict:
    return {
        "x-razorpay-signature": hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
        "x-razorpay-event-id": event_id,
    }


@pytest.fixture
def service() -> RecoveryService:
    return RecoveryService(
        engine=ComplianceEngine.from_yaml(POLICY_PATH),
        audit=SqliteAuditChain(":memory:"),
        persona_for=lambda case: Persona.COOPERATIVE,
    )


def make_client(service: RecoveryService) -> TestClient:
    app = create_app(webhook_secret=SECRET, intake=service.enqueue, processor=service.process_pending)
    return TestClient(app)


def test_webhook_to_recovery_end_to_end(service):
    client = make_client(service)
    body = payment_failed("pay_E2E1", "cust_e2e")
    assert client.post("/webhooks/razorpay", content=body, headers=signed(body, "e1")).json()["status"] == "accepted"

    results = service.process_pending()
    assert len(results) == 1
    assert results[0].case.state is CaseState.RECOVERED
    assert results[0].recovered_inr == 2499
    stages = [r.stage for r in service.audit.records_for_case("case_pay_E2E1")]
    assert stages[0] == "DETECT" and stages[-1] == "OUTCOME"
    assert service.audit.verify() == (True, None)


def test_admin_process_endpoint_drives_the_worker(service):
    client = make_client(service)
    body = payment_failed("pay_E2E2", "cust_e2e2")
    client.post("/webhooks/razorpay", content=body, headers=signed(body, "e2"))
    summary = client.post("/admin/process").json()
    assert summary == {"processed": 1, "recovered_inr": 2499}


def test_opt_out_in_one_case_protects_the_customer_in_the_next():
    service = RecoveryService(
        engine=ComplianceEngine.from_yaml(POLICY_PATH),
        audit=SqliteAuditChain(":memory:"),
        persona_for=lambda case: Persona.DISPUTER,
    )
    client = make_client(service)
    first = payment_failed("pay_O1", "cust_optout")
    client.post("/webhooks/razorpay", content=first, headers=signed(first, "o1"))
    service.process_pending()

    second = payment_failed("pay_O2", "cust_optout")
    client.post("/webhooks/razorpay", content=second, headers=signed(second, "o2"))
    results = service.process_pending()
    assert results[0].case.state is CaseState.ABANDONED
    assert "opted out" in results[0].case.history[-1].reason
    assert results[0].actions_executed == []


def test_default_persona_assignment_is_deterministic():
    service = RecoveryService(
        engine=ComplianceEngine.from_yaml(POLICY_PATH),
        audit=SqliteAuditChain(":memory:"),
    )
    from datetime import UTC, datetime

    from revrecover.gateway.events import case_from_payment_entity

    entity = {"id": "pay_D", "amount": 100000, "customer_id": "cust_d"}
    case = case_from_payment_entity(entity, at=datetime(2026, 8, 31, tzinfo=UTC))
    assert service.persona_for(case) is service.persona_for(case)
