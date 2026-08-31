"""Thin Razorpay REST client (test mode) — Payment Links are the recovery
nudge primitive.

Resilience: transient failures (5xx, transport errors) are retried with
exponential backoff + jitter; 4xx never retries. A circuit breaker counts
consecutive request-level failures and, once open, fails fast without
touching the wire until a cooldown elapses (then one half-open probe).
reference_id doubles as the idempotency handle: Razorpay rejects duplicate
reference_ids, so a replayed action cannot issue a second link. Amounts
are INR at the domain boundary and paise on the wire.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BASE_URL = "https://api.razorpay.com"
_BACKOFF_BASE_S = 0.2


class RazorpayError(Exception):
    pass


class CircuitOpenError(RazorpayError):
    pass


@dataclass(frozen=True)
class PaymentLink:
    id: str
    short_url: str
    status: str


class RazorpayClient:
    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        breaker_threshold: int = 5,
        breaker_cooldown_s: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] | None = None,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            auth=(key_id, key_secret),
            timeout=10.0,
            transport=transport,
        )
        self._max_retries = max_retries
        self._breaker_threshold = breaker_threshold
        self._breaker_cooldown_s = breaker_cooldown_s
        self._sleep = sleeper
        self._clock = clock
        self._jitter = jitter if jitter is not None else lambda: random.uniform(0, 0.1)
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def create_payment_link(
        self, *, amount_inr: int, description: str, reference_id: str
    ) -> PaymentLink:
        data = self._request(
            "POST",
            "/v1/payment_links",
            json={
                "amount": amount_inr * 100,
                "currency": "INR",
                "description": description,
                "reference_id": reference_id,
            },
        )
        return PaymentLink(id=data["id"], short_url=data["short_url"], status=data["status"])

    def fetch_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/v1/payments/{payment_id}")

    def list_payments(self, *, from_ts: int, to_ts: int, count: int = 100) -> list[dict]:
        data = self._request(
            "GET", "/v1/payments", params={"from": from_ts, "to": to_ts, "count": count}
        )
        return data.get("items", [])

    # -- request path with retries and circuit breaker ---------------------

    def _check_breaker(self) -> None:
        if self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self._breaker_cooldown_s:
            self._opened_at = None  # half-open: allow one probe
            return
        raise CircuitOpenError("circuit open: skipping request during cooldown")

    def _record_outcome(self, *, success: bool) -> None:
        if success:
            self._consecutive_failures = 0
            self._opened_at = None
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._breaker_threshold:
            self._opened_at = self._clock()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        self._check_breaker()
        last_error: RazorpayError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)) + self._jitter())
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_error = RazorpayError(f"transport error: {exc}")
                continue
            if response.is_success:
                self._record_outcome(success=True)
                return response.json()
            detail = self._error_detail(response)
            if response.status_code < 500:
                self._record_outcome(success=False)
                raise RazorpayError(f"{response.status_code}: {detail}")
            last_error = RazorpayError(f"{response.status_code}: {detail}")
        self._record_outcome(success=False)
        raise last_error

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            return response.json()["error"]["description"]
        except Exception:
            return response.text
