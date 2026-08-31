import json
from datetime import datetime, timezone

from revrecover.comms.voice import VoiceRecoveryAgent
from revrecover.domain.models import Case, CaseType

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def make_case() -> Case:
    return Case(
        case_id="case_v1",
        case_type=CaseType.OVERDUE_INVOICE,
        customer_id="cust_v1",
        amount_inr=15000,
        error_code="OVERDUE",
        detected_at=NOW,
    )


class ScriptedLLM:
    def __init__(self, line):
        self.line = line

    def complete(self, *, system, user, schema):
        return json.dumps({"say": self.line})


def test_cooperative_customer_call_ends_in_payment():
    def responder(agent_line, turn):
        return "haan haan, abhi payment kar diya, done" if turn >= 1 else "kaun bol raha hai?"

    outcome = VoiceRecoveryAgent(None).call(make_case(), responder)
    assert outcome.result == "paid"
    assert outcome.transcript[0].speaker == "agent"
    assert "Acme Store" in outcome.transcript[0].text  # identifies the merchant
    speakers = [t.speaker for t in outcome.transcript]
    assert speakers == ["agent", "customer"] * (len(speakers) // 2)


def test_opt_out_is_honored_immediately():
    def responder(agent_line, turn):
        return "mujhe call mat karo, stop"

    outcome = VoiceRecoveryAgent(None).call(make_case(), responder)
    assert outcome.result == "opt_out"
    # one exchange, then a single closing line — never another ask
    assert len(outcome.transcript) == 3
    assert outcome.transcript[-1].speaker == "agent"


def test_promise_to_pay_is_detected():
    def responder(agent_line, turn):
        return "abhi nahi ho payega, kal pakka kar dunga"

    outcome = VoiceRecoveryAgent(None).call(make_case(), responder)
    assert outcome.result == "promise_to_pay"


def test_unresponsive_call_is_capped_at_max_turns():
    def responder(agent_line, turn):
        return "hmm"

    outcome = VoiceRecoveryAgent(None, max_turns=4).call(make_case(), responder)
    assert outcome.result == "no_resolution"
    agent_turns = [t for t in outcome.transcript if t.speaker == "agent"]
    assert len(agent_turns) == 4  # the LLM/script can never extend past the cap


def test_threatening_llm_line_is_replaced_by_script():
    llm = ScriptedLLM("Pay now or we will take legal action and call the police!")
    outcome = VoiceRecoveryAgent(llm, max_turns=2).call(make_case(), lambda l, t: "hmm")
    for turn in outcome.transcript:
        if turn.speaker == "agent":
            assert "legal action" not in turn.text.lower()
            assert "police" not in turn.text.lower()
