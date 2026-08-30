from datetime import datetime, timezone

from revrecover.detection.scorer import FailureClass, score
from revrecover.domain.models import Case, CaseType

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def make_case(case_type=CaseType.SUBSCRIPTION_FAILURE, error_code="INSUFFICIENT_FUNDS") -> Case:
    return Case(
        case_id="case_0001",
        case_type=case_type,
        customer_id="cust_001",
        amount_inr=2499,
        error_code=error_code,
        detected_at=NOW,
    )


def test_hard_failure_codes_are_not_pursued():
    for code in ("CARD_BLOCKED", "ACCOUNT_CLOSED", "FRAUD_SUSPECTED"):
        assessment = score(make_case(error_code=code))
        assert assessment.pursue is False
        assert assessment.failure_class is FailureClass.HARD
        assert assessment.p_recover == 0.0


def test_insufficient_funds_is_soft_and_routed_to_dunning():
    assessment = score(make_case(error_code="INSUFFICIENT_FUNDS"))
    assert assessment.pursue is True
    assert assessment.failure_class is FailureClass.SOFT
    assert assessment.p_recover >= 0.6
    assert assessment.playbook == "dunning"


def test_transient_issuer_failure_scores_highest():
    transient = score(make_case(error_code="ISSUER_UNAVAILABLE"))
    nsf = score(make_case(error_code="INSUFFICIENT_FUNDS"))
    assert transient.pursue is True
    assert transient.p_recover > nsf.p_recover


def test_expired_card_needs_customer_action_via_message():
    assessment = score(make_case(error_code="CARD_EXPIRED"))
    assert assessment.pursue is True
    assert assessment.playbook == "update_method"


def test_overdue_invoice_routes_to_receivables_chaser():
    case = make_case(case_type=CaseType.OVERDUE_INVOICE, error_code="OVERDUE")
    assert score(case).playbook == "receivables"


def test_abandoned_checkout_routes_to_checkout_recovery():
    case = make_case(case_type=CaseType.CHECKOUT_ABANDONED, error_code="SESSION_EXPIRED")
    assert score(case).playbook == "checkout_recovery"


def test_unknown_error_code_gets_conservative_low_score():
    assessment = score(make_case(error_code="SOMETHING_NEW"))
    assert assessment.p_recover <= 0.3
    assert assessment.playbook == "manual_review"
