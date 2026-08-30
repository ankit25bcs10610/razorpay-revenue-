"""Evidence pack builder: the only thing the LLM diagnostician ever sees.

Structured facts plus the rule engine's prior — never raw logs, never
customer identifiers. The case_id is the correlation handle; customer
PII stays host-side.
"""

from __future__ import annotations

from typing import Any

from revrecover.detection.scorer import score
from revrecover.domain.models import Case

_ERROR_TAXONOMY: dict[str, str] = {
    "INSUFFICIENT_FUNDS": "customer_side",
    "CARD_EXPIRED": "customer_side",
    "CARD_BLOCKED": "customer_side",
    "ACCOUNT_CLOSED": "customer_side",
    "ISSUER_UNAVAILABLE": "issuer_side",
    "GATEWAY_TIMEOUT": "network_side",
    "FRAUD_SUSPECTED": "risk",
    "OVERDUE": "receivable",
    "SESSION_EXPIRED": "checkout",
}


def build_evidence_pack(case: Case) -> dict[str, Any]:
    assessment = score(case)
    return {
        "case_id": case.case_id,
        "case_type": case.case_type.value,
        "error_code": case.error_code,
        "error_class": _ERROR_TAXONOMY.get(case.error_code, "unknown"),
        "amount_inr": case.amount_inr,
        "attempts_so_far": case.attempts,
        "rule_prior": {
            "p_recover": assessment.p_recover,
            "failure_class": assessment.failure_class.value,
            "playbook": assessment.playbook,
        },
    }
