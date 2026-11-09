"""Strip credentials and tokens from error text before persisting or showing."""

from __future__ import annotations

import re

# Matches common credential leaks in git/GitHub stderr and URLs.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(x-access-token:)[^@\s/]+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(authorization:\s*token\s+)\S+"),
    re.compile(r"https?://[^:\s]+:[^@\s]+@"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(github_pat_[A-Za-z0-9_]{20,})\b"),
    # Fernet ciphertext accidentally embedded in messages.
    re.compile(r"\bgAAAAA[A-Za-z0-9_\-]{20,}\b"),
)


def sanitize_error_message(text: str, *, max_length: int = 2000) -> str:
    """
    Return a user-safe error string with secrets removed.

    Never store raw git stderr that may include credential-bearing URLs.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cleaned = _SECRET_PATTERNS[0].sub(r"\1***", cleaned)
    cleaned = _SECRET_PATTERNS[1].sub(r"\1***", cleaned)
    cleaned = _SECRET_PATTERNS[2].sub(r"\1***", cleaned)
    cleaned = _SECRET_PATTERNS[3].sub("https://***:***@", cleaned)
    cleaned = _SECRET_PATTERNS[4].sub("***", cleaned)
    cleaned = _SECRET_PATTERNS[5].sub("***", cleaned)
    cleaned = _SECRET_PATTERNS[6].sub("***", cleaned)

    # Collapse noisy whitespace for UI readability.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 3].rstrip() + "..."
    return cleaned
