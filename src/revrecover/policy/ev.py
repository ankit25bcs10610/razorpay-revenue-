"""Expected-value intervention ranking (§3.4).

EV(playbook) = P(recover | playbook, case) × amount − action costs −
annoyance cost. Compliance filtering happens later at the Action Gate;
this layer only orders economically sensible options and refuses to
spend money on negative-EV cases. Priors are declared, not learned —
the bandit adjusts within a chosen playbook, never around this gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from revrecover.domain.models import Case, CaseType

CONTACT_COST_INR = 12
RETRY_COST_INR = 4
ANNOYANCE_COST_INR = 8  # per customer contact, on top of send cost

# playbook -> (contacts, retries); mirrors workflows.flow._PLAYBOOKS
_PLAYBOOK_SHAPE: dict[str, tuple[int, int]] = {
    "dunning": (2, 1),
    "smart_retry": (1, 2),
    "update_method": (3, 0),
    "receivables": (3, 0),
    "checkout_recovery": (2, 0),
}

# P(recover | playbook) per error code / case type — declared priors.
_CANDIDATES: dict[str, dict[str, float]] = {
    "INSUFFICIENT_FUNDS": {"dunning": 0.68, "smart_retry": 0.35, "update_method": 0.30},
    "ISSUER_UNAVAILABLE": {"smart_retry": 0.85, "dunning": 0.55},
    "GATEWAY_TIMEOUT": {"smart_retry": 0.82, "dunning": 0.50},
    "CARD_EXPIRED": {"update_method": 0.50, "dunning": 0.25},
}
_CASE_TYPE_CANDIDATES: dict[CaseType, dict[str, float]] = {
    CaseType.OVERDUE_INVOICE: {"receivables": 0.55},
    CaseType.CHECKOUT_ABANDONED: {"checkout_recovery": 0.25},
}


@dataclass(frozen=True)
class RankedIntervention:
    playbook: str
    p_recover: float
    cost_inr: int
    ev_inr: int
    chosen: bool
    rejected_reason: str | None = None


def playbook_cost_inr(playbook: str) -> int:
    contacts, retries = _PLAYBOOK_SHAPE[playbook]
    return contacts * (CONTACT_COST_INR + ANNOYANCE_COST_INR) + retries * RETRY_COST_INR


def expected_value_inr(p_recover: float, amount_inr: int, playbook: str) -> int:
    return round(p_recover * amount_inr - playbook_cost_inr(playbook))


def rank_interventions(case: Case) -> list[RankedIntervention]:
    candidates = _CASE_TYPE_CANDIDATES.get(
        case.case_type, _CANDIDATES.get(case.error_code, {})
    )
    if not candidates:
        return []

    evs = {
        playbook: expected_value_inr(p, case.amount_inr, playbook)
        for playbook, p in candidates.items()
    }
    best = max(evs, key=evs.get)
    worth_it = evs[best] > 0

    ranked = []
    for playbook, p in sorted(candidates.items(), key=lambda kv: -evs[kv[0]]):
        chosen = worth_it and playbook == best
        if chosen:
            reason = None
        elif not worth_it:
            reason = "negative expected value"
        else:
            reason = "lower EV"
        ranked.append(
            RankedIntervention(
                playbook=playbook,
                p_recover=p,
                cost_inr=playbook_cost_inr(playbook),
                ev_inr=evs[playbook],
                chosen=chosen,
                rejected_reason=reason,
            )
        )
    return ranked
