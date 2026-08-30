from pathlib import Path

import pytest

from revrecover.evaluation.batch import run_batch

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture(scope="module")
def report():
    return run_batch(n=200, seed=42, policy_path=POLICY_PATH)


def test_batch_is_deterministic_for_a_given_seed(report):
    again = run_batch(n=200, seed=42, policy_path=POLICY_PATH)
    assert again == report


def test_agent_recovers_more_than_do_nothing_baseline(report):
    assert report.recovered_inr > report.baseline_do_nothing_inr


def test_agent_recovers_more_than_naive_retry_baseline(report):
    assert report.recovered_inr > report.baseline_naive_retry_inr


def test_recovery_is_never_total_because_never_payers_exist(report):
    assert 0 < report.recovered_inr < report.total_at_risk_inr


def test_audit_chain_is_intact_after_full_batch(report):
    assert report.audit_intact is True
    assert report.audit_records > report.n_cases  # multiple records per case


def test_false_positive_cost_is_measured_not_hidden(report):
    # Contacts to self-cure customers (who would have paid anyway) must be
    # counted as annoyance cost, and a 200-case batch will contain some.
    assert report.annoyance_contacts > 0


def test_every_case_reaches_a_terminal_outcome(report):
    assert (
        report.recovered_cases + report.escalated_cases + report.abandoned_cases
        == report.n_cases
    )
