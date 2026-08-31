from datetime import UTC, datetime
from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.detection.scorer import score
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.evaluation.tuning import tune_pursue_floor
from revrecover.policy.compliance import ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_case(error_code="SOMETHING_NEW") -> Case:
    return Case(
        case_id="case_t1",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_t1",
        amount_inr=999,
        error_code=error_code,
        detected_at=BATCH_START,
    )


def test_scorer_honors_an_explicit_pursue_floor():
    unknown = make_case("SOMETHING_NEW")  # prior 0.3
    assert score(unknown).pursue is True
    assert score(unknown, pursue_floor=0.4).pursue is False
    nsf = make_case("INSUFFICIENT_FUNDS")  # prior 0.68
    assert score(nsf, pursue_floor=0.4).pursue is True


def test_flow_honors_the_tuned_floor(engine):
    scenario = Scenario(case=make_case("SOMETHING_NEW"), persona=Persona.COOPERATIVE)
    result = run_case(scenario, engine=engine, audit=AuditChain(), pursue_floor=0.4)
    assert result.case.state is CaseState.ABANDONED
    assert "not recoverable" in result.case.history[-1].reason


def test_tuner_picks_a_candidate_deterministically(engine):
    first = tune_pursue_floor(seed=42, engine=engine, candidates=(0.2, 0.4))
    second = tune_pursue_floor(seed=42, engine=engine, candidates=(0.2, 0.4))
    assert first == second
    assert first.pursue_floor in (0.2, 0.4)
    assert first.holdout_net_inr > 0


def test_tuner_holdout_differs_from_the_measured_batch(engine):
    tuned = tune_pursue_floor(seed=42, engine=engine, candidates=(0.2,))
    from revrecover.evaluation.harness import generate_scenarios

    # holdout uses a derived seed: same ids would mean tuning on the
    # measured batch, which the protocol forbids
    assert tuned.holdout_error_codes != tuple(
        s.case.error_code for s in generate_scenarios(n=tuned.holdout_n, seed=42)
    )
