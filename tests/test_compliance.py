from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from revrecover.domain.models import Case, CaseType
from revrecover.policy.compliance import (
    ActionKind,
    Channel,
    ComplianceEngine,
    ProposedAction,
)

IST = ZoneInfo("Asia/Kolkata")
POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"

DAYTIME = datetime(2026, 8, 31, 14, 0, tzinfo=IST)   # 2 pm IST
NIGHT = datetime(2026, 8, 31, 22, 30, tzinfo=IST)    # 10:30 pm IST


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_case(
    *,
    error_code="INSUFFICIENT_FUNDS",
    amount_inr=2499,
    attempts=0,
    case_type=CaseType.SUBSCRIPTION_FAILURE,
) -> Case:
    case = Case(
        case_id="case_0001",
        case_type=case_type,
        customer_id="cust_001",
        amount_inr=amount_inr,
        error_code=error_code,
        detected_at=DAYTIME,
    )
    case.attempts = attempts
    return case


WHATSAPP_NUDGE = ProposedAction(kind=ActionKind.MESSAGE, channel=Channel.WHATSAPP)
RETRY = ProposedAction(kind=ActionKind.RETRY)


def test_daytime_message_within_limits_passes(engine):
    decision = engine.check(WHATSAPP_NUDGE, case=make_case(), contact_history=[], now=DAYTIME)
    assert decision.allowed is True
    assert decision.failed_checks == []
    assert decision.requires_approval is False


def test_message_blocked_during_quiet_hours(engine):
    decision = engine.check(WHATSAPP_NUDGE, case=make_case(), contact_history=[], now=NIGHT)
    assert decision.allowed is False
    assert "quiet_hours" in decision.failed_checks


def test_retry_is_not_a_customer_contact_so_quiet_hours_do_not_apply(engine):
    # one-off payment: not e-mandate bound, so quiet hours alone decide
    case = make_case(case_type=CaseType.PAYMENT_FAILURE)
    decision = engine.check(RETRY, case=case, contact_history=[], now=NIGHT)
    assert decision.allowed is True


def test_retry_blocked_for_never_retry_error_code(engine):
    decision = engine.check(RETRY, case=make_case(error_code="CARD_BLOCKED"), contact_history=[], now=DAYTIME)
    assert decision.allowed is False
    assert "never_retry_code" in decision.failed_checks


def test_blocked_when_case_attempt_cap_reached(engine):
    decision = engine.check(WHATSAPP_NUDGE, case=make_case(attempts=3), contact_history=[], now=DAYTIME)
    assert decision.allowed is False
    assert "max_attempts_per_case" in decision.failed_checks


def test_contact_blocked_when_weekly_frequency_cap_reached(engine):
    recent = [DAYTIME - timedelta(days=d, hours=2) for d in (1, 2, 3, 4)]  # 4 in past week
    decision = engine.check(WHATSAPP_NUDGE, case=make_case(), contact_history=recent, now=DAYTIME)
    assert decision.allowed is False
    assert "max_contacts_per_week" in decision.failed_checks


def test_contacts_older_than_a_week_do_not_count_toward_cap(engine):
    old = [DAYTIME - timedelta(days=d) for d in (10, 12, 15, 20)]
    decision = engine.check(WHATSAPP_NUDGE, case=make_case(), contact_history=old, now=DAYTIME)
    assert decision.allowed is True


def test_contact_blocked_within_min_gap_of_previous_contact(engine):
    decision = engine.check(
        WHATSAPP_NUDGE,
        case=make_case(),
        contact_history=[DAYTIME - timedelta(hours=5)],
        now=DAYTIME,
    )
    assert decision.allowed is False
    assert "min_gap_between_contacts" in decision.failed_checks


def test_high_value_action_passes_but_requires_human_approval(engine):
    case = make_case(amount_inr=75000, case_type=CaseType.PAYMENT_FAILURE)
    decision = engine.check(RETRY, case=case, contact_history=[], now=DAYTIME)
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_kill_switch_blocks_everything(engine):
    decision = engine.check(
        RETRY, case=make_case(), contact_history=[], now=DAYTIME, kill_switch=True
    )
    assert decision.allowed is False
    assert "kill_switch" in decision.failed_checks


def test_escalation_to_human_is_always_allowed(engine):
    escalate = ProposedAction(kind=ActionKind.ESCALATE)
    decision = engine.check(escalate, case=make_case(attempts=3), contact_history=[], now=NIGHT)
    assert decision.allowed is True
