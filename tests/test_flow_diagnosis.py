import json
from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.diagnosis.diagnostician import Diagnostician
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import Channel, ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_scenario(persona=Persona.COOPERATIVE) -> Scenario:
    case = Case(
        case_id="case_d001",
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        customer_id="cust_d001",
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=BATCH_START,
    )
    return Scenario(case=case, persona=persona)


class FixedLLM:
    def __init__(self, playbook: str):
        self.playbook = playbook

    def complete(self, *, system: str, user: str, schema: dict) -> str:
        return json.dumps(
            {
                "cause": "B2B receivable pattern detected",
                "failure_class": "soft",
                "recovery_odds": 0.7,
                "confidence": 0.9,
                "recommended_playbook": self.playbook,
                "human_summary": "Treat as receivable; chase by email.",
            }
        )


class DownLLM:
    def complete(self, *, system: str, user: str, schema: dict) -> str:
        raise RuntimeError("api down")


def test_confident_llm_diagnosis_selects_the_playbook(engine):
    diagnostician = Diagnostician(FixedLLM("receivables"))
    result = run_case(
        make_scenario(), engine=engine, audit=AuditChain(), diagnostician=diagnostician
    )
    # receivables playbook opens with an email, dunning would open with WhatsApp
    assert result.actions_executed[0].channel is Channel.EMAIL


def test_diagnose_stage_is_audited_with_source_and_summary(engine):
    audit = AuditChain()
    run_case(
        make_scenario(), engine=engine, audit=audit,
        diagnostician=Diagnostician(FixedLLM("dunning")),
    )
    diagnose = [r for r in audit.records_for_case("case_d001") if r.stage == "DIAGNOSE"]
    assert len(diagnose) == 1
    assert diagnose[0].payload["source"] == "llm"
    assert diagnose[0].payload["human_summary"]


def test_llm_outage_degrades_to_rules_and_still_recovers(engine):
    audit = AuditChain()
    result = run_case(
        make_scenario(), engine=engine, audit=audit,
        diagnostician=Diagnostician(DownLLM()),
    )
    assert result.case.state is CaseState.RECOVERED
    diagnose = [r for r in audit.records_for_case("case_d001") if r.stage == "DIAGNOSE"]
    assert diagnose[0].payload["source"] == "fallback"


def test_without_a_diagnostician_behavior_is_unchanged(engine):
    result = run_case(make_scenario(), engine=engine, audit=AuditChain())
    assert result.actions_executed[0].channel is Channel.WHATSAPP  # dunning default
