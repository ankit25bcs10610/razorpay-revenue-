"""Bounded recovery flow: plan -> gated actions -> outcome, fully audited.

Stopping rules live here and in the compliance engine, never in any model:
the playbook sequence is finite, every action passes the Action Gate, and a
case always terminates in a terminal state with a reason. In production the
loop body becomes a Temporal workflow with real timers; the simulated clock
(one attempt per day, always daytime) preserves identical semantics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from revrecover.audit.chain import AuditChain
from revrecover.detection.outages import OutageRegistry
from revrecover.detection.scorer import PURSUE_FLOOR, score
from revrecover.diagnosis.diagnostician import Diagnostician
from revrecover.domain.models import Case, CaseState
from revrecover.evaluation.harness import Response, Scenario, respond
from revrecover.memory.customer360 import Customer360
from revrecover.policy.compliance import (
    ActionBudget,
    ActionKind,
    Channel,
    ComplianceEngine,
    ProposedAction,
)
from revrecover.policy.ev import expected_value_inr, rank_interventions

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


class TransientActuatorError(Exception):
    """A side-effecting call failed transiently (gateway 5xx, issuer down).

    The flow absorbs it: audit the failure, back off, move to the next
    step. It must never crash a case or silently count as customer touch.
    """


@dataclass
class CaseResult:
    case: Case
    recovered_inr: int = 0
    contacts_made: int = 0
    actions_executed: list[ProposedAction] = field(default_factory=list)
    playbook: str = "none"


def run_case(
    scenario: Scenario,
    *,
    engine: ComplianceEngine,
    audit: AuditChain,
    kill_switch: bool = False,
    diagnostician: Diagnostician | None = None,
    channel_chooser: Callable[[Case], Channel] | None = None,
    budget: ActionBudget | None = None,
    dry_run: bool = False,
    executor: Callable[[ProposedAction, Case], None] | None = None,
    pursue_floor: float = PURSUE_FLOOR,
    customer360: Customer360 | None = None,
    outages: OutageRegistry | None = None,
) -> CaseResult:
    case, persona = scenario.case, scenario.persona
    result = CaseResult(case=case)
    now = case.detected_at

    assessment = score(case, pursue_floor=pursue_floor)
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
    if customer360 is not None and customer360.has_opted_out(case.customer_id):
        return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                       reason="customer previously opted out")

    playbook = assessment.playbook
    diagnosis = None
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

    ranked = rank_interventions(case)
    if diagnosis is not None:
        playbook = diagnosis.recommended_playbook
    elif ranked:
        chosen = next((r for r in ranked if r.chosen), None)
        playbook = chosen.playbook if chosen else playbook

    if ranked or diagnosis is not None:
        audit.append(
            case_id=case.case_id,
            stage="PLAN",
            payload={
                "considered": [
                    {
                        "playbook": r.playbook,
                        "p_recover": r.p_recover,
                        "cost_inr": r.cost_inr,
                        "ev_inr": r.ev_inr,
                        "chosen": r.playbook == playbook,
                        "rejected_reason": None if r.playbook == playbook else r.rejected_reason or "diagnosis override",
                    }
                    for r in ranked
                ],
                "diagnosis_override": diagnosis is not None
                and not any(r.chosen and r.playbook == playbook for r in ranked),
            },
            at=now,
        )

    # The EV gate: never spend money on a case whose best option loses money.
    if playbook in _PLAYBOOKS:
        odds = diagnosis.recovery_odds if diagnosis is not None else assessment.p_recover
        best_ev = expected_value_inr(odds, case.amount_inr, playbook)
        if best_ev <= 0:
            return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                           reason=f"negative expected value (best ₹{best_ev})")

    result.playbook = playbook
    if playbook not in _PLAYBOOKS:
        return _finish(result, audit, at=now, state=CaseState.ESCALATED,
                       reason="manual review required")

    case.transition(CaseState.DIAGNOSED, at=now, reason=playbook)
    case.transition(CaseState.PLANNED, at=now)

    contact_history: list[datetime] = (
        customer360.contacts_for(case.customer_id) if customer360 is not None else []
    )
    last_response: Response | None = None
    last_contact_channel: Channel | None = None
    retries_executed = 0
    actuator_failures = 0
    budget = budget if budget is not None else ActionBudget()
    # The chooser (e.g. the learning bandit) picks the contact channel once
    # per case; it re-ranks among channels only — every action still passes
    # the compliance gate below.
    chosen_channel = channel_chooser(case) if channel_chooser else None

    for step, planned in enumerate(_PLAYBOOKS[playbook], start=1):
        action = _P2P_FOLLOW_UP if last_response is Response.PROMISE_TO_PAY else planned
        if chosen_channel is not None and action.kind is ActionKind.MESSAGE:
            action = ProposedAction(ActionKind.MESSAGE, chosen_channel)
        if (
            action.kind is ActionKind.RETRY
            and outages is not None
            and case.cell is not None
            and outages.active(case.cell, at=now)
        ):
            # A retry into a down issuer is a wasted representment — defer.
            audit.append(
                case_id=case.case_id,
                stage="DEFERRED",
                payload={"attempt": step, "reason": "issuer_outage",
                         "cell": list(case.cell)},
                at=now,
            )
            now += timedelta(hours=24)
            continue
        decision = engine.check(
            action, case=case, contact_history=contact_history, now=now,
            kill_switch=kill_switch,
            actions_today=budget.count(now.astimezone(engine.tz)),
            retries_so_far=retries_executed,
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
                **({"dry_run": True} if dry_run else {}),
                **({"hitl_approved": True} if decision.allowed and decision.requires_approval else {}),
            },
            at=now,
        )
        if not decision.allowed:
            if kill_switch:
                return _finish(result, audit, at=now, state=CaseState.ESCALATED,
                               reason="compliance blocked: kill_switch")
            # A blocked step is skipped, not fatal — later steps may still
            # be compliant (e.g. a retry after the notice has aged 24h).
            now += timedelta(hours=24)
            continue
        if dry_run:
            now += timedelta(hours=24)
            continue
        if executor is not None:
            try:
                executor(action, case)
            except TransientActuatorError as exc:
                actuator_failures += 1
                audit.append(
                    case_id=case.case_id,
                    stage="ACT_FAILED",
                    payload={"attempt": step, "action": action.kind.value, "error": str(exc)},
                    at=now,
                )
                now += timedelta(hours=24)  # back off, re-plan next step
                continue

        if case.state is not CaseState.INTERVENING:
            case.transition(CaseState.INTERVENING, at=now)
        case.record_attempt()
        budget.record(now.astimezone(engine.tz))
        result.actions_executed.append(action)
        if action.kind is ActionKind.RETRY:
            retries_executed += 1
        if action.kind in _CONTACT_KINDS:
            result.contacts_made += 1
            contact_history.append(now)
            last_contact_channel = action.channel
            if customer360 is not None:
                customer360.record_contact(case.customer_id, now)

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
            if customer360 is not None:
                customer360.record_recovery(case.customer_id, last_contact_channel)
            return _finish(result, audit, at=now, state=CaseState.RECOVERED,
                           reason="payment captured")
        if response is Response.OPT_OUT:
            if customer360 is not None:
                customer360.record_opt_out(case.customer_id)
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

    if dry_run:
        return _finish(result, audit, at=now, state=CaseState.ABANDONED,
                       reason="dry run — no actions executed")
    if not result.actions_executed:
        reason = (
            "actuator failures exhausted playbook"
            if actuator_failures
            else "all actions compliance-blocked"
        )
        return _finish(result, audit, at=now, state=CaseState.ESCALATED, reason=reason)
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
