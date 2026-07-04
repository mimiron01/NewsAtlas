from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

# bcrypt has a hard 72-byte input limit; enforced via SignupRequest.password max_length too,
# but guarded here as well since this function must never raise on valid schema input.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


def create_access_token(subject: str, token_version: int) -> str:
    """Embeds the user's current token_version — get_current_user rejects any token
    whose "ver" claim doesn't match the user's *current* DB value, which is how
    /auth/logout revokes every outstanding token at once (see api/deps.py). A version
    counter sidesteps the precision issues a timestamp-based cutoff would have against
    JWT's whole-second "iat" granularity.
    """
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": subject, "iat": issued_at, "exp": expire, "ver": token_version}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload
