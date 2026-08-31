from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ComplianceEngine
from revrecover.policy.ev import rank_interventions
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_case(error_code="INSUFFICIENT_FUNDS", case_type=CaseType.SUBSCRIPTION_FAILURE, amount_inr=2499):
    return Case(
        case_id="case_ev1",
        case_type=case_type,
        customer_id="cust_ev1",
        amount_inr=amount_inr,
        error_code=error_code,
        detected_at=BATCH_START,
    )


def test_nsf_ranks_dunning_over_blind_retry():
    ranked = rank_interventions(make_case("INSUFFICIENT_FUNDS"))
    assert len(ranked) >= 2
    chosen = [r for r in ranked if r.chosen]
    assert len(chosen) == 1
    assert chosen[0].playbook == "dunning"
    assert chosen[0].ev_inr == max(r.ev_inr for r in ranked)
    assert all(r.rejected_reason == "lower EV" for r in ranked if not r.chosen)


def test_transient_issuer_failure_prefers_smart_retry():
    ranked = rank_interventions(make_case("ISSUER_UNAVAILABLE"))
    assert next(r for r in ranked if r.chosen).playbook == "smart_retry"


def test_tiny_amounts_are_not_worth_chasing():
    ranked = rank_interventions(make_case(amount_inr=20))
    assert all(not r.chosen for r in ranked)
    assert all(r.ev_inr <= 0 for r in ranked)


def test_invoice_has_a_single_receivables_candidate():
    ranked = rank_interventions(
        make_case("OVERDUE", case_type=CaseType.OVERDUE_INVOICE)
    )
    assert [r.playbook for r in ranked] == ["receivables"]


def test_flow_audits_the_plan_with_considered_alternatives(engine):
    audit = AuditChain()
    scenario = Scenario(case=make_case(), persona=Persona.COOPERATIVE)
    result = run_case(scenario, engine=engine, audit=audit)
    plans = [r for r in audit.records_for_case("case_ev1") if r.stage == "PLAN"]
    assert len(plans) == 1
    considered = plans[0].payload["considered"]
    assert len(considered) >= 2
    assert sum(1 for c in considered if c["chosen"]) == 1
    assert result.playbook == "dunning"


def test_flow_abandons_negative_ev_cases_before_spending_money(engine):
    audit = AuditChain()
    scenario = Scenario(case=make_case(amount_inr=20), persona=Persona.COOPERATIVE)
    result = run_case(scenario, engine=engine, audit=audit)
    assert result.case.state is CaseState.ABANDONED
    assert "expected value" in result.case.history[-1].reason
    assert result.actions_executed == []
