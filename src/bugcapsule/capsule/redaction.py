"""Deterministic recursive redaction for evidence and model inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue, TypeAdapter

from bugcapsule.capsule.identifiers import stable_identifier
from bugcapsule.capsule.schema import RedactionFinding, RedactionReport


@dataclass(frozen=True)
class RedactionRule:
    """One versioned string-matching rule."""

    rule_id: str
    pattern: re.Pattern[str]
    replacement: str


@dataclass(frozen=True)
class RedactionResult:
    """Redacted JSON value paired with its audit report."""

    value: JsonValue
    report: RedactionReport


DEFAULT_RULES = (
    RedactionRule(
        "authorization-value",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
        "[REDACTED:AUTHORIZATION]",
    ),
    RedactionRule(
        "database-url",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)"
            r"(?:\+[a-z0-9_]+)?://[^\s\"'<>]+",
            re.IGNORECASE,
        ),
        "[REDACTED:DATABASE_URL]",
    ),
    RedactionRule(
        "email",
        re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE),
        "[REDACTED:EMAIL]",
    ),
    RedactionRule(
        "phone-cn",
        re.compile(r"(?<![A-Za-z0-9])(?:\+?86[- ]?)?1[3-9]\d{9}(?![A-Za-z0-9])"),
        "[REDACTED:PHONE]",
    ),
    RedactionRule(
        "common-api-key",
        re.compile(r"(?<![A-Za-z0-9])(?:sk|pk|api)[-_][A-Za-z0-9_-]{16,}(?![A-Za-z0-9])"),
        "[REDACTED:API_KEY]",
    ),
)

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "setcookie",
        "password",
        "passwd",
        "secret",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "token",
        "connectionstring",
        "databaseurl",
    }
)
JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class Redactor:
    """Apply default or injected rules without retaining matched secret text."""

    def __init__(self, rules: tuple[RedactionRule, ...] = DEFAULT_RULES) -> None:
        self.rules = rules

    def redact(self, value: object, *, completed_at: datetime) -> RedactionResult:
        findings: list[RedactionFinding] = []
        normalized = JSON_VALUE_ADAPTER.validate_python(value)
        redacted = self._redact_value(normalized, "$", findings)
        report = RedactionReport(
            completed_at=completed_at,
            total_findings=len(findings),
            findings=tuple(findings),
        )
        return RedactionResult(value=redacted, report=report)

    def _redact_value(
        self,
        value: JsonValue,
        location: str,
        findings: list[RedactionFinding],
    ) -> JsonValue:
        if isinstance(value, dict):
            output: dict[str, JsonValue] = {}
            for key, child in value.items():
                child_location = f"{location}/{self._escape_pointer(str(key))}"
                if self._normalize_field_name(str(key)) in SENSITIVE_FIELD_NAMES:
                    output[str(key)] = "[REDACTED:SENSITIVE_FIELD]"
                    findings.append(
                        self._finding(
                            rule_id="sensitive-field",
                            location=child_location,
                            replacement="[REDACTED:SENSITIVE_FIELD]",
                            match_count=1,
                        )
                    )
                else:
                    output[str(key)] = self._redact_value(child, child_location, findings)
            return output
        if isinstance(value, list):
            return [
                self._redact_value(child, f"{location}/{index}", findings)
                for index, child in enumerate(value)
            ]
        if isinstance(value, str):
            return self._redact_string(value, location, findings)
        return value

    def _redact_string(
        self,
        value: str,
        location: str,
        findings: list[RedactionFinding],
    ) -> str:
        redacted = value
        for rule in self.rules:
            redacted, match_count = rule.pattern.subn(rule.replacement, redacted)
            if match_count:
                findings.append(
                    self._finding(
                        rule_id=rule.rule_id,
                        location=location,
                        replacement=rule.replacement,
                        match_count=match_count,
                    )
                )
        return redacted

    @staticmethod
    def _finding(
        *,
        rule_id: str,
        location: str,
        replacement: str,
        match_count: int,
    ) -> RedactionFinding:
        identity = {
            "rule_id": rule_id,
            "location": location,
            "replacement": replacement,
            "match_count": match_count,
        }
        return RedactionFinding(
            finding_id=stable_identifier("RF", identity),
            rule_id=rule_id,
            location=location,
            replacement=replacement,
            match_count=match_count,
        )

    @staticmethod
    def _normalize_field_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @staticmethod
    def _escape_pointer(value: str) -> str:
        return value.replace("~", "~0").replace("/", "~1")
