"""Thin Razorpay REST client (test mode) — Payment Links are the recovery
nudge primitive.

reference_id doubles as the idempotency handle: Razorpay rejects duplicate
reference_ids, so a replayed action cannot issue a second link. Amounts are
INR at the domain boundary and paise on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

BASE_URL = "https://api.razorpay.com"


class RazorpayError(Exception):
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
    ):
        self._http = httpx.Client(
            base_url=base_url,
            auth=(key_id, key_secret),
            timeout=10.0,
            transport=transport,
        )

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

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self._http.request(method, path, **kwargs)
        if response.is_success:
            return response.json()
        try:
            detail = response.json()["error"]["description"]
        except Exception:
            detail = response.text
        raise RazorpayError(f"{response.status_code}: {detail}")
