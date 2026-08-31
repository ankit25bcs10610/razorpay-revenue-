"""Property-based invariants over the system's core guarantees.

These don't test examples — they test laws: for *any* history the audit
chain verifies and any tamper breaks it; for *any* transition sequence the
case state machine stays sound; for *any* inputs the compliance engine
never lets a spent budget, an attempt cap, or the escalate escape hatch be
violated; for *any* customer utterances the voice call stays bounded.
"""

from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from revrecover.audit.chain import AuditChain
from revrecover.comms.drafter import lint
from revrecover.comms.voice import VoiceRecoveryAgent
from revrecover.domain.models import (
    TERMINAL_STATES,
    Case,
    CaseState,
    CaseType,
    IllegalTransition,
)
from revrecover.evaluation.harness import Persona, Response, respond
from revrecover.learning.bandit import ThompsonBandit
from revrecover.policy.compliance import (
    ActionKind,
    Channel,
    ComplianceEngine,
    ProposedAction,
)

NOW = datetime(2026, 8, 31, 14, 0, tzinfo=UTC)
ENGINE = ComplianceEngine.from_yaml("policy/compliance.yaml")

json_scalars = st.one_of(st.integers(), st.booleans(), st.text(max_size=30), st.none())
payloads = st.dictionaries(st.text(min_size=1, max_size=15), json_scalars, max_size=5)
appends = st.lists(
    st.tuples(st.sampled_from(["c1", "c2", "c3"]), st.sampled_from(["DETECT", "ACT"]), payloads),
    min_size=1,
    max_size=12,
)


@given(appends)
@settings(max_examples=60)
def test_any_append_history_yields_a_verifiable_chain(entries):
    chain = AuditChain()
    for case_id, stage, payload in entries:
        chain.append(case_id=case_id, stage=stage, payload=payload, at=NOW)
    assert chain.verify() == (True, None)


@given(appends, st.data())
@settings(max_examples=60)
def test_tampering_with_any_record_is_always_detected(entries, data):
    chain = AuditChain()
    for case_id, stage, payload in entries:
        chain.append(case_id=case_id, stage=stage, payload=payload, at=NOW)
    victim = data.draw(st.integers(min_value=0, max_value=len(entries) - 1))
    chain._records[victim].payload["__tampered__"] = True
    ok, broken = chain.verify()
    assert ok is False
    assert broken == victim


@given(st.lists(st.sampled_from(list(CaseState)), max_size=15))
@settings(max_examples=80)
def test_state_machine_never_reaches_an_inconsistent_state(targets):
    case = Case(
        case_id="c", case_type=CaseType.PAYMENT_FAILURE, customer_id="x",
        amount_inr=100, error_code="E", detected_at=NOW,
    )
    for target in targets:
        was_terminal = case.state in TERMINAL_STATES
        try:
            case.transition(target, at=NOW, reason="r")
        except IllegalTransition:
            continue
        assert not was_terminal, "terminal states must be absorbing"
    # history is a connected path ending at the current state
    previous = CaseState.DETECTED
    for event in case.history:
        assert event.from_state is previous
        previous = event.to_state
    assert previous is case.state


@given(
    kind=st.sampled_from([ActionKind.RETRY, ActionKind.MESSAGE, ActionKind.VOICE_CALL]),
    amount=st.integers(min_value=1, max_value=10_000_000),
    attempts=st.integers(min_value=0, max_value=10),
    actions_today=st.integers(min_value=0, max_value=2000),
)
@settings(max_examples=100)
def test_compliance_hard_limits_are_never_crossed(kind, amount, attempts, actions_today):
    case = Case(
        case_id="c", case_type=CaseType.PAYMENT_FAILURE, customer_id="x",
        amount_inr=amount, error_code="INSUFFICIENT_FUNDS", detected_at=NOW,
    )
    case.attempts = attempts
    decision = ENGINE.check(
        ProposedAction(kind, Channel.WHATSAPP if kind is not ActionKind.RETRY else None),
        case=case, contact_history=[], now=NOW, actions_today=actions_today,
    )
    if actions_today >= ENGINE.daily_action_budget:
        assert decision.allowed is False
    if attempts >= ENGINE.max_attempts_per_case:
        assert decision.allowed is False
    if amount >= ENGINE.hitl_amount_threshold_inr:
        assert decision.requires_approval is True


