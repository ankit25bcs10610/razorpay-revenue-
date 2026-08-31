"""SQLite-backed persistence: the audit chain and case snapshots survive a
restart.

SqliteAuditChain is hash-format-compatible with the in-memory AuditChain
(same digest over the same canonical body), duck-type-compatible with the
flow, and re-verifiable after reopen — tampering with a row breaks the
chain at that exact seq. Stdlib sqlite3; Postgres swaps in behind the
same interface.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from revrecover.audit.chain import GENESIS_HASH, AuditRecord, _body_digest


class SqliteAuditChain:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY,
                case_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                payload TEXT NOT NULL,
                at TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def _row_to_record(self, row: tuple) -> AuditRecord:
        seq, case_id, stage, payload, at, prev_hash, digest = row
        return AuditRecord(
            seq=seq,
            case_id=case_id,
            stage=stage,
            payload=json.loads(payload),
            at=datetime.fromisoformat(at),
            prev_hash=prev_hash,
            hash=digest,
        )

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash FROM audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS_HASH

    def append(
        self, *, case_id: str, stage: str, payload: dict[str, Any], at: datetime
    ) -> AuditRecord:
        record = AuditRecord(
            seq=len(self),
            case_id=case_id,
            stage=stage,
            payload=payload,
            at=at,
            prev_hash=self._last_hash(),
        )
        record.hash = _body_digest(record)
        self._conn.execute(
            "INSERT INTO audit VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.seq,
                record.case_id,
                record.stage,
                json.dumps(record.payload, sort_keys=True, default=str),
                record.at.isoformat(),
                record.prev_hash,
                record.hash,
            ),
        )
        self._conn.commit()
        return record

    def verify(self) -> tuple[bool, int | None]:
        prev_hash = GENESIS_HASH
        for position, row in enumerate(
            self._conn.execute("SELECT * FROM audit ORDER BY seq")
        ):
            record = self._row_to_record(row)
            if (
                record.seq != position
                or record.prev_hash != prev_hash
                or record.hash != _body_digest(record)
            ):
                return False, position
            prev_hash = record.hash
        return True, None

    def records_for_case(self, case_id: str) -> list[AuditRecord]:
        rows = self._conn.execute(
            "SELECT * FROM audit WHERE case_id = ? ORDER BY seq", (case_id,)
        )
        return [self._row_to_record(row) for row in rows]

    def __len__(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]

    def close(self) -> None:
        self._conn.close()


class SqliteCaseStore:
    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                case_type TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                amount_inr INTEGER NOT NULL,
                error_code TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                detected_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def save(self, case) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case.case_id,
                case.case_type.value,
                case.customer_id,
                case.amount_inr,
                case.error_code,
                case.state.value,
                case.attempts,
                case.detected_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get(self, case_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        keys = (
            "case_id", "case_type", "customer_id", "amount_inr",
            "error_code", "state", "attempts", "detected_at",
        )
        return dict(zip(keys, row))

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
