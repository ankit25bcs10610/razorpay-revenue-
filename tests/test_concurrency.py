from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from revrecover.gateway.events import EventLedger
from revrecover.policy.compliance import ActionBudget

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def test_ledger_accepts_each_event_exactly_once_under_contention():
    ledger = EventLedger()
    event_ids = [f"evt_{i}" for i in range(100)] * 8  # 8 threads race per id

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(ledger.register, event_ids))

    assert sum(outcomes) == 100  # every id accepted exactly once


def test_budget_counts_are_exact_under_contention():
    budget = ActionBudget()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: budget.record(NOW), range(400)))
    assert budget.count(NOW) == 400
