from pathlib import Path

import pytest

from revrecover.evaluation.batch import run_batch

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture(scope="module")
def report():
    return run_batch(n=200, seed=42, policy_path=POLICY_PATH, learning=True)


def test_recovery_is_broken_down_by_playbook(report):
    assert report.recovered_by_playbook
    assert sum(report.recovered_by_playbook.values()) == report.recovered_inr
    assert all(v > 0 for v in report.recovered_by_playbook.values())


def test_stop_reason_counts_cover_every_case(report):
    assert sum(report.stop_reasons.values()) == report.n_cases
    assert "payment captured" in report.stop_reasons


def test_unrecoverable_cases_are_visible_as_a_stop_reason(report):
    assert report.stop_reasons.get("not recoverable", 0) > 0


def test_mean_actions_per_recovered_case_is_reported(report):
    assert report.actions_per_recovery >= 1.0


def test_time_to_recovery_percentiles(report):
    assert 0 <= report.p50_days_to_recovery <= report.p95_days_to_recovery
    assert report.p95_days_to_recovery <= 5  # playbooks span at most a few days
