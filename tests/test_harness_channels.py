from revrecover.evaluation.harness import (
    Persona,
    Response,
    generate_scenarios,
    respond,
)
from revrecover.policy.compliance import ActionKind, Channel


def test_reminder_persona_ignores_off_channel_nudges():
    response = respond(
        Persona.NEEDS_REMINDER, ActionKind.MESSAGE, attempt=2,
        channel=Channel.WHATSAPP, preferred_channel=Channel.EMAIL,
    )
    assert response is Response.NO_RESPONSE


def test_reminder_persona_pays_on_preferred_channel():
    response = respond(
        Persona.NEEDS_REMINDER, ActionKind.MESSAGE, attempt=2,
        channel=Channel.EMAIL, preferred_channel=Channel.EMAIL,
    )
    assert response is Response.PAID


def test_promise_breaker_only_engages_on_preferred_channel():
    off = respond(
        Persona.PROMISE_BREAKER, ActionKind.MESSAGE, attempt=1,
        channel=Channel.SMS, preferred_channel=Channel.WHATSAPP,
    )
    on = respond(
        Persona.PROMISE_BREAKER, ActionKind.MESSAGE, attempt=1,
        channel=Channel.WHATSAPP, preferred_channel=Channel.WHATSAPP,
    )
    assert off is Response.NO_RESPONSE
    assert on is Response.PROMISE_TO_PAY


def test_cooperative_pays_regardless_of_channel():
    response = respond(
        Persona.COOPERATIVE, ActionKind.MESSAGE, attempt=1,
        channel=Channel.SMS, preferred_channel=Channel.EMAIL,
    )
    assert response is Response.PAID


def test_voice_calls_reach_everyone():
    response = respond(
        Persona.NEEDS_REMINDER, ActionKind.VOICE_CALL, attempt=2,
        channel=Channel.VOICE, preferred_channel=Channel.EMAIL,
    )
    assert response is Response.PAID


def test_omitting_channel_means_on_preference_backward_compatible():
    assert respond(Persona.NEEDS_REMINDER, ActionKind.MESSAGE, attempt=2) is Response.PAID


def test_scenarios_carry_segment_and_preferred_channel():
    scenarios = generate_scenarios(n=200, seed=42)
    assert all(s.segment in ("consumer", "business") for s in scenarios)
    assert all(
        s.preferred_channel in (Channel.WHATSAPP, Channel.SMS, Channel.EMAIL)
        for s in scenarios
    )


def test_invoices_are_business_and_segments_shape_channel_preference():
    scenarios = generate_scenarios(n=500, seed=7)
    assert all(
        s.segment == "business"
        for s in scenarios
        if s.case.case_type.value == "overdue_invoice"
    )
    business = [s for s in scenarios if s.segment == "business"]
    consumer = [s for s in scenarios if s.segment == "consumer"]
    email_share_business = sum(
        1 for s in business if s.preferred_channel is Channel.EMAIL
    ) / len(business)
    whatsapp_share_consumer = sum(
        1 for s in consumer if s.preferred_channel is Channel.WHATSAPP
    ) / len(consumer)
    assert email_share_business > 0.5
    assert whatsapp_share_consumer > 0.4
