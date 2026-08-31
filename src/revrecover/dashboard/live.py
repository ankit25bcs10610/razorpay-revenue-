"""Live gateway dashboard: what the service has processed so far.

Auto-refreshing single page reusing the batch report's card renderer —
watch a webhook arrive on one side of the screen and its case card
resolve here on the other.
"""

from __future__ import annotations

from typing import Any

from revrecover.dashboard.report import _CSS, _case_card, _fmt_inr


def render_live(*, audit: Any, results: list) -> str:
    recovered_inr = sum(r.recovered_inr for r in results)
    recovered = sum(1 for r in results if r.recovered_inr > 0)
    intact, broken = audit.verify()
    badge = (
        '<span class="badge"><span class="dot" style="background:var(--good)"></span>'
        f"✓ chain intact · {len(audit)} records</span>"
        if intact
        else '<span class="badge"><span class="dot" style="background:var(--critical)"></span>'
        f"✕ CHAIN BROKEN at record #{broken}</span>"
    )
    tiles = (
        f'<div class="tile"><div class="label">Cases processed</div>'
        f'<div class="value">{len(results)} cases</div>'
        f'<div class="note">{recovered} recovered</div></div>'
        f'<div class="tile"><div class="label">Recovered</div>'
        f'<div class="value">{_fmt_inr(recovered_inr)}</div>'
        f'<div class="note">live pipeline total</div></div>'
    )
    cards = "".join(_case_card(r, audit) for r in reversed(results[-50:]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RevRecover — live</title><style>{_CSS}</style></head>
<body>
<h1>RevRecover — live pipeline</h1>
<div class="sub">auto-refreshes every 3s · {badge}</div>
<div class="tiles">{tiles}</div>
<div class="panel"><h2>Latest cases</h2>{cards or '<p class="kv">waiting for webhooks…</p>'}</div>
</body></html>"""
