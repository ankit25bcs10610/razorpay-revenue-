"""Ask the Ledger: natural-language Q&A over the hash-chained audit trail.

Read-only by construction — the analyst can quote the ledger, never write
it. The LLM answers strictly from the named case's records and must cite
record sequence numbers that actually exist; a hallucinated citation, a
schema violation, or an API failure all degrade to a deterministic
timeline summary. The audit trail stays the source of truth either way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from revrecover.diagnosis.diagnostician import LLMClient

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "cited_records": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "cited_records"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You answer questions about one recovery case using ONLY the audit "
    "records provided (each has a seq number). Cite the seq numbers you "
    "relied on in cited_records. If the records don't answer the question, "
    "say so. Return JSON: {\"answer\": ..., \"cited_records\": [...]}."
)

_CASE_ID = re.compile(r"case_[A-Za-z0-9_]+")


@dataclass(frozen=True)
class Answer:
    text: str
    source: str  # "llm" | "fallback"
    cited_records: tuple[int, ...] = ()


class LedgerAnalyst:
    def __init__(self, *, audit: Any, llm: LLMClient | None):
        self._audit = audit
        self._llm = llm

    def ask(self, question: str, *, case_id: str | None = None) -> Answer:
        if case_id is None:
            match = _CASE_ID.search(question)
            case_id = match.group(0) if match else None
        records = self._audit.records_for_case(case_id) if case_id else []
        if not records:
            return Answer(
                text=f"No records found for {case_id or 'any case named in the question'}.",
                source="fallback",
            )

        if self._llm is not None:
            try:
                raw = self._llm.complete(
                    system=_SYSTEM_PROMPT,
                    user=json.dumps(
                        {
                            "question": question,
                            "case_id": case_id,
                            "records": [
                                {"seq": r.seq, "stage": r.stage, "at": r.at.isoformat(),
                                 "payload": r.payload}
                                for r in records
                            ],
                        },
                        default=str,
                    ),
                    schema=_ANSWER_SCHEMA,
                )
                data = json.loads(raw)
                cited = tuple(int(seq) for seq in data["cited_records"])
                known = {r.seq for r in records}
                if not str(data["answer"]).strip() or any(seq not in known for seq in cited):
                    raise ValueError("invalid answer or hallucinated citation")
                return Answer(text=data["answer"], source="llm", cited_records=cited)
            except Exception:
                pass

        return Answer(text=self._summary(case_id, records), source="fallback")

    @staticmethod
    def _summary(case_id: str, records: list) -> str:
        lines = [f"Timeline for {case_id} ({len(records)} records):"]
        for record in records:
            highlights = ", ".join(f"{k}={v}" for k, v in record.payload.items())
            lines.append(f"  #{record.seq} {record.stage}: {highlights}")
        outcome = next((r for r in reversed(records) if r.stage == "OUTCOME"), None)
        if outcome is not None:
            state = outcome.payload.get("state", "unknown")
            reason = outcome.payload.get("reason", "")
            lines.append(f"Final: {state}" + (f" — {reason}" if reason else ""))
        return "\n".join(lines)
