"""Canonical serialization and deterministic identifiers."""

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Serialize JSON-compatible data with stable UTF-8 byte output."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_identifier(prefix: str, value: Any, *, digest_length: int = 12) -> str:
    """Create an uppercase SHA-256-derived identifier for canonical data."""
    if not prefix or not prefix.isascii() or not prefix.replace("-", "").isalpha():
        raise ValueError("identifier prefix must contain ASCII letters and optional hyphens")
    if not 8 <= digest_length <= 64:
        raise ValueError("digest_length must be between 8 and 64")
    digest = hashlib.sha256(canonical_json(value)).hexdigest().upper()
    return f"{prefix.upper()}-{digest[:digest_length]}"


def sha256_hex(value: bytes) -> str:
    """Return a lowercase SHA-256 digest for immutable capsule bytes."""
    return hashlib.sha256(value).hexdigest()
