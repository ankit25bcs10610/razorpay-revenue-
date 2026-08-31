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
from revrecover.learning.bandit import ThompsonBandit
from revrecover.policy.compliance import ActionKind, Channel, ComplianceEngine
from revrecover.workflows.flow import run_case

CONTACT_ARMS = [Channel.WHATSAPP.value, Channel.SMS.value, Channel.EMAIL.value]

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
    learning_enabled: bool
    learning_curve_pct: tuple[float, float, float, float]


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


def run_batch(
    *,
    n: int,
    seed: int,
    policy_path: Path | str = DEFAULT_POLICY,
    learning: bool = False,
) -> BatchReport:
    engine = ComplianceEngine.from_yaml(policy_path)
    scenarios = generate_scenarios(n=n, seed=seed)
    audit = AuditChain()
    bandit = ThompsonBandit(arms=CONTACT_ARMS, seed=seed) if learning else None

    results = []
    for scenario in scenarios:
        chooser = None
        if bandit is not None:
            arm = bandit.choose(scenario.segment)
            chooser = lambda case, chosen=Channel(arm): chosen
        result = run_case(scenario, engine=engine, audit=audit, channel_chooser=chooser)
        if bandit is not None and any(
            a.kind is ActionKind.MESSAGE for a in result.actions_executed
        ):
            bandit.update(scenario.segment, arm, success=result.recovered_inr > 0)
        results.append(result)

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

    quartile = max(1, n // 4)
    curve = []
    for i in range(4):
        chunk = results[i * quartile : (i + 1) * quartile if i < 3 else n]
        at_risk = sum(r.case.amount_inr for r in chunk) or 1
        curve.append(round(100 * sum(r.recovered_inr for r in chunk) / at_risk, 1))

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
        learning_enabled=learning,
        learning_curve_pct=tuple(curve),
    )


def main() -> None:
    static = run_batch(n=400, seed=2026)
    learned = run_batch(n=400, seed=2026, learning=True)
    curve = " → ".join(f"{q}%" for q in learned.learning_curve_pct)
    lines = [
        "RevRecover — measured batch run (seed=2026, n=400)",
        "=" * 56,
        f"  Revenue at risk          ₹{static.total_at_risk_inr:>12,}",
        f"  Recovered (static)       ₹{static.recovered_inr:>12,}  ({static.recovery_rate_pct}%)",
        f"  Recovered (learning)     ₹{learned.recovered_inr:>12,}  ({learned.recovery_rate_pct}%)",
        f"  Baseline: do nothing     ₹{static.baseline_do_nothing_inr:>12,}",
        f"  Baseline: naive retry    ₹{static.baseline_naive_retry_inr:>12,}",
        f"  Incremental (learning)   ₹{learned.incremental_inr:>12,}",
        "-" * 56,
        f"  Learning curve (quartile recovery): {curve}",
        f"  Cases: {learned.recovered_cases} recovered / "
        f"{learned.escalated_cases} escalated / {learned.abandoned_cases} abandoned",
        f"  Contacts sent: {learned.contacts_total} "
        f"(false-positive/annoyance: {learned.annoyance_contacts})",
        f"  Audit chain: {learned.audit_records} records, "
        f"intact={learned.audit_intact}",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
