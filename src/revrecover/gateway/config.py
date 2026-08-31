"""Secret resolution: environment-first, never a fixed fallback.

A known default secret is a vulnerability (anyone can sign webhooks or
call the admin endpoint). When an env var is missing, a cryptographically
random value is generated per run and the caller prints it — the demo
stays copy-paste friendly without ever shipping a baked-in credential.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping


def resolve_secret(
    name: str, *, env: Mapping[str, str] | None = None
) -> tuple[str, bool]:
    """Return (value, generated). generated=True means it was minted now."""
    source = os.environ if env is None else env
    value = source.get(name, "")
    if value:
        return value, False
    return secrets.token_urlsafe(24), True
