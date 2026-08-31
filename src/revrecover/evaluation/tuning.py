"""Holdout threshold tuning (§3.9 protocol).

The pursue floor is chosen by net recovery on a held-out slice generated
from a *derived* seed — never from the measured batch, so the headline
number can't be tuned to its own data. Action costs are declared here,
not hidden: chasing low-odds cases costs real money.
"""

from __future__ import annotations

from dataclasses import dataclass

from revrecover.audit.chain import AuditChain
from revrecover.evaluation.harness import generate_scenarios
from revrecover.policy.compliance import ActionKind, ComplianceEngine
from revrecover.workflows.flow import run_case

HOLDOUT_SEED_OFFSET = 100_003  # prime, far from any human-picked seed
CONTACT_COST_INR = 12
RETRY_COST_INR = 4
DEFAULT_CANDIDATES = (0.2, 0.3, 0.4, 0.5)


@dataclass(frozen=True)
class TunedThresholds:
    pursue_floor: float
    holdout_net_inr: int
    holdout_n: int
    holdout_error_codes: tuple


def _net_recovery(scenarios, engine: ComplianceEngine, floor: float) -> int:
    net = 0
    for scenario in scenarios:
        result = run_case(scenario, engine=engine, audit=AuditChain(), pursue_floor=floor)
        cost = sum(
            CONTACT_COST_INR if a.kind is not ActionKind.RETRY else RETRY_COST_INR
            for a in result.actions_executed
        )
        net += result.recovered_inr - cost
    return net


def tune_pursue_floor(
    *,
    seed: int,
    engine: ComplianceEngine,
    candidates: tuple[float, ...] = DEFAULT_CANDIDATES,
    holdout_n: int = 100,
) -> TunedThresholds:
    holdout_seed = seed + HOLDOUT_SEED_OFFSET
    best_floor, best_net = None, None
    for floor in sorted(candidates):
        # regenerate per candidate: Cases are mutable and terminal after a run
        holdout = generate_scenarios(n=holdout_n, seed=holdout_seed)
        net = _net_recovery(holdout, engine, floor)
        if best_net is None or net > best_net:  # ties keep the lower floor
            best_floor, best_net = floor, net
    return TunedThresholds(
        pursue_floor=best_floor,
        holdout_net_inr=best_net,
        holdout_n=holdout_n,
        holdout_error_codes=tuple(
            s.case.error_code for s in generate_scenarios(n=holdout_n, seed=holdout_seed)
        ),
    )
