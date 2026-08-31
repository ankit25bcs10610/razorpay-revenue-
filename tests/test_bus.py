from datetime import datetime, timezone

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseType
from revrecover.gateway.bus import InMemoryBus, case_from_payload, case_to_payload
from revrecover.gateway.service import DemoIntake

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def make_case(case_id="case_b1") -> Case:
    return Case(
        case_id=case_id,
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_b1",
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=NOW,
    )


def test_entries_are_delivered_in_order_exactly_once_per_group():
    bus = InMemoryBus()
    bus.publish("cases", {"n": 1})
    bus.publish("cases", {"n": 2})
    seen = []
    assert bus.consume("cases", group="workers", handler=seen.append) == 2
    assert [e["n"] for e in seen] == [1, 2]
    assert bus.consume("cases", group="workers", handler=seen.append) == 0


def test_failed_handler_keeps_the_entry_for_redelivery():
    bus = InMemoryBus()
    bus.publish("cases", {"n": 1})
    calls = []

    def flaky(entry):
        calls.append(entry)
        if len(calls) == 1:
            raise RuntimeError("worker crashed")

    with pytest.raises(RuntimeError):
        bus.consume("cases", group="workers", handler=flaky)
    assert bus.pending("cases", group="workers") == 1
    assert bus.consume("cases", group="workers", handler=flaky) == 1  # redelivered
    assert bus.pending("cases", group="workers") == 0


def test_groups_are_independent():
    bus = InMemoryBus()
    bus.publish("cases", {"n": 1})
    a, b = [], []
    bus.consume("cases", group="a", handler=a.append)
    bus.consume("cases", group="b", handler=b.append)
    assert a == b == [{"n": 1}]


def test_case_payload_round_trip():
    case = make_case()
    assert case_from_payload(case_to_payload(case)) == case


def test_gateway_to_worker_pipeline_over_the_bus():
    bus = InMemoryBus()
    intake = DemoIntake(audit=AuditChain())

    # producer side (what the gateway's intake seam does)
    bus.publish("cases", case_to_payload(make_case("case_p1")))
    bus.publish("cases", case_to_payload(make_case("case_p2")))
    # worker side
    processed = bus.consume(
        "cases", group="recovery", handler=lambda e: intake(case_from_payload(e))
    )
    assert processed == 2
    assert [c.case_id for c in intake.cases] == ["case_p1", "case_p2"]
