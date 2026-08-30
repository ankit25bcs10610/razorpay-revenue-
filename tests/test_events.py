from datetime import datetime, timezone

from revrecover.domain.models import CaseType
from revrecover.gateway.events import EventLedger, parse_event

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

PAYMENT_FAILED = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_ABC123",
                "amount": 249900,  # paise
                "currency": "INR",
                "customer_id": "cust_XYZ",
                "error_code": "BAD_REQUEST_ERROR",
                "error_reason": "insufficient_funds",
            }
        }
    },
}

SUBSCRIPTION_HALTED = {
    "event": "subscription.halted",
    "payload": {
        "subscription": {"entity": {"id": "sub_DEF456", "customer_id": "cust_XYZ"}},
        "payment": {
            "entity": {"id": "pay_GHI789", "amount": 99900, "error_reason": "insufficient_funds"}
        },
    },
}

INVOICE_EXPIRED = {
    "event": "invoice.expired",
    "payload": {
        "invoice": {"entity": {"id": "inv_JKL012", "amount": 5000000, "customer_id": "cust_B2B"}}
    },
}


def test_payment_failed_becomes_a_payment_failure_case():
    case = parse_event(PAYMENT_FAILED, at=NOW)
    assert case.case_type is CaseType.PAYMENT_FAILURE
    assert case.case_id == "case_pay_ABC123"
    assert case.amount_inr == 2499  # paise converted
    assert case.error_code == "INSUFFICIENT_FUNDS"
    assert case.customer_id == "cust_XYZ"
    assert case.detected_at == NOW


def test_subscription_halted_becomes_a_subscription_failure_case():
    case = parse_event(SUBSCRIPTION_HALTED, at=NOW)
    assert case.case_type is CaseType.SUBSCRIPTION_FAILURE
    assert case.case_id == "case_sub_DEF456"
    assert case.amount_inr == 999


def test_invoice_expired_becomes_an_overdue_invoice_case():
    case = parse_event(INVOICE_EXPIRED, at=NOW)
    assert case.case_type is CaseType.OVERDUE_INVOICE
    assert case.amount_inr == 50000
    assert case.error_code == "OVERDUE"


def test_irrelevant_event_types_are_ignored():
    assert parse_event({"event": "payment.captured", "payload": {}}, at=NOW) is None


def test_ledger_accepts_an_event_id_only_once():
    ledger = EventLedger()
    assert ledger.register("evt_001") is True
    assert ledger.register("evt_001") is False
    assert ledger.register("evt_002") is True
