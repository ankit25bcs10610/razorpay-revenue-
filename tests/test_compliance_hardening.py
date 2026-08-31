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
DAYTIME = datetime(2026, 8, 31, 14, 0, tzinfo=IST)

RETRY = ProposedAction(kind=ActionKind.RETRY)
NUDGE = ProposedAction(kind=ActionKind.MESSAGE, channel=Channel.WHATSAPP)


@pytest.fixture
def engine() -> ComplianceEngine:
    return ComplianceEngine.from_yaml(POLICY_PATH)


def make_case(case_type=CaseType.PAYMENT_FAILURE, error_code="INSUFFICIENT_FUNDS") -> Case:
    return Case(
        case_id="case_0001",
        case_type=case_type,
        customer_id="cust_001",
        amount_inr=2499,
        error_code=error_code,
        detected_at=DAYTIME,
    )


# --- daily action budget -------------------------------------------------

def test_action_blocked_when_daily_budget_is_spent(engine):
    decision = engine.check(
        RETRY, case=make_case(), contact_history=[], now=DAYTIME,
        actions_today=engine.daily_action_budget,
    )
    assert decision.allowed is False
    assert "daily_action_budget" in decision.failed_checks


def test_action_allowed_under_budget(engine):
    decision = engine.check(
        RETRY, case=make_case(), contact_history=[], now=DAYTIME, actions_today=10
    )
    assert decision.allowed is True


# --- e-mandate rules (subscription retries) ------------------------------

def test_mandate_retry_needs_pre_debit_notification(engine):
    subscription = make_case(case_type=CaseType.SUBSCRIPTION_FAILURE)
    decision = engine.check(
        RETRY, case=subscription, contact_history=[], now=DAYTIME
    )
    assert decision.allowed is False
    assert "pre_debit_notification" in decision.failed_checks


def test_mandate_retry_allowed_after_24h_notification(engine):
    subscription = make_case(case_type=CaseType.SUBSCRIPTION_FAILURE)
    notified = [DAYTIME - timedelta(hours=24)]
    decision = engine.check(
        RETRY, case=subscription, contact_history=notified, now=DAYTIME
    )
    assert decision.allowed is True


def test_mandate_representment_cap(engine):
    subscription = make_case(case_type=CaseType.SUBSCRIPTION_FAILURE)
    notified = [DAYTIME - timedelta(hours=25)]
    decision = engine.check(
        RETRY, case=subscription, contact_history=notified, now=DAYTIME,
        retries_so_far=engine.max_representments,
    )
    assert decision.allowed is False
    assert "max_representments" in decision.failed_checks


def test_one_off_payment_retry_is_not_mandate_bound(engine):
    decision = engine.check(
        RETRY, case=make_case(case_type=CaseType.PAYMENT_FAILURE),
        contact_history=[], now=DAYTIME,
    )
    assert decision.allowed is True


def test_messages_are_not_mandate_bound(engine):
    subscription = make_case(case_type=CaseType.SUBSCRIPTION_FAILURE)
    decision = engine.check(NUDGE, case=subscription, contact_history=[], now=DAYTIME)
    assert decision.allowed is True
