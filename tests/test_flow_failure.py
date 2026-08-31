from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ActionKind, ComplianceEngine
from revrecover.workflows.flow import TransientActuatorError, run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def issuer_outage_scenario() -> Scenario:
    case = Case(
        case_id="case_f001",
        case_type=CaseType.PAYMENT_FAILURE,  # not mandate-bound
        customer_id="cust_f001",
        amount_inr=4999,
        error_code="ISSUER_UNAVAILABLE",  # smart_retry playbook
        detected_at=BATCH_START,
    )
    return Scenario(case=case, persona=Persona.SALARY_CYCLE)


class OutageOnFirstRetry:
    def __init__(self):
        self.retry_calls = 0

    def __call__(self, action, case) -> None:
        if action.kind is ActionKind.RETRY:
            self.retry_calls += 1
            if self.retry_calls == 1:
                raise TransientActuatorError("issuer gateway 5xx: HDFC UPI down")


def test_outage_mid_retry_is_absorbed_and_case_still_recovers(engine):
    audit = AuditChain()
    result = run_case(
        issuer_outage_scenario(), engine=engine, audit=audit,
        executor=OutageOnFirstRetry(),
    )
    assert result.case.state is CaseState.RECOVERED
    failures = [r for r in audit.records_for_case("case_f001") if r.stage == "ACT_FAILED"]
    assert len(failures) == 1
    assert "HDFC" in failures[0].payload["error"]


def test_total_outage_never_crashes_and_ends_with_a_reason(engine):
    def always_down(action, case):
        raise TransientActuatorError("everything is down")

    audit = AuditChain()
    result = run_case(
        issuer_outage_scenario(), engine=engine, audit=audit, executor=always_down
    )
    assert result.case.state in (CaseState.ABANDONED, CaseState.ESCALATED)
    assert result.case.history[-1].reason
    assert result.recovered_inr == 0


def test_failed_actions_do_not_count_as_customer_contacts(engine):
    def always_down(action, case):
        raise TransientActuatorError("down")

    result = run_case(
        issuer_outage_scenario(), engine=engine, audit=AuditChain(), executor=always_down
    )
    assert result.contacts_made == 0
