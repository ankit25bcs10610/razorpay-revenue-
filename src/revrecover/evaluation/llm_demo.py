"""Live-LLM diagnosis demo:  make demo-llm   (needs ANTHROPIC_API_KEY)

Runs a handful of seeded cases through the full flow with real Claude
diagnosis and prints each DIAGNOSE record — the model's cause, odds,
confidence, and recommendation, straight from the audit chain. Without a
key it refuses (the point of this demo is the live model; everything
else in the repo runs deterministically without one).
"""

import os
from pathlib import Path

from revrecover.audit.chain import AuditChain
from revrecover.diagnosis.anthropic_client import AnthropicDiagnosisClient
from revrecover.diagnosis.diagnostician import Diagnostician
from revrecover.evaluation.harness import generate_scenarios
from revrecover.policy.compliance import ComplianceEngine
from revrecover.workflows.flow import run_case

POLICY = Path(__file__).parents[3] / "policy" / "compliance.yaml"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("demo-llm needs ANTHROPIC_API_KEY (all other demos run without it)")

    engine = ComplianceEngine.from_yaml(POLICY)
    diagnostician = Diagnostician(AnthropicDiagnosisClient())
    audit = AuditChain()
    scenarios = [s for s in generate_scenarios(n=40, seed=7) if s.case.error_code
                 not in ("CARD_BLOCKED", "ACCOUNT_CLOSED", "FRAUD_SUSPECTED")][:6]

    print("RevRecover — live Claude diagnosis over 6 cases")
    print("=" * 60)
    for scenario in scenarios:
        result = run_case(scenario, engine=engine, audit=audit, diagnostician=diagnostician)
        diagnose = next(
            r for r in audit.records_for_case(result.case.case_id) if r.stage == "DIAGNOSE"
        )
        p = diagnose.payload
        print(f"\n  {result.case.case_id} · {result.case.error_code} · ₹{result.case.amount_inr:,}")
        print(f"    cause      : {p['cause']}")
        print(f"    odds/conf  : {p['recovery_odds']} / {p['confidence']}  (source: {p['source']})")
        print(f"    playbook   : {p['recommended_playbook']}")
        print(f"    summary    : {p['human_summary']}")
        print(f"    outcome    : {result.case.state.value} (₹{result.recovered_inr:,})")
    print("\n" + "=" * 60)
    print(f"audit chain intact: {audit.verify()[0]}")


if __name__ == "__main__":
    main()
