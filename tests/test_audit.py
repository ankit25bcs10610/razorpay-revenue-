from datetime import UTC, datetime

from revrecover.audit.chain import GENESIS_HASH, AuditChain

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def test_first_record_links_to_genesis_hash():
    chain = AuditChain()
    record = chain.append(case_id="case_1", stage="DETECT", payload={"amount": 100}, at=NOW)
    assert record.prev_hash == GENESIS_HASH
    assert record.seq == 0


def test_each_record_links_to_previous_hash():
    chain = AuditChain()
    first = chain.append(case_id="case_1", stage="DETECT", payload={}, at=NOW)
    second = chain.append(case_id="case_1", stage="DECIDE", payload={}, at=NOW)
    assert second.prev_hash == first.hash
    assert second.seq == 1


def test_verify_passes_on_intact_chain():
    chain = AuditChain()
    for stage in ("DETECT", "DIAGNOSE", "DECIDE", "ACT"):
        chain.append(case_id="case_1", stage=stage, payload={"stage": stage}, at=NOW)
    assert chain.verify() == (True, None)


def test_verify_detects_tampered_payload():
    chain = AuditChain()
    chain.append(case_id="case_1", stage="DECIDE", payload={"action": "retry"}, at=NOW)
    chain.append(case_id="case_1", stage="ACT", payload={"result": "ok"}, at=NOW)
    chain._records[0].payload["action"] = "whatsapp"  # tamper after the fact
    ok, broken_seq = chain.verify()
    assert ok is False
    assert broken_seq == 0


def test_verify_detects_deleted_record():
    chain = AuditChain()
    chain.append(case_id="case_1", stage="DETECT", payload={}, at=NOW)
    chain.append(case_id="case_1", stage="DECIDE", payload={}, at=NOW)
    chain.append(case_id="case_1", stage="ACT", payload={}, at=NOW)
    del chain._records[1]
    ok, broken_seq = chain.verify()
    assert ok is False
    assert broken_seq == 1


def test_records_for_case_filters_by_case_id():
    chain = AuditChain()
    chain.append(case_id="case_1", stage="DETECT", payload={}, at=NOW)
    chain.append(case_id="case_2", stage="DETECT", payload={}, at=NOW)
    chain.append(case_id="case_1", stage="ACT", payload={}, at=NOW)
    assert [r.stage for r in chain.records_for_case("case_1")] == ["DETECT", "ACT"]


def test_identical_payloads_still_produce_distinct_hashes():
    chain = AuditChain()
    first = chain.append(case_id="case_1", stage="ACT", payload={"x": 1}, at=NOW)
    second = chain.append(case_id="case_1", stage="ACT", payload={"x": 1}, at=NOW)
    assert first.hash != second.hash
