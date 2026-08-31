import json
from datetime import UTC, datetime

from revrecover.diagnosis.diagnostician import Diagnostician
from revrecover.domain.models import Case, CaseType

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_case() -> Case:
    return Case(
        case_id="case_0001",
        case_type=CaseType.SUBSCRIPTION_FAILURE,
        customer_id="cust_0001",
        amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS",
        detected_at=NOW,
    )


VALID_LLM_JSON = json.dumps(
    {
        "cause": "Insufficient funds aligned with month-end salary cycle",
        "failure_class": "soft",
        "recovery_odds": 0.72,
        "confidence": 0.88,
        "recommended_playbook": "dunning",
        "human_summary": "NSF near salary date; retry after payday likely to succeed.",
    }
)


class FakeLLM:
    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str, schema: dict) -> str:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self.error:
            raise self.error
        return self.reply


def test_valid_llm_response_becomes_a_diagnosis():
    diagnosis = Diagnostician(FakeLLM(VALID_LLM_JSON)).diagnose(make_case())
    assert diagnosis.source == "llm"
    assert diagnosis.recommended_playbook == "dunning"
    assert diagnosis.recovery_odds == 0.72
    assert "salary" in diagnosis.human_summary


def test_llm_receives_only_the_evidence_pack_never_pii():
    fake = FakeLLM(VALID_LLM_JSON)
    Diagnostician(fake).diagnose(make_case())
    assert "cust_0001" not in fake.calls[0]["user"]


def test_malformed_json_falls_back_to_rules():
    diagnosis = Diagnostician(FakeLLM("not json at all")).diagnose(make_case())
    assert diagnosis.source == "fallback"
    assert diagnosis.recommended_playbook == "dunning"  # scorer prior


def test_missing_required_field_falls_back_to_rules():
    incomplete = json.dumps({"cause": "x", "failure_class": "soft"})
    diagnosis = Diagnostician(FakeLLM(incomplete)).diagnose(make_case())
    assert diagnosis.source == "fallback"


def test_unknown_playbook_from_llm_is_rejected():
    hallucinated = json.loads(VALID_LLM_JSON) | {"recommended_playbook": "call_the_ceo"}
    diagnosis = Diagnostician(FakeLLM(json.dumps(hallucinated))).diagnose(make_case())
    assert diagnosis.source == "fallback"
    assert diagnosis.recommended_playbook == "dunning"


def test_out_of_range_odds_are_rejected():
    bad = json.loads(VALID_LLM_JSON) | {"recovery_odds": 1.7}
    diagnosis = Diagnostician(FakeLLM(json.dumps(bad))).diagnose(make_case())
    assert diagnosis.source == "fallback"


def test_llm_exception_falls_back_instead_of_crashing():
    diagnosis = Diagnostician(FakeLLM(error=RuntimeError("api down"))).diagnose(make_case())
    assert diagnosis.source == "fallback"
    assert diagnosis.recommended_playbook == "dunning"


def test_low_confidence_llm_answer_defers_to_rules():
    unsure = json.loads(VALID_LLM_JSON) | {"confidence": 0.3, "recommended_playbook": "receivables"}
    diagnosis = Diagnostician(FakeLLM(json.dumps(unsure))).diagnose(make_case())
    assert diagnosis.source == "fallback"
    assert diagnosis.recommended_playbook == "dunning"


def test_no_client_at_all_means_pure_rule_diagnosis():
    diagnosis = Diagnostician(None).diagnose(make_case())
    assert diagnosis.source == "fallback"
    assert diagnosis.recommended_playbook == "dunning"
    assert diagnosis.recovery_odds == 0.68
