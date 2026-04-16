"""Password hashing, JWT, Fernet encryption."""
from app.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    encrypt_secret, decrypt_secret,
)


def test_password_hash_and_verify():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = create_access_token({"sub": "42"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"


def test_jwt_rejects_tampered():
    token = create_access_token({"sub": "42"})
    assert decode_access_token(token + "garbage") is None


def test_fernet_roundtrip():
    plain = "SK-live-abc123"
    ct = encrypt_secret(plain)
    assert ct != plain
    assert decrypt_secret(ct) == plain


def test_fernet_rejects_tampered():
    import pytest
    ct = encrypt_secret("secret")
    with pytest.raises(Exception):
        decrypt_secret(ct[:-4] + "XXXX")
