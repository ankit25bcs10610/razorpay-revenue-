"""Batch runner: the number that matters is incremental ₹ recovered.

Two baselines keep the headline honest:
  - do-nothing: self-cure customers pay anyway; that money is not the agent's.
  - naive retry: retry everything 3x, contact no one.
Annoyance contacts (nudges sent to customers who would have paid anyway) are
reported as false-positive cost, not hidden.

Run directly for the demo report:  python -m revrecover.evaluation.batch
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from revrecover.audit.chain import AuditChain
from revrecover.evaluation.harness import (
    Persona,
    Response,
    generate_scenarios,
    respond,
)
from revrecover.policy.compliance import ActionKind, ComplianceEngine
from revrecover.workflows.flow import run_case

DEFAULT_POLICY = Path(__file__).parents[3] / "policy" / "compliance.yaml"


@dataclass(frozen=True)
class BatchReport:
    n_cases: int
    total_at_risk_inr: int
    recovered_inr: int
    recovered_cases: int
    escalated_cases: int
    abandoned_cases: int
    recovery_rate_pct: float
    baseline_do_nothing_inr: int
    baseline_naive_retry_inr: int
    incremental_inr: int
    contacts_total: int
    annoyance_contacts: int
    audit_intact: bool
    audit_records: int


def _baseline_do_nothing(scenarios) -> int:
    return sum(s.case.amount_inr for s in scenarios if s.persona is Persona.SELF_CURE)


def _baseline_naive_retry(scenarios) -> int:
    recovered = 0
    for s in scenarios:
        for attempt in (1, 2, 3):
            if respond(s.persona, ActionKind.RETRY, attempt=attempt) is Response.PAID:
                recovered += s.case.amount_inr
                break
    return recovered


def run_batch(*, n: int, seed: int, policy_path: Path | str = DEFAULT_POLICY) -> BatchReport:
    engine = ComplianceEngine.from_yaml(policy_path)
    scenarios = generate_scenarios(n=n, seed=seed)
    audit = AuditChain()

    results = [run_case(s, engine=engine, audit=audit) for s in scenarios]

    total_at_risk = sum(s.case.amount_inr for s in scenarios)
    recovered_inr = sum(r.recovered_inr for r in results)
    recovered_cases = sum(1 for r in results if r.recovered_inr > 0)
    escalated = sum(1 for r in results if r.case.state.value == "escalated")
    abandoned = sum(1 for r in results if r.case.state.value == "abandoned")
    annoyance = sum(
        r.contacts_made
        for r, s in zip(results, scenarios)
        if s.persona is Persona.SELF_CURE
    )
    intact, _ = audit.verify()

    return BatchReport(
        n_cases=n,
        total_at_risk_inr=total_at_risk,
        recovered_inr=recovered_inr,
        recovered_cases=recovered_cases,
        escalated_cases=escalated,
        abandoned_cases=abandoned,
        recovery_rate_pct=round(100 * recovered_inr / total_at_risk, 1),
        baseline_do_nothing_inr=_baseline_do_nothing(scenarios),
        baseline_naive_retry_inr=_baseline_naive_retry(scenarios),
        incremental_inr=recovered_inr - _baseline_do_nothing(scenarios),
        contacts_total=sum(r.contacts_made for r in results),
        annoyance_contacts=annoyance,
        audit_intact=intact,
        audit_records=len(audit),
    )


def main() -> None:
    report = run_batch(n=400, seed=2026)
    lines = [
        "RevRecover — measured batch run (seed=2026, n=400)",
        "=" * 52,
        f"  Revenue at risk        ₹{report.total_at_risk_inr:>12,}",
        f"  Recovered by agent     ₹{report.recovered_inr:>12,}  ({report.recovery_rate_pct}%)",
        f"  Baseline: do nothing   ₹{report.baseline_do_nothing_inr:>12,}",
        f"  Baseline: naive retry  ₹{report.baseline_naive_retry_inr:>12,}",
        f"  Incremental recovery   ₹{report.incremental_inr:>12,}",
        "-" * 52,
        f"  Cases: {report.recovered_cases} recovered / "
        f"{report.escalated_cases} escalated / {report.abandoned_cases} abandoned",
        f"  Contacts sent: {report.contacts_total} "
        f"(false-positive/annoyance: {report.annoyance_contacts})",
        f"  Audit chain: {report.audit_records} records, "
        f"intact={report.audit_intact}",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
