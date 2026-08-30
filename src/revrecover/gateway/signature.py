"""Razorpay webhook signature verification.

Razorpay signs the raw request body with HMAC-SHA256 using the webhook
secret and sends the hex digest in X-Razorpay-Signature. Comparison must be
constant-time to avoid timing side channels.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
