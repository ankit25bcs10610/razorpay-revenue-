"""Bounded recovery flow: plan -> gated actions -> outcome, fully audited.

Stopping rules live here and in the compliance engine, never in any model:
the playbook sequence is finite, every action passes the Action Gate, and a
case always terminates in a terminal state with a reason. In production the
loop body becomes a Temporal workflow with real timers; the simulated clock
(one attempt per day, always daytime) preserves identical semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from revrecover.audit.chain import AuditChain
from revrecover.detection.scorer import score
from revrecover.diagnosis.diagnostician import Diagnostician
from revrecover.domain.models import Case, CaseState
from revrecover.evaluation.harness import Persona, Response, Scenario, respond
from revrecover.policy.compliance import (
    ActionKind,
    Channel,
    ComplianceEngine,
    ProposedAction,
)

_PLAYBOOKS: dict[str, list[ProposedAction]] = {
    "dunning": [
        ProposedAction(ActionKind.MESSAGE, Channel.WHATSAPP),
        ProposedAction(ActionKind.RETRY),
        ProposedAction(ActionKind.MESSAGE, Channel.SMS),
    ],
    "smart_retry": [
        ProposedAction(ActionKind.RETRY),
        ProposedAction(ActionKind.RETRY),
        ProposedAction(ActionKind.MESSAGE, Channel.WHATSAPP),
    ],
    "update_method": [
        ProposedAction(ActionKind.MESSAGE, Channel.WHATSAPP),
        ProposedAction(ActionKind.MESSAGE, Channel.EMAIL),
        ProposedAction(ActionKind.MESSAGE, Channel.SMS),
    ],
    "receivables": [
        ProposedAction(ActionKind.MESSAGE, Channel.EMAIL),
        ProposedAction(ActionKind.MESSAGE, Channel.EMAIL),
        ProposedAction(ActionKind.VOICE_CALL, Channel.VOICE),
    ],
    "checkout_recovery": [
        ProposedAction(ActionKind.MESSAGE, Channel.WHATSAPP),
        ProposedAction(ActionKind.MESSAGE, Channel.EMAIL),
    ],
}

_P2P_FOLLOW_UP = ProposedAction(ActionKind.MESSAGE, Channel.WHATSAPP)
_ESCALATE_VALUE_FLOOR_INR = 10_000
_CONTACT_KINDS = (ActionKind.MESSAGE, ActionKind.VOICE_CALL)


@dataclass
class CaseResult:
    case: Case
    recovered_inr: int = 0
    contacts_made: int = 0
    actions_executed: list[ProposedAction] = field(default_factory=list)


def run_case(
    scenario: Scenario,
    *,
    engine: ComplianceEngine,
    audit: AuditChain,
    kill_switch: bool = False,
    diagnostician: Diagnostician | None = None,
    channel_chooser: Callable[[Case], Channel] | None = None,
) -> CaseResult:
    case, persona = scenario.case, scenario.persona
    result = CaseResult(case=case)
    now = case.detected_at

    assessment = score(case)
    audit.append(
        case_id=case.case_id,
        stage="DETECT",
        payload={
            "error_code": case.error_code,
            "amount_inr": case.amount_inr,
            "p_recover": assessment.p_recover,
            "failure_class": assessment.failure_class.value,
            "playbook": assessment.playbook,
            "pursue": assessment.pursue,
        },
        at=now,
    )

    if not assessment.pursue:
        return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                       reason=f"not recoverable: {case.error_code}")

    playbook = assessment.playbook
    if diagnostician is not None:
        diagnosis = diagnostician.diagnose(case)
        audit.append(
            case_id=case.case_id,
            stage="DIAGNOSE",
            payload={
                "source": diagnosis.source,
                "cause": diagnosis.cause,
                "failure_class": diagnosis.failure_class,
                "recovery_odds": diagnosis.recovery_odds,
                "confidence": diagnosis.confidence,
                "recommended_playbook": diagnosis.recommended_playbook,
                "human_summary": diagnosis.human_summary,
            },
            at=now,
        )
        playbook = diagnosis.recommended_playbook

    if playbook not in _PLAYBOOKS:
        return _finish(result, audit, at=now, state=CaseState.ESCALATED,
                       reason="manual review required")

    case.transition(CaseState.DIAGNOSED, at=now, reason=playbook)
    case.transition(CaseState.PLANNED, at=now)

    contact_history: list[datetime] = []
    last_response: Response | None = None
    # The chooser (e.g. the learning bandit) picks the contact channel once
    # per case; it re-ranks among channels only — every action still passes
    # the compliance gate below.
    chosen_channel = channel_chooser(case) if channel_chooser else None

    for step, planned in enumerate(_PLAYBOOKS[playbook], start=1):
        action = _P2P_FOLLOW_UP if last_response is Response.PROMISE_TO_PAY else planned
        if chosen_channel is not None and action.kind is ActionKind.MESSAGE:
            action = ProposedAction(ActionKind.MESSAGE, chosen_channel)
        decision = engine.check(
            action, case=case, contact_history=contact_history, now=now,
            kill_switch=kill_switch,
        )
        audit.append(
            case_id=case.case_id,
            stage="DECIDE",
            payload={
                "attempt": step,
                "action": action.kind.value,
                "channel": action.channel.value if action.channel else None,
                "allowed": decision.allowed,
                "failed_checks": decision.failed_checks,
                **({"hitl_approved": True} if decision.allowed and decision.requires_approval else {}),
            },
            at=now,
        )
        if not decision.allowed:
            return _finish(result, audit, at=now, state=CaseState.ESCALATED,
                           reason=f"compliance blocked: {', '.join(decision.failed_checks)}")

        if case.state is not CaseState.INTERVENING:
            case.transition(CaseState.INTERVENING, at=now)
        case.record_attempt()
        result.actions_executed.append(action)
        if action.kind in _CONTACT_KINDS:
            result.contacts_made += 1
            contact_history.append(now)

        response = respond(
            persona,
            action.kind,
            attempt=step,
            channel=action.channel,
            preferred_channel=scenario.preferred_channel,
        )
        audit.append(
            case_id=case.case_id,
            stage="ACT",
            payload={"attempt": step, "action": action.kind.value, "response": response.value},
            at=now,
        )

        if response is Response.PAID:
            result.recovered_inr = case.amount_inr
            return _finish(result, audit, at=now, state=CaseState.RECOVERED,
                           reason="payment captured")
        if response is Response.OPT_OUT:
            return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                           reason="customer opted out")
        if response is Response.PROMISE_TO_PAY:
            audit.append(
                case_id=case.case_id,
                stage="PROMISE_TO_PAY",
                payload={"attempt": step, "follow_up_scheduled": True},
                at=now,
            )

        last_response = response
        case.transition(CaseState.WAITING, at=now)
        now += timedelta(hours=24)

    if case.amount_inr >= _ESCALATE_VALUE_FLOOR_INR:
        return _finish(result, audit, at=now, state=CaseState.ESCALATED,
                       reason="high value unresolved after max attempts")
    return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                   reason="attempts exhausted")


def _finish(
    result: CaseResult,
    audit: AuditChain,
    *,
    at: datetime,
    state: CaseState,
    reason: str,
) -> CaseResult:
    result.case.transition(state, at=at, reason=reason)
    audit.append(
        case_id=result.case.case_id,
        stage="OUTCOME",
        payload={
            "state": state.value,
            "reason": reason,
            "recovered_inr": result.recovered_inr,
            "attempts": result.case.attempts,
            "contacts_made": result.contacts_made,
        },
        at=at,
    )
    return result
