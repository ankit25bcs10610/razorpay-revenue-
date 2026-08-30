"""Append-only, hash-chained audit ledger.

hash_n = SHA256(prev_hash || canonical_json(record_body_n)) — editing or
deleting any historical record breaks every hash after it, so tampering is
detectable with a single linear verify pass.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

GENESIS_HASH = "0" * 64


@dataclass
class AuditRecord:
    seq: int
    case_id: str
    stage: str
    payload: dict[str, Any]
    at: datetime
    prev_hash: str
    hash: str = ""


def _body_digest(record: AuditRecord) -> str:
    body = {
        "seq": record.seq,
        "case_id": record.case_id,
        "stage": record.stage,
        "payload": record.payload,
        "at": record.at.isoformat(),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((record.prev_hash + canonical).encode()).hexdigest()


@dataclass
class AuditChain:
    _records: list[AuditRecord] = field(default_factory=list)

    def append(
        self, *, case_id: str, stage: str, payload: dict[str, Any], at: datetime
    ) -> AuditRecord:
        prev_hash = self._records[-1].hash if self._records else GENESIS_HASH
        record = AuditRecord(
            seq=len(self._records),
            case_id=case_id,
            stage=stage,
            payload=payload,
            at=at,
            prev_hash=prev_hash,
        )
        record.hash = _body_digest(record)
        self._records.append(record)
        return record

    def verify(self) -> tuple[bool, int | None]:
        prev_hash = GENESIS_HASH
        for position, record in enumerate(self._records):
            if (
                record.seq != position
                or record.prev_hash != prev_hash
                or record.hash != _body_digest(record)
            ):
                return False, position
            prev_hash = record.hash
        return True, None

    def records_for_case(self, case_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.case_id == case_id]

    def __len__(self) -> int:
        return len(self._records)
