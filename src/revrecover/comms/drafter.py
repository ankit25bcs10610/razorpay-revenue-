"""Customer message drafting: the LLM personalizes, deterministic rules gate.

Every outgoing text — template or LLM — must pass lint(): no threat
language (RBI collection-conduct norms), an opt-out line, sender identity,
and a length cap. A draft that fails lint silently falls back to the
playbook template, which lints clean by construction. The LLM can make a
message warmer; it can never make one non-compliant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from revrecover.diagnosis.diagnostician import LLMClient
from revrecover.domain.models import Case
from revrecover.policy.compliance import Channel

MAX_LENGTH = 480
_THREAT_PATTERNS = (
    "legal action", "police", "court", "arrest", "blacklist",
    "consequences", "final warning", "penalty", "or else",
)
_OPT_OUT_MARKERS = ("reply stop", "opt out", "unsubscribe")

_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string", "minLength": 1}},
    "required": ["text"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You draft one short payment-recovery message for an Indian customer. "
    "Warm, respectful, no pressure tactics of any kind. It must include the "
    "amount, a way to pay ({link}), the line 'Reply STOP to opt out.' and "
    "end with '— {merchant}'. Return JSON: {\"text\": ...}."
)

_TEMPLATES: dict[str, str] = {
    "dunning": (
        "Hi! Your subscription payment of ₹{amount} didn't go through. "
        "You can complete it here: {link}. Reply STOP to opt out. — {merchant}"
    ),
    "smart_retry": (
        "Heads up: we'll retry your payment of ₹{amount} tomorrow. "
        "No action needed, or pay now: {link}. Reply STOP to opt out. — {merchant}"
    ),
    "update_method": (
        "Your saved card couldn't be charged ₹{amount}. Please update your "
        "payment method here: {link}. Reply STOP to opt out. — {merchant}"
    ),
    "receivables": (
        "Gentle reminder: invoice of ₹{amount} is due. Pay securely here: "
        "{link}. Reply STOP to opt out. — {merchant}"
    ),
    "checkout_recovery": (
        "You left ₹{amount} worth of items in your cart — complete your "
        "order here: {link}. Reply STOP to opt out. — {merchant}"
    ),
}


@dataclass(frozen=True)
class Draft:
    text: str
    source: str  # "llm" | "template"


def contains_threats(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _THREAT_PATTERNS)


def lint(text: str) -> list[str]:
    violations: list[str] = []
    lowered = text.lower()
    for pattern in _THREAT_PATTERNS:
        if pattern in lowered:
            violations.append(f"threatening language: {pattern!r}")
    if not any(marker in lowered for marker in _OPT_OUT_MARKERS):
        violations.append("missing opt-out line")
    if "—" not in text and "on behalf of" not in lowered:
        violations.append("missing sender identity")
    if len(text) > MAX_LENGTH:
        violations.append(f"length {len(text)} exceeds cap {MAX_LENGTH}")
    return violations


class MessageDrafter:
    def __init__(self, llm: LLMClient | None, *, merchant: str = "Acme Store"):
        self._llm = llm
        self._merchant = merchant

    def draft(self, case: Case, *, playbook: str, channel: Channel) -> Draft:
        template_text = _TEMPLATES[playbook].format(
            amount=f"{case.amount_inr:,}", link="{link}", merchant=self._merchant
        )
        if self._llm is not None:
            try:
                raw = self._llm.complete(
                    system=_SYSTEM_PROMPT.replace("{merchant}", self._merchant),
                    user=json.dumps(
                        {
                            "playbook": playbook,
                            "channel": channel.value,
                            "amount_inr": case.amount_inr,
                            "error_code": case.error_code,
                        }
                    ),
                    schema=_DRAFT_SCHEMA,
                )
                text = json.loads(raw)["text"]
                if not lint(text):
                    return Draft(text=text, source="llm")
            except Exception:
                pass
        return Draft(text=template_text, source="template")


# Templates are the safety net — fail loudly at import time if one regresses.
for _name, _template in _TEMPLATES.items():
    _rendered = _template.format(amount="1,000", link="https://rzp.io/x", merchant="Acme Store")
    assert lint(_rendered) == [], f"template {_name} fails lint: {lint(_rendered)}"
del _name, _template, _rendered