@given(
    history_hours=st.lists(st.integers(min_value=0, max_value=400), max_size=8),
    kill=st.booleans(),
)
@settings(max_examples=80)
def test_escalation_is_allowed_unless_the_kill_switch_is_on(history_hours, kill):
    case = Case(
        case_id="c", case_type=CaseType.SUBSCRIPTION_FAILURE, customer_id="x",
        amount_inr=99999, error_code="CARD_BLOCKED", detected_at=NOW,
    )
    case.attempts = 99
    history = [NOW - timedelta(hours=h) for h in history_hours]
    decision = ENGINE.check(
        ProposedAction(ActionKind.ESCALATE), case=case,
        contact_history=history, now=NOW, kill_switch=kill, actions_today=10_000,
    )
    assert decision.allowed is (not kill)


@given(
    persona=st.sampled_from(list(Persona)),
    kind=st.sampled_from([ActionKind.RETRY, ActionKind.MESSAGE, ActionKind.VOICE_CALL]),
    attempt=st.integers(min_value=1, max_value=5),
    channel=st.sampled_from(list(Channel)),
    preferred=st.sampled_from(list(Channel)),
)
@settings(max_examples=100)
def test_personas_always_answer_with_a_valid_response(persona, kind, attempt, channel, preferred):
    response = respond(persona, kind, attempt=attempt, channel=channel, preferred_channel=preferred)
    assert isinstance(response, Response)
    if response is Response.OPT_OUT:
        assert kind in (ActionKind.MESSAGE, ActionKind.VOICE_CALL)


@given(st.lists(st.text(max_size=40), min_size=1, max_size=30), st.integers(2, 8))
@settings(max_examples=60)
def test_voice_calls_are_bounded_for_any_customer_utterances(replies, max_turns):
    agent = VoiceRecoveryAgent(None, max_turns=max_turns)
    case = Case(
        case_id="c", case_type=CaseType.OVERDUE_INVOICE, customer_id="x",
        amount_inr=5000, error_code="OVERDUE", detected_at=NOW,
    )
    outcome = agent.call(case, lambda line, turn: replies[turn % len(replies)])
    agent_turns = [t for t in outcome.transcript if t.speaker == "agent"]
    assert len(agent_turns) <= max_turns + 1  # +1 = the opt-out closing apology
    if outcome.result == "opt_out":
        assert outcome.transcript[-1].speaker == "agent"


@given(st.integers(min_value=1, max_value=10**9))
@settings(max_examples=60)
def test_templates_lint_clean_for_any_amount(amount):
    from revrecover.comms.drafter import MessageDrafter

    case = Case(
        case_id="c", case_type=CaseType.SUBSCRIPTION_FAILURE, customer_id="x",
        amount_inr=amount, error_code="INSUFFICIENT_FUNDS", detected_at=NOW,
    )
    draft = MessageDrafter(None).draft(case, playbook="dunning", channel=Channel.WHATSAPP)
    assert lint(draft.text) == []


@given(st.lists(st.tuples(st.sampled_from(["a", "b"]), st.booleans()), max_size=60))
@settings(max_examples=60)
def test_bandit_always_picks_a_real_arm_and_counts_exactly(updates):
    bandit = ThompsonBandit(arms=["a", "b"], seed=7)
    for arm, success in updates:
        assert bandit.choose("ctx") in ("a", "b")
        bandit.update("ctx", arm, success=success)
    total = sum(1 for _ in updates)
    alpha_a, beta_a = bandit.stats("ctx", "a")
    alpha_b, beta_b = bandit.stats("ctx", "b")
    assert (alpha_a + beta_a + alpha_b + beta_b) - 4.0 == total  # Beta(1,1) priors
