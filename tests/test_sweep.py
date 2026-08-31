from pathlib import Path

import pytest

from revrecover.evaluation.sweep import run_seed_sweep

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"


@pytest.fixture(scope="module")
def sweep():
    return run_seed_sweep(seeds=(1, 2, 3), n=100, policy_path=POLICY_PATH)


def test_sweep_reports_per_seed_and_aggregate_rates(sweep):
    assert len(sweep.static_rates_pct) == 3
    assert len(sweep.learning_rates_pct) == 3
    assert sweep.static_min_pct <= sweep.static_mean_pct <= sweep.static_max_pct
    assert sweep.learning_min_pct <= sweep.learning_mean_pct <= sweep.learning_max_pct


def test_learning_beats_static_on_average_across_seeds(sweep):
    assert sweep.learning_mean_pct > sweep.static_mean_pct


def test_sweep_is_deterministic(sweep):
    assert run_seed_sweep(seeds=(1, 2, 3), n=100, policy_path=POLICY_PATH) == sweep
