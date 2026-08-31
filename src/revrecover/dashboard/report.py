"""Static, self-contained HTML dashboard: batch KPIs, the learning curve,
and every case's audit chain as a timeline card.

No build step, no external resources — judges open one file. Colors come
from the validated reference palette (single categorical slot for the one
chart; status colors always paired with icon + label, never color alone).
All dynamic content is HTML-escaped.
"""

from __future__ import annotations

import html
import os
from typing import Any

from revrecover.evaluation.batch import BatchReport, BatchRun

# ROI tile assumptions — tunable, documented in docs/PRIORS.md
ROI_MONTHLY_GMV_INR = int(os.environ.get("ROI_MONTHLY_GMV_INR", 10_000_000))
ROI_FAILURE_RATE = float(os.environ.get("ROI_FAILURE_RATE", 0.10))

_STATUS = {
    "recovered": ("✓", "good"),
    "partially_recovered": ("✓", "good"),
    "escalated": ("⚠", "warning"),
    "abandoned": ("✕", "serious"),
}

_CSS = """
:root { color-scheme: light;
  --surface: #fcfcfb; --card: #ffffff; --ink: #0b0b0b; --ink-2: #52514e;
  --line: #e4e3df; --series-1: #2a78d6;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b; }
@media (prefers-color-scheme: dark) { :root {
  color-scheme: dark;
  --surface: #1a1a19; --card: #232322; --ink: #ffffff; --ink-2: #c3c2b7;
  --line: #3a3936; --series-1: #3987e5; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: var(--surface); color: var(--ink);
  font: 14px/1.5 system-ui, -apple-system, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin-bottom: 20px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px;
  border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid var(--line); }
.badge .dot { width: 8px; height: 8px; border-radius: 50%; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-bottom: 24px; }
.tile { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px; }
.tile .label { color: var(--ink-2); font-size: 12px; }
.tile .value { font-size: 22px; font-weight: 700; margin-top: 2px; }
.tile .note { color: var(--ink-2); font-size: 12px; margin-top: 2px; }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px; margin-bottom: 24px; }
.panel h2 { font-size: 14px; margin: 0 0 12px; }
.bar:hover { opacity: 0.8; }
table.q { border-collapse: collapse; margin-top: 8px; font-size: 12px; color: var(--ink-2); }
table.q td, table.q th { border: 1px solid var(--line); padding: 2px 10px; text-align: right; }
.chips { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 24px; }
.chip { display: inline-flex; align-items: center; gap: 6px; background: var(--card);
  border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; font-size: 13px; }
details { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 14px; margin-bottom: 8px; }
summary { cursor: pointer; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
summary .amount { margin-left: auto; font-weight: 600; }
ol.timeline { list-style: none; margin: 10px 0 4px; padding: 0 0 0 14px;
  border-left: 2px solid var(--line); }
ol.timeline li { margin: 8px 0; }
.stage { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
  padding: 1px 8px; border-radius: 4px; border: 1px solid var(--line); color: var(--ink-2); }
.kv { color: var(--ink-2); font-size: 12px; }
"""


def _fmt_inr(value: int) -> str:
    return f"₹{value:,}"


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _chart(curve: tuple[float, ...]) -> str:
    width, height, pad = 460, 180, 28
    plot_h = height - 2 * pad
    top = max(curve) or 1.0
    bar_w, gap = 56, 44
    bars, grid = [], []
    for frac in (0.0, 0.5, 1.0):
        y = height - pad - frac * plot_h
        grid.append(
            f'<line x1="{pad}" y1="{y:.0f}" x2="{width - pad}" y2="{y:.0f}" '
            f'stroke="var(--line)" stroke-width="1"/>'
        )
    for i, pct in enumerate(curve):
        x = pad + 30 + i * (bar_w + gap)
        bar_h = max(4, plot_h * pct / top)
        y = height - pad - bar_h
        r = 4  # rounded data-end, square base anchored to the baseline
        bars.append(
            f'<g class="bar"><title>Q{i + 1}: {pct}% recovered</title>'
            f'<path d="M{x},{height - pad} v-{bar_h - r:.1f} q0,-{r} {r},-{r} '
            f'h{bar_w - 2 * r} q{r},0 {r},{r} v{bar_h - r:.1f} z" fill="var(--series-1)"/>'
            f'<text x="{x + bar_w / 2}" y="{y - 6:.0f}" text-anchor="middle" '
            f'fill="var(--ink)" font-size="12" font-weight="600">{pct}%</text>'
            f'<text x="{x + bar_w / 2}" y="{height - pad + 16}" text-anchor="middle" '
            f'fill="var(--ink-2)" font-size="12">Q{i + 1}</text></g>'
        )
    rows = "".join(f"<td>{pct}%</td>" for pct in curve)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" role="img" '
        f'aria-label="Recovery rate by batch quartile">{"".join(grid)}{"".join(bars)}</svg>'
        f'<table class="q"><tr><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th></tr>'
        f"<tr>{rows}</tr></table>"
    )


