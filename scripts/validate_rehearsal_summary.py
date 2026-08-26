"""Validate three real Windows Docker rehearsals without creating placeholder evidence."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_FIELDS = {
    "schema_version",
    "project_commit_sha",
    "operating_system",
    "docker_version",
    "docker_compose_version",
    "runs",
}
EXPECTED_RUN_FIELDS = {
    "id",
    "started_at",
    "completed_at",
    "duration_seconds",
    "network_mode",
    "model_mode",
    "fault_http_statuses",
    "fault_code",
    "capsule_sha256",
    "report_sha256",
    "verification_before_exit_code",
    "verification_after_exit_code",
    "workspace_unchanged",
    "offline_replay_passed",
    "operator_observation_codes",
    "failed_checkpoint",
}
OBSERVATION_CODES = {
    "audio_issue",
    "command_retry",
    "cursor_visibility",
    "narration_miss",
    "none",
    "timing_overrun",
    "timing_underrun",
    "ui_wait",
}
SHA256_PATTERN = re.compile(r"[a-f0-9]{64}")
COMMIT_PATTERN = re.compile(r"[a-f0-9]{40}")
WINDOWS_PATTERN = re.compile(r"Windows (?:10|11)(?: .+)?")


class RehearsalSummaryError(RuntimeError):
    """Explain why rehearsal evidence cannot be accepted."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RehearsalSummaryError(f"{label} must be a JSON object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise RehearsalSummaryError(f"{label} field mismatch; missing={missing}, extra={extra}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RehearsalSummaryError(f"{label} must be non-empty trimmed text")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RehearsalSummaryError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RehearsalSummaryError(f"{label} must include a UTC offset")
    return parsed


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RehearsalSummaryError(f"{label} must be an integer")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if SHA256_PATTERN.fullmatch(text) is None:
        raise RehearsalSummaryError(f"{label} must be a lowercase SHA-256")
    return text


def validate_rehearsal_summary(
    summary_path: Path,
    *,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Validate three passing rehearsals and return non-sensitive aggregate facts."""
    try:
        document = _object(json.loads(summary_path.read_text(encoding="utf-8")), "summary")
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalSummaryError(f"cannot read rehearsal summary: {exc}") from exc
    _exact_fields(document, EXPECTED_FIELDS, "summary")
    if document["schema_version"] != "0.1.0":
        raise RehearsalSummaryError("schema_version must be 0.1.0")

    commit = _text(document["project_commit_sha"], "project_commit_sha")
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise RehearsalSummaryError("project_commit_sha must be a full lowercase Git SHA")
    if expected_commit is not None and commit != expected_commit:
        raise RehearsalSummaryError("project_commit_sha does not match the frozen commit")
    operating_system = _text(document["operating_system"], "operating_system")
    if WINDOWS_PATTERN.fullmatch(operating_system) is None:
        raise RehearsalSummaryError("operating_system must identify Windows 10 or Windows 11")
    _text(document["docker_version"], "docker_version")
    _text(document["docker_compose_version"], "docker_compose_version")

    runs = document["runs"]
    if not isinstance(runs, list) or len(runs) != 3:
        raise RehearsalSummaryError("runs must contain exactly three rehearsals")
    durations: list[int] = []
    offline_count = 0
    for position, raw_run in enumerate(runs, start=1):
        run = _object(raw_run, f"run {position}")
        _exact_fields(run, EXPECTED_RUN_FIELDS, f"run {position}")
        expected_id = f"rehearsal-{position:02d}"
        if run["id"] != expected_id:
            raise RehearsalSummaryError(f"run {position} id must be {expected_id}")
        started_at = _timestamp(run["started_at"], f"{expected_id} started_at")
        completed_at = _timestamp(run["completed_at"], f"{expected_id} completed_at")
        duration = _integer(run["duration_seconds"], f"{expected_id} duration_seconds")
        measured_duration = (completed_at - started_at).total_seconds()
        if completed_at <= started_at or abs(measured_duration - duration) > 2:
            raise RehearsalSummaryError(f"{expected_id} duration must match its timestamps")
        if not 175 <= duration <= 185:
            raise RehearsalSummaryError(f"{expected_id} duration must be within 180±5 seconds")
        durations.append(duration)

        network_mode = run["network_mode"]
        if network_mode not in {"online", "offline"}:
            raise RehearsalSummaryError(f"{expected_id} network_mode is unsupported")
        offline_count += network_mode == "offline"
        if run["model_mode"] != "replay":
            raise RehearsalSummaryError(f"{expected_id} must disclose replay model mode")
        if run["fault_http_statuses"] != [500, 500, 503]:
            raise RehearsalSummaryError(f"{expected_id} fault status sequence must be 500/500/503")
        if run["fault_code"] != "database_pool_exhausted":
            raise RehearsalSummaryError(f"{expected_id} fault_code is invalid")
        _sha256(run["capsule_sha256"], f"{expected_id} capsule_sha256")
        _sha256(run["report_sha256"], f"{expected_id} report_sha256")
        before_code = _integer(
            run["verification_before_exit_code"],
            f"{expected_id} verification_before_exit_code",
        )
        after_code = _integer(
            run["verification_after_exit_code"],
            f"{expected_id} verification_after_exit_code",
        )
        if before_code == 0 or after_code != 0:
            raise RehearsalSummaryError(f"{expected_id} must prove before failure and after pass")
        for field in ("workspace_unchanged", "offline_replay_passed"):
            if run[field] is not True:
                raise RehearsalSummaryError(f"{expected_id} {field} must be true")
        if run["failed_checkpoint"] is not None:
            raise RehearsalSummaryError(f"{expected_id} failed_checkpoint must be null")

        observations = run["operator_observation_codes"]
        if (
            not isinstance(observations, list)
            or not observations
            or any(not isinstance(item, str) for item in observations)
            or len(observations) != len(set(observations))
            or not set(observations).issubset(OBSERVATION_CODES)
            or ("none" in observations and len(observations) != 1)
        ):
            raise RehearsalSummaryError(f"{expected_id} operator observation codes are invalid")

    if offline_count < 1:
        raise RehearsalSummaryError("at least one rehearsal must run in offline network mode")
    return {
        "project_commit_sha": commit,
        "rehearsal_count": len(runs),
        "offline_rehearsal_count": offline_count,
        "minimum_duration_seconds": min(durations),
        "median_duration_seconds": statistics.median(durations),
        "maximum_duration_seconds": max(durations),
        "ready_for_final_recording": True,
    }


def main() -> int:
    """CLI entry point for the external recording operator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--expected-commit")
    arguments = parser.parse_args()
    if arguments.expected_commit is not None and (
        COMMIT_PATTERN.fullmatch(arguments.expected_commit) is None
    ):
        parser.error("--expected-commit must be a full lowercase Git SHA")
    try:
        result = validate_rehearsal_summary(
            arguments.summary.resolve(),
            expected_commit=arguments.expected_commit,
        )
    except RehearsalSummaryError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
