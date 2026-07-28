import pytest

from app.core.crypto import CryptoError, decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_round_trips():
    ciphertext = encrypt_secret("sk-my-secret-value")
    assert ciphertext != "sk-my-secret-value"
    assert decrypt_secret(ciphertext) == "sk-my-secret-value"


def test_empty_string_round_trips_as_empty():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""


def test_decrypt_garbage_raises_crypto_error():
    with pytest.raises(CryptoError):
        decrypt_secret("not-a-real-fernet-token")


def test_encrypt_is_not_deterministic_but_decrypts_the_same(monkeypatch):
    # Fernet includes a random IV, so two encryptions of the same plaintext produce
    # different ciphertext — this is expected, not a bug, and both must still decrypt
    # back to the original value.
    a = encrypt_secret("sk-my-secret-value")
    b = encrypt_secret("sk-my-secret-value")
    assert a != b
    assert decrypt_secret(a) == decrypt_secret(b) == "sk-my-secret-value"


def test_decrypt_fails_under_a_different_app_secret_key(monkeypatch):
    ciphertext = encrypt_secret("sk-my-secret-value")

    from app.core import crypto as crypto_module
    from app.core.config import get_settings

    monkeypatch.setenv("APP_SECRET_KEY", "a-completely-different-secret-key-value")
    get_settings.cache_clear()
    crypto_module._fernet.cache_clear()
    try:
        with pytest.raises(CryptoError):
            decrypt_secret(ciphertext)
    finally:
        get_settings.cache_clear()
        crypto_module._fernet.cache_clear()
