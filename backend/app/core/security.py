"""Security helpers: token encryption (Fernet) and signed session cookies.

- GitHub access tokens are encrypted before they reach the database and decrypted only when a clone or
  GitHub API call needs them. TOKEN_ENCRYPTION_KEY may hold several comma-separated keys: the first
  encrypts, all of them decrypt, so a key can be rotated without logging everyone out of GitHub.
- The session cookie holds only the user id and a session version, signed and time-limited with SESSION_SECRET. It is
  not encrypted, so never put anything secret in it. The version is compared with users.session_version on every
  request (app/api/deps.py), so raising that number cuts off every cookie issued before (server-side logout).

Generate fresh secrets:  python -m app.core.security
"""
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings

MIN_SECRET_LENGTH = 32


class SecurityConfigError(RuntimeError):
    """A required secret is missing or malformed (a deployment problem, not a user error)."""


class TokenDecryptError(ValueError):
    """The stored ciphertext cannot be decrypted with the configured key(s)."""


# ---------- encrypted GitHub tokens ----------

def _fernet() -> MultiFernet:
    raw = get_settings().token_encryption_key
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SecurityConfigError("TOKEN_ENCRYPTION_KEY is not set. Generate one with: python -m app.core.security")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as e:
        raise SecurityConfigError(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes). "
            "Generate one with: python -m app.core.security") from e


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except InvalidToken as e:
        raise TokenDecryptError("Stored token cannot be decrypted (was TOKEN_ENCRYPTION_KEY changed?)") from e


def rotate_token(cipher: str) -> str:
    """Re-encrypt with the newest key (the first one in TOKEN_ENCRYPTION_KEY)."""
    try:
        return _fernet().rotate(cipher.encode()).decode()
    except InvalidToken as e:
        raise TokenDecryptError("Stored token cannot be decrypted (was TOKEN_ENCRYPTION_KEY changed?)") from e


def config_problem() -> str | None:
    """None when login secrets are usable, otherwise a short reason (used to disable the login button)."""
    for check in (_fernet, _serializer):
        try:
            check()
        except SecurityConfigError as e:
            return str(e)
    return None


# ---------- signed session cookie ----------

def _serializer() -> URLSafeTimedSerializer:
    secret = get_settings().session_secret
    if len(secret) < MIN_SECRET_LENGTH:
        raise SecurityConfigError(
            f"SESSION_SECRET must be at least {MIN_SECRET_LENGTH} characters. Generate one with: python -m app.core.security")
    return URLSafeTimedSerializer(secret, salt="session")


def create_session_token(user_id: int, version: int = 0) -> str:
    return _serializer().dumps({"uid": user_id, "ver": version})


def read_session(token: str) -> tuple[int, int] | None:
    """Return (user id, session version), or None if the token is forged, tampered with or expired.

    Cookies issued before sessions had a version carry none; they count as version 0, so the upgrade logs nobody out.
    """
    try:
        data = _serializer().loads(token, max_age=get_settings().session_ttl_seconds)
    except BadSignature:                       # includes SignatureExpired
        return None
    if not isinstance(data, dict):
        return None
    uid, version = data.get("uid"), data.get("ver", 0)
    if not isinstance(uid, int) or isinstance(version, bool) or not isinstance(version, int):
        return None
    return uid, version


def read_session_token(token: str) -> int | None:
    """Return the user id, or None if the token is forged, tampered with or expired (the version is not checked here)."""
    session = read_session(token)
    return session[0] if session else None


if __name__ == "__main__":
    print("# paste these into backend/.env")
    print(f"TOKEN_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    print(f"SESSION_SECRET={secrets.token_urlsafe(48)}")
