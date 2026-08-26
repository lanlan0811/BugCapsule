"""Tests for deterministic recursive redaction and its audit report."""

from datetime import datetime, timezone

from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.capsule.redaction import Redactor

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def test_redactor_removes_sensitive_fields_and_value_patterns() -> None:
    original = {
        "headers": {
            "Authorization": "Bearer test-secret-token-value",
            "Cookie": "session=private-session-value",
        },
        "database": "postgresql+psycopg://user:password@db:5432/orders",
        "message": "contact dev@example.com or +86 13800138000",
        "credentials": "Bearer generic-secret-value and sk-live_abcdefghijklmnopqrstuvwxyz",
        "nested": [{"api_key": "sk-exampleabcdefghijklmnop"}],
    }

    result = Redactor().redact(original, completed_at=NOW)
    serialized = canonical_json(result.value)
    report_bytes = canonical_json(result.report.model_dump(mode="json"))

    for secret in (
        b"test-secret-token-value",
        b"private-session-value",
        b"user:password",
        b"dev@example.com",
        b"13800138000",
        b"generic-secret-value",
        b"sk-live_abcdefghijklmnopqrstuvwxyz",
        b"sk-exampleabcdefghijklmnop",
    ):
        assert secret not in serialized
        assert secret not in report_bytes
    assert result.report.total_findings == 8
    assert {finding.rule_id for finding in result.report.findings} == {
        "sensitive-field",
        "database-url",
        "email",
        "phone-cn",
        "authorization-value",
        "common-api-key",
    }


def test_redaction_report_and_finding_ids_are_deterministic() -> None:
    value = {"message": "email first@example.com and second@example.com"}

    first = Redactor().redact(value, completed_at=NOW)
    second = Redactor().redact(value, completed_at=NOW)

    assert first == second
    assert first.report.findings[0].match_count == 2
    assert first.report.findings[0].finding_id.startswith("RF-")


def test_phone_rule_does_not_redact_identifier_substrings() -> None:
    value = {"trace_id": "abc13800138000def", "number": 13800138000}

    result = Redactor().redact(value, completed_at=NOW)

    assert result.value == value


def test_json_pointer_locations_escape_special_key_characters() -> None:
    result = Redactor().redact({"a/b~c": "dev@example.com"}, completed_at=NOW)

    assert result.report.findings[0].location == "$/a~1b~0c"
