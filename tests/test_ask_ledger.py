import json
from datetime import UTC, datetime

from revrecover.audit.ask import LedgerAnalyst
from revrecover.audit.chain import AuditChain

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_audit() -> AuditChain:
    audit = AuditChain()
    audit.append(case_id="case_a1", stage="DETECT",
                 payload={"error_code": "INSUFFICIENT_FUNDS", "amount_inr": 2499}, at=NOW)
    audit.append(case_id="case_a1", stage="DECIDE",
                 payload={"action": "message", "allowed": True}, at=NOW)
    audit.append(case_id="case_a1", stage="OUTCOME",
                 payload={"state": "abandoned", "reason": "customer opted out",
                          "recovered_inr": 0}, at=NOW)
    audit.append(case_id="case_b2", stage="DETECT",
                 payload={"error_code": "OVERDUE", "amount_inr": 50000}, at=NOW)
    return audit


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error
        self.prompts = []

    def complete(self, *, system, user, schema):
        self.prompts.append(user)
        if self.error:
            raise self.error
        return self.reply


def test_llm_answer_with_valid_citations_is_used():
    reply = json.dumps({
        "answer": "The case was abandoned because the customer opted out after one contact.",
        "cited_records": [0, 2],
    })
    analyst = LedgerAnalyst(audit=make_audit(), llm=FakeLLM(reply))
    answer = analyst.ask("why did case_a1 get abandoned?")
    assert answer.source == "llm"
    assert answer.cited_records == (0, 2)
    assert "opted out" in answer.text


def test_only_the_named_cases_records_reach_the_llm():
    fake = FakeLLM(json.dumps({"answer": "x", "cited_records": []}))
    LedgerAnalyst(audit=make_audit(), llm=fake).ask("what happened to case_a1?")
    assert "case_b2" not in fake.prompts[0]
    assert "INSUFFICIENT_FUNDS" in fake.prompts[0]


def test_hallucinated_citation_falls_back():
    reply = json.dumps({"answer": "made up", "cited_records": [99]})
    answer = LedgerAnalyst(audit=make_audit(), llm=FakeLLM(reply)).ask("case_a1?")
    assert answer.source == "fallback"


def test_llm_failure_falls_back_to_a_deterministic_summary():
    answer = LedgerAnalyst(audit=make_audit(), llm=FakeLLM(error=RuntimeError("down"))).ask(
        "why did case_a1 end?"
    )
    assert answer.source == "fallback"
    assert "abandoned" in answer.text
    assert "customer opted out" in answer.text


def test_no_llm_gives_the_summary_directly():
    answer = LedgerAnalyst(audit=make_audit(), llm=None).ask("case_a1 status")
    assert answer.source == "fallback"
    assert "DETECT" in answer.text and "OUTCOME" in answer.text


def test_unknown_case_says_so():
    answer = LedgerAnalyst(audit=make_audit(), llm=None).ask("what about case_zz9?")
    assert "no records" in answer.text.lower()
