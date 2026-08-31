from datetime import datetime, timezone
from pathlib import Path

import pytest

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseState, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ComplianceEngine
from revrecover.storage.sqlite import SqliteAuditChain, SqliteCaseStore
from revrecover.workflows.flow import run_case

POLICY_PATH = Path(__file__).parent.parent / "policy" / "compliance.yaml"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def test_hashes_match_the_in_memory_chain_exactly():
    memory, disk = AuditChain(), SqliteAuditChain(":memory:")
    for chain in (memory, disk):
        chain.append(case_id="c1", stage="DETECT", payload={"amount": 1}, at=NOW)
        chain.append(case_id="c1", stage="ACT", payload={"ok": True}, at=NOW)
    assert disk.records_for_case("c1")[1].hash == memory.records_for_case("c1")[1].hash
    assert disk.verify() == (True, None)


def test_chain_survives_a_restart_and_keeps_extending(tmp_path):
    db = tmp_path / "audit.db"
    first = SqliteAuditChain(db)
    first.append(case_id="c1", stage="DETECT", payload={}, at=NOW)
    first.close()

    reopened = SqliteAuditChain(db)
    assert len(reopened) == 1
    assert reopened.verify() == (True, None)
    record = reopened.append(case_id="c1", stage="ACT", payload={}, at=NOW)
    assert record.seq == 1
    assert reopened.verify() == (True, None)


def test_tampering_in_the_database_is_detected(tmp_path):
    db = tmp_path / "audit.db"
    chain = SqliteAuditChain(db)
    chain.append(case_id="c1", stage="DECIDE", payload={"action": "retry"}, at=NOW)
    chain.append(case_id="c1", stage="ACT", payload={}, at=NOW)
    chain._conn.execute(
        "UPDATE audit SET payload = '{\"action\": \"whatsapp\"}' WHERE seq = 0"
    )
    ok, broken = chain.verify()
    assert ok is False and broken == 0


def test_flow_runs_against_the_sqlite_chain():
    case = Case(
        case_id="case_s1", case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_s1", amount_inr=2499,
        error_code="INSUFFICIENT_FUNDS", detected_at=BATCH_START,
    )
    chain = SqliteAuditChain(":memory:")
    engine = ComplianceEngine.from_yaml(POLICY_PATH)
    result = run_case(
        Scenario(case=case, persona=Persona.COOPERATIVE), engine=engine, audit=chain
    )
    assert result.case.state is CaseState.RECOVERED
    assert chain.verify() == (True, None)
    assert [r.stage for r in chain.records_for_case("case_s1")][0] == "DETECT"


def test_case_store_persists_case_snapshots(tmp_path):
    db = tmp_path / "cases.db"
    store = SqliteCaseStore(db)
    case = Case(
        case_id="case_s2", case_type=CaseType.OVERDUE_INVOICE,
        customer_id="cust_s2", amount_inr=50000,
        error_code="OVERDUE", detected_at=NOW,
    )
    case.transition(CaseState.ESCALATED, at=NOW, reason="manual review required")
    store.save(case)
    store.close()

    reopened = SqliteCaseStore(db)
    loaded = reopened.get("case_s2")
    assert loaded["state"] == "escalated"
    assert loaded["amount_inr"] == 50000
    assert reopened.count() == 1
