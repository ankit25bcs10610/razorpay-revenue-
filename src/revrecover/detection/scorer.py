"""Rule-based recoverability scorer (v1).

Deliberately conservative: hard failures are never pursued (chasing dead
cases is the false-positive cost the batch report measures), unknown codes
score low and route to manual review. The LightGBM model replaces the
priors here later behind the same `score()` signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from revrecover.domain.models import Case, CaseType

PURSUE_FLOOR = 0.2


class FailureClass(str, Enum):
    SOFT = "soft"
    HARD = "hard"


@dataclass(frozen=True)
class Assessment:
    p_recover: float
    failure_class: FailureClass
    playbook: str
    pursue: bool


_HARD_CODES = frozenset({"CARD_BLOCKED", "ACCOUNT_CLOSED", "FRAUD_SUSPECTED"})

# error code -> (p_recover, playbook)
_SOFT_PRIORS: dict[str, tuple[float, str]] = {
    "INSUFFICIENT_FUNDS": (0.68, "dunning"),
    "ISSUER_UNAVAILABLE": (0.85, "smart_retry"),
    "GATEWAY_TIMEOUT": (0.82, "smart_retry"),
    "CARD_EXPIRED": (0.50, "update_method"),
}

_CASE_TYPE_PLAYBOOKS: dict[CaseType, tuple[float, str]] = {
    CaseType.OVERDUE_INVOICE: (0.55, "receivables"),
    CaseType.CHECKOUT_ABANDONED: (0.25, "checkout_recovery"),
}


def score(case: Case, *, pursue_floor: float = PURSUE_FLOOR) -> Assessment:
    if case.error_code in _HARD_CODES:
        return Assessment(
            p_recover=0.0, failure_class=FailureClass.HARD, playbook="none", pursue=False
        )

    if case.case_type in _CASE_TYPE_PLAYBOOKS:
        p_recover, playbook = _CASE_TYPE_PLAYBOOKS[case.case_type]
    else:
        p_recover, playbook = _SOFT_PRIORS.get(case.error_code, (0.3, "manual_review"))

    return Assessment(
        p_recover=p_recover,
        failure_class=FailureClass.SOFT,
        playbook=playbook,
        pursue=p_recover >= pursue_floor,
    )
