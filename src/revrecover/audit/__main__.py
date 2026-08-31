"""Audit ledger verifier CLI.

    uv run python -m revrecover.audit verify <audit.db>

Exit code 0 if the hash chain is intact, 1 with the broken record's
sequence number otherwise — usable from CI or a compliance script.
"""

from __future__ import annotations

import sys

from revrecover.storage.sqlite import SqliteAuditChain


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "verify":
        print("usage: python -m revrecover.audit verify <audit.db>")
        return 2
    chain = SqliteAuditChain(args[1])
    try:
        intact, broken = chain.verify()
        total = len(chain)
    finally:
        chain.close()
    if intact:
        print(f"audit chain intact — {total} records")
        return 0
    print(f"audit chain BROKEN at record #{broken} (of {total})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
