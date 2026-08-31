import json
from datetime import UTC, datetime

from revrecover.comms.drafter import MessageDrafter, lint
from revrecover.domain.models import Case, CaseType
from revrecover.policy.compliance import Channel

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_case() -> Case:
    return Case(
        case_id="case_d1",
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        customer_id="cust_d1",
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=NOW,
    )


class FakeLLM:
    def __init__(self, text=None, error=None):
        self.text, self.error = text, error

    def complete(self, *, system, user, schema):
        if self.error:
            raise self.error
        return json.dumps({"text": self.text})


# --- lint rules -----------------------------------------------------------

def test_lint_flags_threatening_language():
    violations = lint("Pay now or we will take legal action against you. Reply STOP to opt out. — Acme Store")
    assert any("threat" in v for v in violations)


def test_lint_requires_an_opt_out_line():
    violations = lint("Your payment of ₹2,499 failed. Please retry. — Acme Store")
    assert any("opt-out" in v for v in violations)


def test_lint_requires_sender_identity():
    violations = lint("Your payment failed. Reply STOP to opt out.")
    assert any("sender" in v for v in violations)


def test_lint_caps_length():
    long_text = ("Reply STOP to opt out. — Acme Store " + "x" * 500)
    assert any("length" in v for v in violations_of(long_text))


def violations_of(text):
    return lint(text)


# --- drafting -------------------------------------------------------------

def test_every_playbook_template_lints_clean():
    drafter = MessageDrafter(None)
    for playbook in ("dunning", "smart_retry", "update_method", "receivables", "checkout_recovery"):
        draft = drafter.draft(make_case(), playbook=playbook, channel=Channel.WHATSAPP)
        assert draft.source == "template"
        assert lint(draft.text) == []
        assert "2,499" in draft.text


def test_clean_llm_draft_is_used():
    text = ("Hi! Your ₹2,499 subscription payment didn't go through — you can retry "
            "here: {link}. Reply STOP to opt out. — Acme Store")
    draft = MessageDrafter(FakeLLM(text)).draft(make_case(), playbook="dunning", channel=Channel.WHATSAPP)
    assert draft.source == "llm"


def test_threatening_llm_draft_falls_back_to_template():
    text = ("Final warning: pay ₹2,499 now or face legal action. "
            "Reply STOP to opt out. — Acme Store")
    draft = MessageDrafter(FakeLLM(text)).draft(make_case(), playbook="dunning", channel=Channel.WHATSAPP)
    assert draft.source == "template"
    assert lint(draft.text) == []


def test_llm_failure_falls_back_to_template():
    draft = MessageDrafter(FakeLLM(error=RuntimeError("down"))).draft(
        make_case(), playbook="dunning", channel=Channel.WHATSAPP
    )
    assert draft.source == "template"
