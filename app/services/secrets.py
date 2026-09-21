"""Authenticated encryption for persisted integration credentials."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().integration_encryption_key
    if not key:
        raise ValueError("INTEGRATION_ENCRYPTION_KEY is required for integration credentials")
    try:
        return Fernet(key.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise ValueError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_secret(value: str) -> str:
    """Encrypt a secret for database storage."""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    """Decrypt a database credential without exposing it to callers unnecessarily."""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Integration credential cannot be decrypted with the configured key") from exc
