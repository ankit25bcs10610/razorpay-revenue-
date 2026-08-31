"""Audit ledger CLI.

    uv run python -m revrecover.audit verify <audit.db>
    uv run python -m revrecover.audit ask <audit.db> "why did case_x fail?"

verify: exit 0 if the hash chain is intact, 1 with the broken record's
sequence number otherwise — usable from CI or a compliance script.
ask: natural-language answer over the named case's records (Claude when
ANTHROPIC_API_KEY is set, deterministic timeline summary otherwise).
"""

from __future__ import annotations

import os
import sys

from revrecover.storage.sqlite import SqliteAuditChain

_USAGE = (
    "usage: python -m revrecover.audit verify <audit.db>\n"
    '       python -m revrecover.audit ask <audit.db> "question about case_..."'
)


def _verify(chain: SqliteAuditChain) -> int:
    intact, broken = chain.verify()
    total = len(chain)
    if intact:
        print(f"audit chain intact — {total} records")
        return 0
    print(f"audit chain BROKEN at record #{broken} (of {total})")
    return 1


def _ask(chain: SqliteAuditChain, question: str) -> int:
    from revrecover.audit.ask import LedgerAnalyst

    llm = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from revrecover.diagnosis.anthropic_client import AnthropicDiagnosisClient

        llm = AnthropicDiagnosisClient()
    answer = LedgerAnalyst(audit=chain, llm=llm).ask(question)
    print(answer.text)
    if answer.cited_records:
        print(f"(cites records: {', '.join(str(s) for s in answer.cited_records)})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "verify":
        command, extra = _verify, ()
    elif len(args) == 3 and args[0] == "ask":
        command, extra = _ask, (args[2],)
    else:
        print(_USAGE)
        return 2
    chain = SqliteAuditChain(args[1])
    try:
        return command(chain, *extra)
    finally:
        chain.close()


if __name__ == "__main__":
    raise SystemExit(main())
