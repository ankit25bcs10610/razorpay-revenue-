from datetime import UTC, datetime
from pathlib import Path

import pytest

from revrecover.dashboard.report import render_dashboard
from revrecover.evaluation.batch import run_batch, run_batch_full

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def rendered() -> str:
    static = run_batch(n=60, seed=42, policy_path=POLICY_PATH)
    learning = run_batch_full(n=60, seed=42, policy_path=POLICY_PATH, learning=True)
    return render_dashboard(static_report=static, run=learning, max_cases=10)


def test_kpis_are_shown(rendered):
    assert "Revenue at risk" in rendered
    assert "Recovered (learning)" in rendered
    assert "Incremental" in rendered


def test_learning_curve_quartiles_are_charted(rendered):
    learning = run_batch(n=60, seed=42, policy_path=POLICY_PATH, learning=True)
    for quartile_pct in learning.learning_curve_pct:
        assert f"{quartile_pct}%" in rendered


def test_case_timeline_cards_show_stages_in_order(rendered):
    assert "case_0000" in rendered
    detect = rendered.index(">DETECT<")
    outcome = rendered.index(">OUTCOME<")
    assert detect < outcome


def test_audit_intact_badge_is_shown(rendered):
    assert "chain intact" in rendered


def test_tampered_audit_shows_a_critical_warning():
    static = run_batch(n=20, seed=42, policy_path=POLICY_PATH)
    run = run_batch_full(n=20, seed=42, policy_path=POLICY_PATH)
    run.audit._records[0].payload["amount_inr"] = 1
    html = render_dashboard(static_report=static, run=run, max_cases=5)
    assert "CHAIN BROKEN" in html


def test_payload_content_is_html_escaped():
    static = run_batch(n=5, seed=42, policy_path=POLICY_PATH)
    run = run_batch_full(n=5, seed=42, policy_path=POLICY_PATH)
    run.audit.append(
        case_id=run.results[0].case.case_id,
        stage="DETECT",
        payload={"note": "<script>alert(1)</script>"},
        at=NOW,
    )
    html = render_dashboard(static_report=static, run=run, max_cases=5)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_output_is_self_contained_no_external_resources(rendered):
    assert 'src="http' not in rendered
    assert 'href="http' not in rendered


def test_max_cases_cap_is_respected(rendered):
    assert rendered.count("<details") == 10
    assert "of 60 cases" in rendered


def test_roi_estimate_tile_is_shown(rendered):
    assert "per ₹1 Cr monthly GMV" in rendered
