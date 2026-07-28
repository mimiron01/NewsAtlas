"""Application-level encryption for secrets stored at rest — currently
WorkspaceSettings.mistral_api_key/.newsdata_api_key (see docs/v1-release-roadmap.html
§5). These are stored encrypted so a DB backup, a support person running a query, or a
future read-only reporting integration can't read them in plaintext — the API layer
already never returns the raw key to a browser (see schemas/settings.py).
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CryptoError(Exception):
    """Raised when a stored secret can't be decrypted (e.g. APP_SECRET_KEY changed)."""


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if not settings.app_secret_key:
        raise CryptoError("APP_SECRET_KEY is not configured")
    # APP_SECRET_KEY is an arbitrary random string (same convention as JWT_SECRET), not
    # already a Fernet-formatted key, so it's stretched into one via a plain digest
    # rather than requiring admins to generate a separate key format.
    digest = hashlib.sha256(settings.app_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Empty string in, empty string out — this is the existing "no key configured"
    sentinel used throughout workspace_settings (see resolve_mistral_api_key et al.),
    and encrypting it would turn a meaningful empty value into a non-empty ciphertext."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(
            "Failed to decrypt a stored secret — APP_SECRET_KEY may have changed since it was saved"
        ) from exc
