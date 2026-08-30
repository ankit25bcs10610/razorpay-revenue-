import hashlib
import hmac

from revrecover.gateway.signature import verify_signature

SECRET = "whsec_test_123"
BODY = b'{"event": "payment.failed", "payload": {}}'


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    assert verify_signature(BODY, sign(BODY, SECRET), SECRET) is True


def test_tampered_body_fails():
    signature = sign(BODY, SECRET)
    assert verify_signature(BODY + b" ", signature, SECRET) is False


def test_wrong_secret_fails():
    assert verify_signature(BODY, sign(BODY, "other_secret"), SECRET) is False


def test_empty_or_garbage_signature_fails():
    assert verify_signature(BODY, "", SECRET) is False
    assert verify_signature(BODY, "not-hex-at-all", SECRET) is False
