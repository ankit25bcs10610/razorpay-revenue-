"""Generate the batch dashboard:  make dashboard  ->  dashboard.html"""

from pathlib import Path

from revrecover.dashboard.report import render_dashboard
from revrecover.evaluation.batch import run_batch, run_batch_full

out = Path("dashboard.html")
static = run_batch(n=400, seed=2026)
learning = run_batch_full(n=400, seed=2026, learning=True)
out.write_text(render_dashboard(static_report=static, run=learning), encoding="utf-8")
print(f"wrote {out.resolve()}")
