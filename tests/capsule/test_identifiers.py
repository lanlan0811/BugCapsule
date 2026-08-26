"""Tests for canonical serialization and stable identifiers."""

import pytest

from bugcapsule.capsule.identifiers import canonical_json, stable_identifier


def test_canonical_json_is_key_order_independent_and_utf8() -> None:
    first = canonical_json({"中文": "证据", "rank": 1})
    second = canonical_json({"rank": 1, "中文": "证据"})

    assert first == second
    assert b"\\u" not in first


def test_stable_identifier_is_deterministic() -> None:
    assert stable_identifier("EV", {"value": 1}) == stable_identifier("EV", {"value": 1})
    assert stable_identifier("EV", {"value": 1}).startswith("EV-")


@pytest.mark.parametrize("prefix", ["", "证据", "EV_1"])
def test_stable_identifier_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(ValueError, match="prefix"):
        stable_identifier(prefix, {})


def test_stable_identifier_rejects_invalid_digest_length() -> None:
    with pytest.raises(ValueError, match="digest_length"):
        stable_identifier("EV", {}, digest_length=7)
