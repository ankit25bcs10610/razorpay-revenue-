from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ActionBudget, ActionKind, ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_scenario(
    persona=Persona.SALARY_CYCLE,
    *,
    case_type=CaseType.SUBSCRIPTION_FAILURE,
    error_code="ISSUER_UNAVAILABLE",
) -> Scenario:
    case = Case(
        case_id="case_h001",
        case_type=case_type,
        customer_id="cust_h001",
        amount_inr=2499,
        error_code=error_code,
        detected_at=BATCH_START,
    )
    return Scenario(case=case, persona=persona)


def test_mandate_blocked_retry_is_skipped_not_fatal(engine):
    # smart_retry opens with an un-noticed subscription retry: the step is
    # blocked by pre_debit_notification, but the flow moves on to later
    # steps instead of abandoning the case.
    audit = AuditChain()
    result = run_case(make_scenario(), engine=engine, audit=audit)
    blocked = [
        r for r in audit.records_for_case("case_h001")
        if r.stage == "DECIDE" and not r.payload["allowed"]
    ]
    assert blocked and all(
        "pre_debit_notification" in r.payload["failed_checks"] for r in blocked
    )
    executed_kinds = [a.kind for a in result.actions_executed]
    assert ActionKind.RETRY not in executed_kinds
    assert ActionKind.MESSAGE in executed_kinds  # later step still ran


def test_noticed_mandate_retry_still_works_in_dunning(engine):
    # dunning notifies on day 1, retries on day 2 — the notice satisfies
    # the e-mandate rule and the salary-cycle customer is recovered.
    scenario = make_scenario(error_code="INSUFFICIENT_FUNDS")
    result = run_case(scenario, engine=engine, audit=AuditChain())
    assert result.case.state is CaseState.RECOVERED


def test_exhausted_budget_escalates_with_zero_actions(engine):
    # The budget is per-day and blocked steps defer 24h, so exhaust every
    # day the playbook can reach before "nothing executable" is true.
    from datetime import timedelta

    budget = ActionBudget()
    for day in range(4):
        for _ in range(engine.daily_action_budget):
            budget.record(BATCH_START + timedelta(days=day))
    result = run_case(
        make_scenario(), engine=engine, audit=AuditChain(), budget=budget
    )
    assert result.actions_executed == []
    assert result.case.state is CaseState.ESCALATED
    assert "compliance" in result.case.history[-1].reason


def test_budget_counts_are_per_day(engine):
    budget = ActionBudget()
    budget.record(BATCH_START)
    assert budget.count(BATCH_START) == 1
    from datetime import timedelta

    assert budget.count(BATCH_START + timedelta(days=1)) == 0


def test_dry_run_logs_decisions_but_executes_nothing(engine):
    audit = AuditChain()
    result = run_case(
        make_scenario(Persona.COOPERATIVE, error_code="INSUFFICIENT_FUNDS"),
        engine=engine, audit=audit, dry_run=True,
    )
    assert result.actions_executed == []
    assert result.recovered_inr == 0
    decides = [r for r in audit.records_for_case("case_h001") if r.stage == "DECIDE"]
    assert decides and all(r.payload.get("dry_run") is True for r in decides)
    assert "dry run" in result.case.history[-1].reason
