"""Encrypt and decrypt sensitive values stored at rest.

Uses Fernet (symmetric) with GITHUB_TOKEN_FERNET_KEY from the environment.
Views must never touch ciphertext format details; call encrypt_secret /
decrypt_secret (or model helpers) from server-side services only.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

# Fernet tokens are url-safe base64 and always start with this prefix.
_FERNET_PREFIX = "gAAAAA"


class TokenEncryptionError(Exception):
    """Raised when a token cannot be encrypted or decrypted."""


def fernet_key_configured() -> bool:
    return bool((getattr(settings, "GITHUB_TOKEN_FERNET_KEY", "") or "").strip())


def looks_like_ciphertext(value: str) -> bool:
    """Heuristic: Fernet ciphertext starts with a fixed base64 prefix."""
    return bool(value) and value.startswith(_FERNET_PREFIX)


def _fernet() -> Fernet:
    key = (getattr(settings, "GITHUB_TOKEN_FERNET_KEY", "") or "").strip()
    if not key:
        raise TokenEncryptionError(
            "GITHUB_TOKEN_FERNET_KEY is not configured. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:
        raise TokenEncryptionError(
            "GITHUB_TOKEN_FERNET_KEY is invalid. Use a Fernet.generate_key() value."
        ) from exc


def encrypt_secret(plaintext: str) -> str:
    """Return Fernet ciphertext for a non-empty secret. Empty stays empty."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored: str) -> str:
    """
    Decrypt a stored value.

    Plaintext legacy rows (pre-encryption) are returned as-is so callers can
    re-save and upgrade. Invalid ciphertext raises TokenEncryptionError.
    """
    if not stored:
        return ""
    if not looks_like_ciphertext(stored):
        return stored
    try:
        return _fernet().decrypt(stored.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenEncryptionError(
            "Stored token could not be decrypted. Check GITHUB_TOKEN_FERNET_KEY "
            "matches the key used when the token was encrypted."
        ) from exc
    except TokenEncryptionError:
        raise
    except Exception as exc:
        raise TokenEncryptionError("Stored token could not be decrypted.") from exc


def encrypt_for_storage(plaintext: str) -> str:
    """
    Encrypt for DB storage when a Fernet key is available.

    Production (DEBUG=False) requires a key. In DEBUG without a key, plaintext
    is stored and a warning is logged (local-only escape hatch).
    """
    if not plaintext:
        return ""
    if fernet_key_configured():
        return encrypt_secret(plaintext)
    if settings.DEBUG:
        logger.warning(
            "Storing a GitHub OAuth token without GITHUB_TOKEN_FERNET_KEY "
            "(allowed only when DJANGO_DEBUG=1). Set a Fernet key before "
            "any non-local deploy."
        )
        return plaintext
    raise TokenEncryptionError(
        "GITHUB_TOKEN_FERNET_KEY is required to store GitHub OAuth tokens."
    )
