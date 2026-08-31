"""Aggregate degradation detector: dual-EWMA success-rate monitor per
(method × issuer) cell.

A fast EWMA tracks the current rate; a slow EWMA is the baseline. The
baseline freezes while the fast rate is breaching, so an outage cannot
drag its own reference down. An alert is latched per incident: it fires
once after `min_consecutive` breaching events and re-arms only after the
rate recovers to within half the threshold of baseline. Statistical, not
LLM — cheap, fast, explainable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class DegradationAlert:
    cell: tuple
    rate: float
    baseline: float
    at: datetime
    failed_inr_in_breach: int


@dataclass
class _CellState:
    fast: float = 1.0
    baseline: float = 1.0
    events: int = 0
    breach_streak: int = 0
    latched: bool = False
    failed_inr: int = 0


@dataclass
class SuccessRateMonitor:
    fast_alpha: float = 0.15
    baseline_alpha: float = 0.02
    warmup: int = 20
    drop_threshold: float = 0.25
    min_consecutive: int = 5
    _cells: dict[tuple, _CellState] = field(default_factory=dict)

    def observe(
        self, *, cell: tuple, success: bool, amount_inr: int, at: datetime
    ) -> DegradationAlert | None:
        state = self._cells.setdefault(cell, _CellState())
        state.events += 1
        value = 1.0 if success else 0.0
        state.fast += self.fast_alpha * (value - state.fast)

        if state.events <= self.warmup:
            state.baseline += self.baseline_alpha * (value - state.baseline)
            return None

        breaching = state.fast < state.baseline - self.drop_threshold
        if breaching:
            state.breach_streak += 1
            if not success:
                state.failed_inr += amount_inr
        else:
            state.baseline += self.baseline_alpha * (value - state.baseline)
            state.breach_streak = 0
            if state.fast >= state.baseline - self.drop_threshold / 2:
                state.latched = False
                state.failed_inr = 0

        if breaching and not state.latched and state.breach_streak >= self.min_consecutive:
            state.latched = True
            return DegradationAlert(
                cell=cell,
                rate=round(state.fast, 3),
                baseline=round(state.baseline, 3),
                at=at,
                failed_inr_in_breach=state.failed_inr,
            )
        return None
