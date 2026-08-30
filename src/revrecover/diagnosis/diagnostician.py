"""LLM diagnostician: reasons over the evidence pack, never guesses.

Contract (§3.3 of the architecture): the LLM sees only the structured
evidence pack; its answer must validate against DIAGNOSIS_SCHEMA and name a
real playbook. Any failure — API error, malformed JSON, schema violation,
hallucinated playbook, out-of-range odds, low confidence — degrades
deterministically to the rule engine's prior. The flow never stalls and the
LLM can never invent an action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from revrecover.detection.scorer import score
from revrecover.diagnosis.evidence import build_evidence_pack
from revrecover.domain.models import Case

KNOWN_PLAYBOOKS = frozenset(
    {"dunning", "smart_retry", "update_method", "receivables", "checkout_recovery", "manual_review"}
)
CONFIDENCE_FLOOR = 0.6

DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "minLength": 1},
        "failure_class": {"type": "string", "enum": ["soft", "hard"]},
        "recovery_odds": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "recommended_playbook": {"type": "string", "enum": sorted(KNOWN_PLAYBOOKS)},
        "human_summary": {"type": "string", "minLength": 1},
    },
    "required": [
        "cause", "failure_class", "recovery_odds",
        "confidence", "recommended_playbook", "human_summary",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the diagnosis stage of a payments revenue-recovery agent. "
    "You receive a structured evidence pack for one failed payment, "
    "subscription charge, invoice, or checkout. Determine the most likely "
    "root cause and recommend one recovery playbook. Ground your answer in "
    "the evidence only; if the evidence is thin, say so and lower your "
    "confidence. You recommend — you never execute."
)


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, schema: dict) -> str: ...


@dataclass(frozen=True)
class Diagnosis:
    cause: str
    failure_class: str
    recovery_odds: float
    confidence: float
    recommended_playbook: str
    human_summary: str
    source: str  # "llm" | "fallback"


class Diagnostician:
    def __init__(self, client: LLMClient | None):
        self._client = client

    def diagnose(self, case: Case) -> Diagnosis:
        if self._client is None:
            return self._fallback(case)
        try:
            raw = self._client.complete(
                system=SYSTEM_PROMPT,
                user=json.dumps(build_evidence_pack(case), sort_keys=True),
                schema=DIAGNOSIS_SCHEMA,
            )
            data = json.loads(raw)
            diagnosis = self._validate(data)
        except Exception:
            return self._fallback(case)
        if diagnosis.confidence < CONFIDENCE_FLOOR:
            return self._fallback(case)
        return diagnosis

    @staticmethod
    def _validate(data: dict[str, Any]) -> Diagnosis:
        for field_name in DIAGNOSIS_SCHEMA["required"]:
            if field_name not in data:
                raise ValueError(f"missing field: {field_name}")
        if data["failure_class"] not in ("soft", "hard"):
            raise ValueError("invalid failure_class")
        if data["recommended_playbook"] not in KNOWN_PLAYBOOKS:
            raise ValueError("unknown playbook")
        for bounded in ("recovery_odds", "confidence"):
            value = data[bounded]
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{bounded} out of range")
        if not str(data["cause"]).strip() or not str(data["human_summary"]).strip():
            raise ValueError("empty narrative field")
        return Diagnosis(
            cause=data["cause"],
            failure_class=data["failure_class"],
            recovery_odds=float(data["recovery_odds"]),
            confidence=float(data["confidence"]),
            recommended_playbook=data["recommended_playbook"],
            human_summary=data["human_summary"],
            source="llm",
        )

    @staticmethod
    def _fallback(case: Case) -> Diagnosis:
        assessment = score(case)
        return Diagnosis(
            cause=f"rule-based prior for {case.error_code}",
            failure_class=assessment.failure_class.value,
            recovery_odds=assessment.p_recover,
            confidence=1.0,  # deterministic rules, not a model guess
            recommended_playbook=assessment.playbook,
            human_summary=(
                f"Rule engine: {case.error_code} on {case.case_type.value}, "
                f"p_recover={assessment.p_recover}, playbook={assessment.playbook}."
            ),
            source="fallback",
        )
