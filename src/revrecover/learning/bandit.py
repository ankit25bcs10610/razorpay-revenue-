"""Thompson-sampling contextual bandit over a fixed arm set.

Beta(1,1) prior per (context, arm); each round samples from every arm's
posterior and plays the argmax, so exploration decays naturally as evidence
accumulates. Safety rail (architecture §3.7): the bandit re-ranks choices
the policy layer already allows — it holds no reference to the compliance
engine or the action gate and structurally cannot relax either.
"""

from __future__ import annotations

import random


class ThompsonBandit:
    def __init__(self, *, arms: list[str], seed: int):
        self._arms = list(arms)
        self._rng = random.Random(seed)
        self._stats: dict[tuple[str, str], list[float]] = {}

    def _posterior(self, context: str, arm: str) -> list[float]:
        return self._stats.setdefault((context, arm), [1.0, 1.0])

    def choose(self, context: str) -> str:
        samples = {
            arm: self._rng.betavariate(*self._posterior(context, arm))
            for arm in self._arms
        }
        return max(samples, key=samples.get)

    def update(self, context: str, arm: str, *, success: bool) -> None:
        posterior = self._posterior(context, arm)
        posterior[0 if success else 1] += 1.0

    def stats(self, context: str, arm: str) -> tuple[float, float]:
        alpha, beta = self._posterior(context, arm)
        return alpha, beta
