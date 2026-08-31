from pathlib import Path

import pytest

from revrecover.evaluation.batch import run_batch

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture(scope="module")
def static_report():
    return run_batch(n=400, seed=2026, policy_path=POLICY_PATH)


@pytest.fixture(scope="module")
def learning_report():
    return run_batch(n=400, seed=2026, policy_path=POLICY_PATH, learning=True)


def test_learning_recovers_more_than_the_static_default(static_report, learning_report):
    assert learning_report.recovered_inr > static_report.recovered_inr


def test_report_carries_a_four_quartile_learning_curve(learning_report):
    assert len(learning_report.learning_curve_pct) == 4
    assert all(0 <= q <= 100 for q in learning_report.learning_curve_pct)


def test_learning_flag_is_reported(static_report, learning_report):
    assert static_report.learning_enabled is False
    assert learning_report.learning_enabled is True


def test_learning_batch_is_deterministic(learning_report):
    again = run_batch(n=400, seed=2026, policy_path=POLICY_PATH, learning=True)
    assert again == learning_report


def test_learning_still_cannot_reach_total_recovery(learning_report):
    assert learning_report.recovered_inr < learning_report.total_at_risk_inr
