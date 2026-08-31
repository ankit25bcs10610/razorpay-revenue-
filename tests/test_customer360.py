from datetime import timedelta
from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.memory.customer360 import Customer360
from revrecover.policy.compliance import Channel, ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_scenario(persona=Persona.NEEDS_REMINDER, customer_id="cust_x") -> Scenario:
    case = Case(
        case_id="case_c360",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id=customer_id,
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=BATCH_START,
    )
    return Scenario(case=case, persona=persona)


def test_weekly_contact_cap_holds_across_cases(engine):
    store = Customer360()
    for days_ago in (1, 2, 3, 4):  # a previous case already used the budget
        store.record_contact("cust_x", BATCH_START - timedelta(days=days_ago))
    result = run_case(
        make_scenario(), engine=engine, audit=AuditChain(), customer360=store
    )
    assert result.contacts_made == 0
    assert result.case.state is not CaseState.RECOVERED


def test_prior_opt_out_stops_a_new_case_before_any_action(engine):
    store = Customer360()
    store.record_opt_out("cust_x")
    result = run_case(
        make_scenario(), engine=engine, audit=AuditChain(), customer360=store
    )
    assert result.actions_executed == []
    assert result.case.state is CaseState.ABANDONED
    assert "opted out" in result.case.history[-1].reason


def test_flow_registers_new_opt_outs_in_the_store(engine):
    store = Customer360()
    run_case(
        make_scenario(persona=Persona.DISPUTER),
        engine=engine, audit=AuditChain(), customer360=store,
    )
    assert store.has_opted_out("cust_x") is True


def test_contacts_made_during_a_run_land_in_the_store(engine):
    store = Customer360()
    run_case(
        make_scenario(persona=Persona.COOPERATIVE),
        engine=engine, audit=AuditChain(), customer360=store,
    )
    assert len(store.contacts_for("cust_x")) >= 1


def test_recovery_records_a_channel_affinity_hint(engine):
    store = Customer360()
    store.record_recovery("cust_x", Channel.EMAIL)
    assert store.preferred_channel_hint("cust_x") is Channel.EMAIL
    assert store.preferred_channel_hint("cust_unknown") is None
