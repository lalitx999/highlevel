import base64
import hashlib
import hmac
import pytest
from app.core.security import verify_line_signature


def test_verify_line_signature_valid():
    secret = "test_secret_key_123"
    body = b'{"events":[{"type":"message","message":{"type":"text","text":"hello"}}]}'
    
    hash_digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    valid_sig = base64.b64encode(hash_digest).decode("utf-8")

    assert verify_line_signature(body, valid_sig, channel_secret=secret) is True


def test_verify_line_signature_invalid():
    secret = "test_secret_key_123"
    body = b'{"events":[]}'
    invalid_sig = "invalid_signature_base64="

    assert verify_line_signature(body, invalid_sig, channel_secret=secret) is False


def test_verify_line_signature_missing_header():
    secret = "test_secret_key_123"
    body = b'{"events":[]}'

    assert verify_line_signature(body, None, channel_secret=secret) is False
