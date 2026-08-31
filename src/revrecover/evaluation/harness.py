"""Evaluation harness: seeded scenario generator + customer persona simulator.

The harness is built before the agent and frozen for the measured batch run.
Personas are deterministic rule tables in v1 (same inputs, same response),
which makes every batch byte-for-byte reproducible from its seed. Hard
failure codes always map to NEVER_PAYER: money behind a blocked card does
not come back, and an honest simulator must not pretend otherwise.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from revrecover.domain.models import Case, CaseType
from revrecover.policy.compliance import ActionKind, Channel

BATCH_START = datetime(2026, 8, 31, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


class Persona(str, Enum):
    SELF_CURE = "self_cure"              # pays anyway — contacting them is pure annoyance cost
    COOPERATIVE = "cooperative"          # pays on first touch
    NEEDS_REMINDER = "needs_reminder"    # pays on the second nudge
    SALARY_CYCLE = "salary_cycle"        # NSF until payday; retry succeeds from attempt 2
    PROMISE_BREAKER = "promise_breaker"  # promises, breaks it once, pays on follow-up
    DISPUTER = "disputer"                # opts out on first contact
    NEVER_PAYER = "never_payer"          # money is gone


class Response(str, Enum):
    PAID = "paid"
    PROMISE_TO_PAY = "promise_to_pay"
    NO_RESPONSE = "no_response"
    OPT_OUT = "opt_out"


@dataclass(frozen=True)
class Scenario:
    case: Case
    persona: Persona
    segment: str = "consumer"  # "consumer" | "business"
    preferred_channel: Channel | None = None  # None -> treat any channel as preferred


# Channel-preference mix per segment. Nudge-sensitive personas only engage
# on their preferred channel, so which channel the agent picks carries real
# money consequences — this is what the learning layer has to discover.
_CHANNEL_PREFS: dict[str, tuple[list[Channel], list[int]]] = {
    "business": ([Channel.EMAIL, Channel.SMS, Channel.WHATSAPP], [70, 15, 15]),
    "consumer": ([Channel.WHATSAPP, Channel.SMS, Channel.EMAIL], [60, 25, 15]),
}


_HARD_CODES = ("CARD_BLOCKED", "ACCOUNT_CLOSED", "FRAUD_SUSPECTED")

_ERROR_CODE_WEIGHTS = {
    "INSUFFICIENT_FUNDS": 45,
    "ISSUER_UNAVAILABLE": 15,
    "GATEWAY_TIMEOUT": 10,
    "CARD_EXPIRED": 10,
    "CARD_BLOCKED": 8,
    "ACCOUNT_CLOSED": 6,
    "FRAUD_SUSPECTED": 6,
}

_SOFT_PERSONA_WEIGHTS = {
    Persona.SELF_CURE: 10,
    Persona.COOPERATIVE: 25,
    Persona.NEEDS_REMINDER: 20,
    Persona.SALARY_CYCLE: 15,
    Persona.PROMISE_BREAKER: 15,
    Persona.DISPUTER: 5,
    Persona.NEVER_PAYER: 10,
}

_CASE_TYPE_WEIGHTS = {
    CaseType.SUBSCRIPTION_FAILURE: 40,
    CaseType.PAYMENT_FAILURE: 25,
    CaseType.OVERDUE_INVOICE: 20,
    CaseType.CHECKOUT_ABANDONED: 15,
}


def generate_scenarios(*, n: int, seed: int) -> list[Scenario]:
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    for i in range(n):
        case_type = rng.choices(
            list(_CASE_TYPE_WEIGHTS), weights=list(_CASE_TYPE_WEIGHTS.values())
        )[0]
        if case_type is CaseType.OVERDUE_INVOICE:
            error_code = "OVERDUE"
        elif case_type is CaseType.CHECKOUT_ABANDONED:
            error_code = "SESSION_EXPIRED"
        else:
            error_code = rng.choices(
                list(_ERROR_CODE_WEIGHTS), weights=list(_ERROR_CODE_WEIGHTS.values())
            )[0]

        if error_code in _HARD_CODES:
            persona = Persona.NEVER_PAYER
        else:
            persona = rng.choices(
                list(_SOFT_PERSONA_WEIGHTS), weights=list(_SOFT_PERSONA_WEIGHTS.values())
            )[0]

        # Skewed toward small tickets, with a tail crossing the HITL threshold.
        amount_inr = int(rng.lognormvariate(7.8, 1.1)) + 199

        case = Case(
            case_id=f"case_{i:04d}",
            case_type=case_type,
            customer_id=f"cust_{i:04d}",
            amount_inr=amount_inr,
            error_code=error_code,
            detected_at=BATCH_START,
        )

        if case_type is CaseType.OVERDUE_INVOICE:
            segment = "business"
        else:
            segment = "business" if rng.random() < 0.25 else "consumer"
        channels, weights = _CHANNEL_PREFS[segment]
        preferred = rng.choices(channels, weights=weights)[0]

        scenarios.append(
            Scenario(case=case, persona=persona, segment=segment, preferred_channel=preferred)
        )
    return scenarios


def respond(
    persona: Persona,
    action: ActionKind | None,
    *,
    attempt: int,
    channel: Channel | None = None,
    preferred_channel: Channel | None = None,
) -> Response:
    is_contact = action in (ActionKind.MESSAGE, ActionKind.VOICE_CALL)
    # A nudge only lands on the customer's preferred channel; voice calls
    # reach everyone. Omitted channel info means on-preference (back-compat).
    on_channel = (
        channel is None
        or preferred_channel is None
        or channel is Channel.VOICE
        or channel == preferred_channel
    )
    effective_contact = is_contact and on_channel
    match persona:
        case Persona.SELF_CURE:
            return Response.PAID
        case Persona.COOPERATIVE:
            return Response.PAID if action is not None else Response.NO_RESPONSE
        case Persona.NEEDS_REMINDER:
            return Response.PAID if effective_contact and attempt >= 2 else Response.NO_RESPONSE
        case Persona.SALARY_CYCLE:
            paid = action is ActionKind.RETRY and attempt >= 2
            return Response.PAID if paid else Response.NO_RESPONSE
        case Persona.PROMISE_BREAKER:
            if not effective_contact:
                return Response.NO_RESPONSE
            if attempt == 1:
                return Response.PROMISE_TO_PAY
            return Response.PAID if attempt >= 3 else Response.NO_RESPONSE
        case Persona.DISPUTER:
            return Response.OPT_OUT if is_contact else Response.NO_RESPONSE
        case Persona.NEVER_PAYER:
            return Response.NO_RESPONSE
