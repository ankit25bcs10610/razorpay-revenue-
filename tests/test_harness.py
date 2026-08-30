from revrecover.evaluation.harness import (
    Persona,
    Response,
    generate_scenarios,
    respond,
)
from revrecover.policy.compliance import ActionKind


def test_same_seed_generates_identical_scenarios():
    first = generate_scenarios(n=50, seed=42)
    second = generate_scenarios(n=50, seed=42)
    assert [(s.case.case_id, s.case.error_code, s.persona) for s in first] == [
        (s.case.case_id, s.case.error_code, s.persona) for s in second
    ]


def test_different_seeds_generate_different_batches():
    first = generate_scenarios(n=50, seed=42)
    second = generate_scenarios(n=50, seed=43)
    assert [s.case.error_code for s in first] != [s.case.error_code for s in second]


def test_batch_always_contains_never_payers_so_full_recovery_is_impossible():
    scenarios = generate_scenarios(n=200, seed=42)
    assert any(s.persona is Persona.NEVER_PAYER for s in scenarios)


def test_hard_failure_codes_are_always_never_payers():
    scenarios = generate_scenarios(n=500, seed=7)
    hard = [s for s in scenarios if s.case.error_code in ("CARD_BLOCKED", "ACCOUNT_CLOSED", "FRAUD_SUSPECTED")]
    assert hard, "expected some hard-failure cases in a 500-case batch"
    assert all(s.persona is Persona.NEVER_PAYER for s in hard)


def test_cooperative_pays_on_first_contact():
    assert respond(Persona.COOPERATIVE, ActionKind.MESSAGE, attempt=1) is Response.PAID


def test_needs_reminder_ignores_first_nudge_then_pays():
    assert respond(Persona.NEEDS_REMINDER, ActionKind.MESSAGE, attempt=1) is Response.NO_RESPONSE
    assert respond(Persona.NEEDS_REMINDER, ActionKind.MESSAGE, attempt=2) is Response.PAID


def test_salary_cycle_pays_only_on_retry_after_first_attempt():
    assert respond(Persona.SALARY_CYCLE, ActionKind.RETRY, attempt=1) is Response.NO_RESPONSE
    assert respond(Persona.SALARY_CYCLE, ActionKind.MESSAGE, attempt=2) is Response.NO_RESPONSE
    assert respond(Persona.SALARY_CYCLE, ActionKind.RETRY, attempt=2) is Response.PAID


def test_promise_breaker_promises_breaks_it_then_pays_third_time():
    assert respond(Persona.PROMISE_BREAKER, ActionKind.MESSAGE, attempt=1) is Response.PROMISE_TO_PAY
    assert respond(Persona.PROMISE_BREAKER, ActionKind.MESSAGE, attempt=2) is Response.NO_RESPONSE
    assert respond(Persona.PROMISE_BREAKER, ActionKind.MESSAGE, attempt=3) is Response.PAID


def test_disputer_opts_out_on_first_contact():
    assert respond(Persona.DISPUTER, ActionKind.MESSAGE, attempt=1) is Response.OPT_OUT


def test_never_payer_never_responds():
    for kind in (ActionKind.MESSAGE, ActionKind.RETRY, ActionKind.VOICE_CALL):
        for attempt in (1, 2, 3):
            assert respond(Persona.NEVER_PAYER, kind, attempt=attempt) is Response.NO_RESPONSE


def test_self_cure_pays_even_without_intervention():
    assert respond(Persona.SELF_CURE, None, attempt=0) is Response.PAID
