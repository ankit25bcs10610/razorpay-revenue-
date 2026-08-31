import random

from revrecover.learning.bandit import ThompsonBandit

ARMS = ["whatsapp", "sms", "email"]


def simulate(bandit: ThompsonBandit, context: str, true_rates: dict, rounds: int, seed: int):
    rng = random.Random(seed)
    picks = []
    for _ in range(rounds):
        arm = bandit.choose(context)
        picks.append(arm)
        bandit.update(context, arm, success=rng.random() < true_rates[arm])
    return picks


def test_converges_to_the_best_arm():
    bandit = ThompsonBandit(arms=ARMS, seed=1)
    picks = simulate(
        bandit, "consumer", {"whatsapp": 0.6, "sms": 0.2, "email": 0.1}, rounds=300, seed=2
    )
    late = picks[-100:]
    assert late.count("whatsapp") / len(late) > 0.7


def test_contexts_learn_independently():
    bandit = ThompsonBandit(arms=ARMS, seed=1)
    simulate(bandit, "consumer", {"whatsapp": 0.7, "sms": 0.1, "email": 0.1}, rounds=200, seed=2)
    picks = simulate(
        bandit, "business", {"whatsapp": 0.1, "sms": 0.1, "email": 0.7}, rounds=300, seed=3
    )
    late = picks[-100:]
    assert late.count("email") / len(late) > 0.7


def test_same_seed_same_choices():
    first = ThompsonBandit(arms=ARMS, seed=42)
    second = ThompsonBandit(arms=ARMS, seed=42)
    for _ in range(50):
        arm_a, arm_b = first.choose("c"), second.choose("c")
        assert arm_a == arm_b
        first.update("c", arm_a, success=True)
        second.update("c", arm_b, success=True)


def test_stats_track_successes_and_failures():
    bandit = ThompsonBandit(arms=ARMS, seed=1)
    bandit.update("c", "sms", success=True)
    bandit.update("c", "sms", success=True)
    bandit.update("c", "sms", success=False)
    alpha, beta = bandit.stats("c", "sms")
    assert (alpha, beta) == (3.0, 2.0)  # Beta(1,1) prior + 2 wins, 1 loss
