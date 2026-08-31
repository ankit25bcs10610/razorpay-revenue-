from datetime import UTC, datetime

from revrecover.audit.__main__ import main
from revrecover.storage.sqlite import SqliteAuditChain

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def make_db(path, tamper=False):
    chain = SqliteAuditChain(path)
    chain.append(case_id="c1", stage="DETECT", payload={"amount": 1}, at=NOW)
    chain.append(case_id="c1", stage="OUTCOME", payload={"ok": True}, at=NOW)
    if tamper:
        with chain._lock:
            chain._conn.execute("UPDATE audit SET payload = '{\"amount\": 999}' WHERE seq = 0")
            chain._conn.commit()
    chain.close()


def test_verify_intact_chain_exits_zero(tmp_path, capsys):
    db = tmp_path / "audit.db"
    make_db(db)
    assert main(["verify", str(db)]) == 0
    out = capsys.readouterr().out
    assert "intact" in out and "2 records" in out


def test_verify_tampered_chain_exits_nonzero_and_names_the_record(tmp_path, capsys):
    db = tmp_path / "audit.db"
    make_db(db, tamper=True)
    assert main(["verify", str(db)]) == 1
    assert "BROKEN at record #0" in capsys.readouterr().out


def test_ask_subcommand_answers_from_the_ledger(tmp_path, capsys):
    db = tmp_path / "audit.db"
    make_db(db)
    assert main(["ask", str(db), "what happened to case_c1?"]) == 0
    out = capsys.readouterr().out
    assert "Timeline for case_c1" in out  # no ANTHROPIC key -> deterministic summary
    assert "DETECT" in out
