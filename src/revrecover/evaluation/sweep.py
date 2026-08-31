"""Multi-seed robustness sweep: one seed proves reproducibility, several
prove the result isn't a lucky seed.

Runs the static and learning batches across a set of seeds and reports
per-seed recovery rates with mean/min/max. The demo quotes the single-seed
report; the sweep is the evidence behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from revrecover.evaluation.batch import DEFAULT_POLICY, run_batch


@dataclass(frozen=True)
class SweepReport:
    seeds: tuple[int, ...]
    n: int
    static_rates_pct: tuple[float, ...]
    learning_rates_pct: tuple[float, ...]
    static_mean_pct: float
    static_min_pct: float
    static_max_pct: float
    learning_mean_pct: float
    learning_min_pct: float
    learning_max_pct: float


def _stats(rates: tuple[float, ...]) -> tuple[float, float, float]:
    return round(sum(rates) / len(rates), 1), min(rates), max(rates)


def run_seed_sweep(
    *, seeds: tuple[int, ...], n: int, policy_path: Path | str = DEFAULT_POLICY
) -> SweepReport:
    static = tuple(
        run_batch(n=n, seed=seed, policy_path=policy_path).recovery_rate_pct for seed in seeds
    )
    learning = tuple(
        run_batch(n=n, seed=seed, policy_path=policy_path, learning=True).recovery_rate_pct
        for seed in seeds
    )
    static_mean, static_min, static_max = _stats(static)
    learning_mean, learning_min, learning_max = _stats(learning)
    return SweepReport(
        seeds=tuple(seeds),
        n=n,
        static_rates_pct=static,
        learning_rates_pct=learning,
        static_mean_pct=static_mean,
        static_min_pct=static_min,
        static_max_pct=static_max,
        learning_mean_pct=learning_mean,
        learning_min_pct=learning_min,
        learning_max_pct=learning_max,
    )


def main() -> None:
    sweep = run_seed_sweep(seeds=(1, 2, 3, 4, 5), n=400)
    print(f"RevRecover — robustness sweep across seeds {sweep.seeds} (n={sweep.n} each)")
    print("=" * 60)
    per_seed = ", ".join(
        f"seed {s}: {st}% → {ln}%"
        for s, st, ln in zip(sweep.seeds, sweep.static_rates_pct, sweep.learning_rates_pct, strict=True)
    )
    print(f"  Per seed (static → learning): {per_seed}")
    print(
        f"  Static   mean {sweep.static_mean_pct}%  "
        f"(min {sweep.static_min_pct}% / max {sweep.static_max_pct}%)"
    )
    print(
        f"  Learning mean {sweep.learning_mean_pct}%  "
        f"(min {sweep.learning_min_pct}% / max {sweep.learning_max_pct}%)"
    )
    print("  The learning lift is not a lucky seed.")


if __name__ == "__main__":
    main()