def _outcome_chip(state: str) -> str:
    icon, role = _STATUS.get(state, ("•", "warning"))
    label = state.replace("_", " ")
    return (
        f'<span class="badge"><span class="dot" style="background:var(--{role})"></span>'
        f"{icon} {_esc(label)}</span>"
    )


def _case_card(result, audit) -> str:
    case = result.case
    records = audit.records_for_case(case.case_id)
    items = []
    for record in records:
        pairs = " · ".join(f"{_esc(k)}: {_esc(v)}" for k, v in record.payload.items())
        items.append(
            f'<li><span class="stage">{_esc(record.stage)}</span> '
            f'<span class="kv">{pairs}</span></li>'
        )
    return (
        f"<details><summary><strong>{_esc(case.case_id)}</strong> "
        f'<span class="kv">{_esc(case.case_type.value)} · {_esc(case.error_code)}</span> '
        f"{_outcome_chip(case.state.value)}"
        f'<span class="amount">{_fmt_inr(case.amount_inr)}</span></summary>'
        f'<ol class="timeline">{"".join(items)}</ol></details>'
    )


def render_dashboard(
    *, static_report: BatchReport, run: BatchRun, max_cases: int = 48
) -> str:
    report = run.report
    intact, broken_at = run.audit.verify()
    if intact:
        audit_badge = (
            '<span class="badge"><span class="dot" style="background:var(--good)"></span>'
            f"✓ chain intact · {report.audit_records} records</span>"
        )
    else:
        audit_badge = (
            '<span class="badge"><span class="dot" style="background:var(--critical)"></span>'
            f"✕ CHAIN BROKEN at record #{broken_at}</span>"
        )

    tiles = [
        ("Revenue at risk", _fmt_inr(report.total_at_risk_inr), f"{report.n_cases} cases"),
        (
            "Recovered (learning)",
            _fmt_inr(report.recovered_inr),
            f"{report.recovery_rate_pct}% of at-risk",
        ),
        (
            "Recovered (static)",
            _fmt_inr(static_report.recovered_inr),
            f"{static_report.recovery_rate_pct}% without learning",
        ),
        ("Incremental vs do-nothing", _fmt_inr(report.incremental_inr), "the agent's own money"),
        (
            "Contacts sent",
            str(report.contacts_total),
            f"{report.annoyance_contacts} annoyance (false-positive cost)",
        ),
        (
            "Merchant ROI estimate",
            _fmt_inr(int(ROI_MONTHLY_GMV_INR * ROI_FAILURE_RATE * report.recovery_rate_pct / 100)) + "/mo",
            f"per ₹1 Cr monthly GMV at a typical {ROI_FAILURE_RATE:.0%} failure rate",
        ),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div><div class="note">{_esc(note)}</div></div>'
        for label, value, note in tiles
    )

    chips = (
        f'<span class="chip">✓ recovered <strong>{report.recovered_cases}</strong></span>'
        f'<span class="chip">⚠ escalated <strong>{report.escalated_cases}</strong></span>'
        f'<span class="chip">✕ abandoned <strong>{report.abandoned_cases}</strong></span>'
    )

    cards = "".join(_case_card(r, run.audit) for r in run.results[:max_cases])
    cases_note = f"showing first {min(max_cases, len(run.results))} of {len(run.results)} cases"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RevRecover — batch report</title><style>{_CSS}</style></head>
<body>
<h1>RevRecover — AI Revenue Recovery</h1>
<div class="sub">Measured batch · seed-reproducible · {audit_badge}</div>
<div class="tiles">{tiles_html}</div>
<div class="panel"><h2>Recovery rate by batch quartile — learning run</h2>{_chart(report.learning_curve_pct)}</div>
<div class="chips">{chips}</div>
<div class="panel"><h2>Case timelines ({cases_note})</h2>{cards}</div>
</body></html>"""
