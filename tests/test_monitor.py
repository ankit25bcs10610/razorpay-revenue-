import random
from datetime import datetime, timedelta, timezone

from revrecover.detection.monitor import SuccessRateMonitor

T0 = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
UPI_HDFC = ("upi", "HDFC")
CARD_ICICI = ("card", "ICICI")


def feed(monitor, cell, outcomes, start=T0):
    alerts = []
    for i, ok in enumerate(outcomes):
        alert = monitor.observe(
            cell=cell, success=ok, amount_inr=500, at=start + timedelta(minutes=i)
        )
        if alert:
            alerts.append(alert)
    return alerts


def healthy(n, seed=1):
    rng = random.Random(seed)
    return [rng.random() < 0.95 for _ in range(n)]


def test_healthy_traffic_never_alerts():
    monitor = SuccessRateMonitor()
    assert feed(monitor, UPI_HDFC, healthy(300)) == []


def test_outage_fires_a_single_latched_alert():
    monitor = SuccessRateMonitor()
    alerts = feed(monitor, UPI_HDFC, healthy(100) + [False] * 60)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.cell == UPI_HDFC
    assert alert.rate < alert.baseline
    assert alert.failed_inr_in_breach > 0


def test_recovery_then_second_outage_alerts_again():
    monitor = SuccessRateMonitor()
    stream = healthy(100) + [False] * 60 + healthy(150, seed=2) + [False] * 60
    alerts = feed(monitor, UPI_HDFC, stream)
    assert len(alerts) == 2


def test_cells_are_independent():
    monitor = SuccessRateMonitor()
    feed(monitor, UPI_HDFC, healthy(100))
    alerts_icici = feed(monitor, CARD_ICICI, healthy(100, seed=3) + [False] * 60)
    alerts_hdfc_more = feed(monitor, UPI_HDFC, healthy(50, seed=4))
    assert len(alerts_icici) == 1
    assert alerts_icici[0].cell == CARD_ICICI
    assert alerts_hdfc_more == []


def test_no_alert_during_warmup_even_if_all_failures():
    monitor = SuccessRateMonitor()
    assert feed(monitor, UPI_HDFC, [False] * 19) == []
