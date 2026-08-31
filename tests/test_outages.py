from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.detection.monitor import SuccessRateMonitor
from revrecover.detection.outages import OutageRegistry
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.gateway.events import parse_event
from revrecover.policy.compliance import ActionKind, ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
T0 = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
UPI_HDFC = ("upi", "HDFC")


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def test_registry_marks_and_expires_outages():
    registry = OutageRegistry(ttl_hours=6)
    registry.mark(UPI_HDFC, at=T0)
    assert registry.active(UPI_HDFC, at=T0 + timedelta(hours=5)) is True
    assert registry.active(UPI_HDFC, at=T0 + timedelta(hours=7)) is False
    assert registry.active(("card", "ICICI"), at=T0) is False


def test_monitor_alert_feeds_the_registry():
    monitor, registry = SuccessRateMonitor(), OutageRegistry(ttl_hours=6)
    for _ in range(100):
        monitor.observe(cell=UPI_HDFC, success=True, amount_inr=500, at=T0)
    for _ in range(60):
        alert = monitor.observe(cell=UPI_HDFC, success=False, amount_inr=500, at=T0)
        if alert:
            registry.mark(alert.cell, at=alert.at)
    assert registry.active(UPI_HDFC, at=T0) is True


def test_webhook_payment_carries_method_and_issuer():
    payload = {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": "pay_M1", "amount": 100000, "customer_id": "cust_m",
            "error_reason": "issuer_unavailable", "method": "upi", "bank": "HDFC",
        }}},
    }
    case = parse_event(payload, at=T0)
    assert case.cell == ("upi", "HDFC")


def outage_scenario() -> Scenario:
    case = Case(
        case_id="case_out1",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_out1",
        amount_inr=4999,
        error_code="ISSUER_UNAVAILABLE",  # smart_retry: retry, retry, message
        detected_at=BATCH_START,
        method="upi",
        issuer="HDFC",
    )
    return Scenario(case=case, persona=Persona.SALARY_CYCLE)


def test_flow_defers_retries_while_the_cell_is_in_outage(engine):
    registry = OutageRegistry(ttl_hours=6)
    registry.mark(UPI_HDFC, at=BATCH_START)
    audit = AuditChain()
    result = run_case(outage_scenario(), engine=engine, audit=audit, outages=registry)

    deferred = [r for r in audit.records_for_case("case_out1") if r.stage == "DEFERRED"]
    assert deferred and deferred[0].payload["reason"] == "issuer_outage"
    # first retry deferred 24h; outage (6h ttl) has expired by the second
    # step, the retry lands on attempt 2 and the salary-cycle customer pays
    assert result.case.state is CaseState.RECOVERED
    assert [a.kind for a in result.actions_executed] == [ActionKind.RETRY]


def test_cases_in_other_cells_are_unaffected(engine):
    registry = OutageRegistry(ttl_hours=6)
    registry.mark(("card", "ICICI"), at=BATCH_START)
    result = run_case(outage_scenario(), engine=engine, audit=AuditChain(), outages=registry)
    assert result.actions_executed[0].kind is ActionKind.RETRY  # not deferred
