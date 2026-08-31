from pathlib import Path

from revrecover.evaluation.batch import run_batch, run_batch_full

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


def test_full_run_exposes_report_audit_and_results():
    run = run_batch_full(n=50, seed=42, policy_path=POLICY_PATH, learning=True)
    assert run.report.n_cases == 50
    assert len(run.results) == 50
    assert run.audit.verify() == (True, None)
    assert len(run.scenarios) == 50


def test_run_batch_report_matches_full_run():
    assert run_batch(n=50, seed=42, policy_path=POLICY_PATH) == run_batch_full(
        n=50, seed=42, policy_path=POLICY_PATH
    ).report


def test_batch_honors_a_tuned_pursue_floor():
    strict = run_batch(n=30, seed=42, policy_path=POLICY_PATH, pursue_floor=0.9)
    assert strict.recovered_inr == 0  # nothing clears a 0.9 floor
    default = run_batch(n=30, seed=42, policy_path=POLICY_PATH)
    assert default.recovered_inr > 0
