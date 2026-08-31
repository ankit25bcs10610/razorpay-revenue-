from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ActionKind, Channel, ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def email_preferring_reminder_customer() -> Scenario:
    case = Case(
        case_id="case_c001",
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        customer_id="cust_c001",
        amount_inr=2499,
        error_code="CARD_EXPIRED",  # update_method playbook: three messages
        detected_at=BATCH_START,
    )
    return Scenario(
        case=case,
        persona=Persona.NEEDS_REMINDER,
        segment="business",
        preferred_channel=Channel.EMAIL,
    )


def test_off_channel_nudges_lose_the_customer(engine):
    result = run_case(
        email_preferring_reminder_customer(),
        engine=engine,
        audit=AuditChain(),
        channel_chooser=lambda case: Channel.WHATSAPP,
    )
    assert result.case.state is not CaseState.RECOVERED


def test_choosing_the_preferred_channel_recovers_the_money(engine):
    result = run_case(
        email_preferring_reminder_customer(),
        engine=engine,
        audit=AuditChain(),
        channel_chooser=lambda case: Channel.EMAIL,
    )
    assert result.case.state is CaseState.RECOVERED
    assert result.recovered_inr == 2499


def test_chooser_overrides_every_message_channel(engine):
    result = run_case(
        email_preferring_reminder_customer(),
        engine=engine,
        audit=AuditChain(),
        channel_chooser=lambda case: Channel.SMS,
    )
    messages = [a for a in result.actions_executed if a.kind is ActionKind.MESSAGE]
    assert messages and all(a.channel is Channel.SMS for a in messages)


def test_chooser_cannot_bypass_the_kill_switch(engine):
    result = run_case(
        email_preferring_reminder_customer(),
        engine=engine,
        audit=AuditChain(),
        channel_chooser=lambda case: Channel.EMAIL,
        kill_switch=True,
    )
    assert result.actions_executed == []


def test_without_chooser_playbook_defaults_apply(engine):
    result = run_case(
        email_preferring_reminder_customer(), engine=engine, audit=AuditChain()
    )
    assert result.actions_executed[0].channel is Channel.WHATSAPP  # update_method default
