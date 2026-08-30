from datetime import datetime, timezone

import pytest

from revrecover.domain.models import (
    Case,
    CaseState,
    CaseType,
    IllegalTransition,
    TERMINAL_STATES,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def make_case() -> Case:
    return Case(
        case_id="case_0001",
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        customer_id="cust_001",
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=NOW,
    )


def test_new_case_starts_in_detected_state():
    assert make_case().state is CaseState.DETECTED


def test_follows_happy_path_to_recovered():
    case = make_case()
    case.transition(CaseState.DIAGNOSED, at=NOW)
    case.transition(CaseState.PLANNED, at=NOW)
    case.transition(CaseState.INTERVENING, at=NOW)
    case.transition(CaseState.RECOVERED, at=NOW, reason="payment captured")
    assert case.state is CaseState.RECOVERED


def test_rejects_illegal_transition():
    case = make_case()
    with pytest.raises(IllegalTransition):
        case.transition(CaseState.INTERVENING, at=NOW)  # skips DIAGNOSED/PLANNED


def test_terminal_state_requires_reason():
    case = make_case()
    with pytest.raises(ValueError, match="reason"):
        case.transition(CaseState.ABANDONED, at=NOW)


def test_no_transition_out_of_terminal_state():
    case = make_case()
    case.transition(CaseState.ESCALATED, at=NOW, reason="low confidence")
    with pytest.raises(IllegalTransition):
        case.transition(CaseState.DIAGNOSED, at=NOW)


def test_terminal_states_are_exactly_the_four_end_states():
    assert TERMINAL_STATES == {
        CaseState.RECOVERED,
        CaseState.PARTIALLY_RECOVERED,
        CaseState.ESCALATED,
        CaseState.ABANDONED,
    }


def test_history_records_every_transition_with_timestamp_and_reason():
    case = make_case()
    case.transition(CaseState.DIAGNOSED, at=NOW, reason="NSF, salary cycle")
    assert len(case.history) == 1
    event = case.history[0]
    assert event.from_state is CaseState.DETECTED
    assert event.to_state is CaseState.DIAGNOSED
    assert event.at == NOW
    assert event.reason == "NSF, salary cycle"


def test_waiting_can_bounce_back_to_intervening():
    case = make_case()
    case.transition(CaseState.DIAGNOSED, at=NOW)
    case.transition(CaseState.PLANNED, at=NOW)
    case.transition(CaseState.INTERVENING, at=NOW)
    case.transition(CaseState.WAITING, at=NOW)
    case.transition(CaseState.INTERVENING, at=NOW)
    assert case.state is CaseState.INTERVENING


def test_record_attempt_increments_counter():
    case = make_case()
    assert case.attempts == 0
    case.record_attempt()
    case.record_attempt()
    assert case.attempts == 2
