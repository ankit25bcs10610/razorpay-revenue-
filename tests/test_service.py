from datetime import UTC, datetime

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseType
from revrecover.gateway.service import DemoIntake

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_case(error_code="INSUFFICIENT_FUNDS") -> Case:
    return Case(
        case_id="case_pay_ABC",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_X",
        amount_inr=2499,
        error_code=error_code,
        detected_at=NOW,
    )


def test_intake_scores_the_case_and_audits_detection():
    audit = AuditChain()
    intake = DemoIntake(audit=audit)
    intake(make_case())
    records = audit.records_for_case("case_pay_ABC")
    assert [r.stage for r in records] == ["DETECT"]
    assert records[0].payload["pursue"] is True
    assert records[0].payload["playbook"] == "dunning"


def test_intake_retains_cases_for_inspection():
    intake = DemoIntake(audit=AuditChain())
    intake(make_case())
    intake(make_case(error_code="CARD_BLOCKED"))
    assert len(intake.cases) == 2


def test_hard_failures_are_marked_not_pursued():
    audit = AuditChain()
    DemoIntake(audit=audit)(make_case(error_code="FRAUD_SUSPECTED"))
    record = audit.records_for_case("case_pay_ABC")[0]
    assert record.payload["pursue"] is False
