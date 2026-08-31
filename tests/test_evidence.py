from datetime import UTC, datetime

from revrecover.diagnosis.evidence import build_evidence_pack
from revrecover.domain.models import Case, CaseType

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_case(error_code="INSUFFICIENT_FUNDS", case_type=CaseType.SUBSCRIPTION_FAILURE) -> Case:
    return Case(
        case_id="case_0001",
        case_type=case_type,
        customer_id="cust_0001",
        amount_inr=2499,
        error_code=error_code,
        detected_at=NOW,
    )


def test_pack_classifies_error_codes_into_taxonomy():
    assert build_evidence_pack(make_case("INSUFFICIENT_FUNDS"))["error_class"] == "customer_side"
    assert build_evidence_pack(make_case("ISSUER_UNAVAILABLE"))["error_class"] == "issuer_side"
    assert build_evidence_pack(make_case("GATEWAY_TIMEOUT"))["error_class"] == "network_side"
    assert build_evidence_pack(make_case("SOMETHING_NEW"))["error_class"] == "unknown"


def test_pack_includes_rule_engine_priors_as_grounding():
    pack = build_evidence_pack(make_case())
    assert pack["rule_prior"]["p_recover"] == 0.68
    assert pack["rule_prior"]["playbook"] == "dunning"


def test_pack_never_contains_customer_identifiers():
    pack = build_evidence_pack(make_case())
    assert "cust_0001" not in str(pack)


def test_pack_is_deterministic_for_the_same_case():
    assert build_evidence_pack(make_case()) == build_evidence_pack(make_case())


def test_pack_carries_case_facts_needed_for_reasoning():
    pack = build_evidence_pack(make_case())
    assert pack["case_type"] == "subscription_failure"
    assert pack["error_code"] == "INSUFFICIENT_FUNDS"
    assert pack["amount_inr"] == 2499
    assert pack["attempts_so_far"] == 0
