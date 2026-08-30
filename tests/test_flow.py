from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_scenario(
    persona: Persona,
    *,
    error_code="INSUFFICIENT_FUNDS",
    case_type=CaseType.SUBSCRIPTION_FAILURE,
    amount_inr=2499,
) -> Scenario:
    case = Case(
        case_id="case_t001",
        case_type=case_type,
        customer_id="cust_t001",
        amount_inr=amount_inr,
        error_code=error_code,
        detected_at=BATCH_START,
    )
    return Scenario(case=case, persona=persona)


def test_cooperative_customer_case_is_recovered_in_full(engine):
    scenario = make_scenario(Persona.COOPERATIVE)
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state is CaseState.RECOVERED
    assert result.recovered_inr == 2499


def test_never_payer_stops_after_max_attempts_never_a_fourth(engine):
    scenario = make_scenario(Persona.NEVER_PAYER)
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state in (CaseState.ABANDONED, CaseState.ESCALATED)
    assert len(result.actions_executed) == engine.max_attempts_per_case


def test_hard_failure_is_abandoned_without_touching_the_customer(engine):
    scenario = make_scenario(Persona.NEVER_PAYER, error_code="CARD_BLOCKED")
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state is CaseState.ABANDONED
    assert result.actions_executed == []
    assert result.contacts_made == 0


def test_opt_out_is_honored_immediately_no_further_contact(engine):
    scenario = make_scenario(Persona.DISPUTER)
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state is CaseState.ABANDONED
    assert result.contacts_made == 1


def test_promise_to_pay_is_tracked_and_followed_up_until_paid(engine):
    scenario = make_scenario(Persona.PROMISE_BREAKER)
    audit = AuditChain()
    result = run_case(scenario, engine=engine, audit=audit)
    assert result.case.state is CaseState.RECOVERED
    stages = [r.stage for r in audit.records_for_case("case_t001")]
    assert "PROMISE_TO_PAY" in stages


def test_salary_cycle_customer_recovered_via_second_attempt_retry(engine):
    scenario = make_scenario(Persona.SALARY_CYCLE)
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state is CaseState.RECOVERED
    assert result.actions_executed[-1].kind.value == "retry"


def test_kill_switch_executes_nothing_and_escalates(engine):
    scenario = make_scenario(Persona.COOPERATIVE)
    result = run_case(scenario, engine=engine, audit=AuditChain(), kill_switch=True)
    assert result.actions_executed == []
    assert result.case.state is CaseState.ESCALATED


def test_high_value_action_records_human_approval_in_audit(engine):
    scenario = make_scenario(Persona.COOPERATIVE, amount_inr=75000)
    audit = AuditChain()
    run_case(scenario, engine=engine, audit=audit)
    decide_records = [r for r in audit.records_for_case("case_t001") if r.stage == "DECIDE"]
    assert any(r.payload.get("hitl_approved") is True for r in decide_records)


def test_every_case_ends_with_outcome_record_and_intact_chain(engine):
    audit = AuditChain()
    for persona in (Persona.COOPERATIVE, Persona.NEVER_PAYER, Persona.DISPUTER):
        scenario = make_scenario(persona)
        run_case(scenario, engine=engine, audit=audit)
    assert audit.verify() == (True, None)
    outcomes = [r for r in audit._records if r.stage == "OUTCOME"]
    assert len(outcomes) == 3


def test_terminal_case_always_has_a_reason(engine):
    scenario = make_scenario(Persona.NEVER_PAYER)
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.history[-1].reason
