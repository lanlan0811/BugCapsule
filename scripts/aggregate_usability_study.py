"""Validate 3-5 consented first-user records and write an anonymous aggregate."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_FIELDS = {
    "participant_id",
    "execution_mode",
    "operating_system",
    "start_to_healthy_seconds",
    "doctor_failed_check_ids",
    "completed_task_ids",
    "hint_count",
    "blocking_step",
    "documentation_gap_codes",
    "confidence_1_to_5",
    "consent_to_publish_anonymized",
}
EXECUTION_MODES = {"participant_operated", "assistant_operated"}
OPERATING_SYSTEMS = {"windows_10", "windows_11", "linux"}
DOCUMENTATION_GAP_CODES = {
    "dependency_install",
    "environment_file",
    "docker_startup",
    "fault_capture",
    "evidence_navigation",
    "patch_approval",
    "verification_report",
    "none",
}
PARTICIPANT_PATTERN = re.compile(r"P[0-9]{2}")
CHECK_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]+")
TASK_IDS = set(range(1, 8))


class UsabilityStudyError(RuntimeError):
    """Explain why participant data cannot be aggregated safely."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UsabilityStudyError(f"{label} must be a JSON object")
    return value


def _integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise UsabilityStudyError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise UsabilityStudyError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise UsabilityStudyError(f"{label} must not contain duplicates")
    return value


def _load_response(path: Path) -> dict[str, Any]:
    try:
        response = _object(json.loads(path.read_text(encoding="utf-8")), path.name)
    except (OSError, json.JSONDecodeError) as exc:
        raise UsabilityStudyError(f"cannot read {path.name}: {exc}") from exc
    if set(response) != EXPECTED_FIELDS:
        missing = sorted(EXPECTED_FIELDS - set(response))
        extra = sorted(set(response) - EXPECTED_FIELDS)
        raise UsabilityStudyError(f"{path.name} field mismatch; missing={missing}, extra={extra}")

    participant_id = response["participant_id"]
    if not isinstance(participant_id, str) or PARTICIPANT_PATTERN.fullmatch(participant_id) is None:
        raise UsabilityStudyError(f"{path.name} participant_id must match P00")
    execution_mode = response["execution_mode"]
    if execution_mode not in EXECUTION_MODES:
        raise UsabilityStudyError(f"{path.name} execution_mode is unsupported")
    operating_system = response["operating_system"]
    if operating_system not in OPERATING_SYSTEMS:
        raise UsabilityStudyError(f"{path.name} operating_system is unsupported")
    _integer(
        response["start_to_healthy_seconds"],
        f"{path.name} start_to_healthy_seconds",
        minimum=1,
        maximum=7200,
    )
    check_ids = _string_list(
        response["doctor_failed_check_ids"], f"{path.name} doctor_failed_check_ids"
    )
    if any(CHECK_ID_PATTERN.fullmatch(check_id) is None for check_id in check_ids):
        raise UsabilityStudyError(f"{path.name} contains an invalid doctor check id")
    completed_tasks = response["completed_task_ids"]
    if (
        not isinstance(completed_tasks, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in completed_tasks)
        or not set(completed_tasks).issubset(TASK_IDS)
        or len(completed_tasks) != len(set(completed_tasks))
    ):
        raise UsabilityStudyError(f"{path.name} completed_task_ids must be unique task IDs 1-7")
    _integer(response["hint_count"], f"{path.name} hint_count", minimum=0, maximum=20)
    blocking_step = response["blocking_step"]
    if blocking_step is not None:
        _integer(blocking_step, f"{path.name} blocking_step", minimum=1, maximum=7)
    gap_codes = _string_list(
        response["documentation_gap_codes"], f"{path.name} documentation_gap_codes"
    )
    if not gap_codes or not set(gap_codes).issubset(DOCUMENTATION_GAP_CODES):
        raise UsabilityStudyError(f"{path.name} contains an invalid documentation gap code")
    if "none" in gap_codes and len(gap_codes) != 1:
        raise UsabilityStudyError(f"{path.name} cannot combine none with a gap code")
    _integer(
        response["confidence_1_to_5"],
        f"{path.name} confidence_1_to_5",
        minimum=1,
        maximum=5,
    )
    if response["consent_to_publish_anonymized"] is not True:
        raise UsabilityStudyError(f"{path.name} lacks consent for anonymous publication")
    return response


def aggregate_usability_study(input_dir: Path) -> dict[str, Any]:
    """Build a deterministic aggregate that contains no participant-level rows."""
    paths = sorted(input_dir.glob("*.json")) if input_dir.is_dir() else []
    if not 3 <= len(paths) <= 5:
        raise UsabilityStudyError("input directory must contain 3-5 JSON responses")
    responses = [_load_response(path) for path in paths]
    non_participant_records = [
        path.name
        for path, response in zip(paths, responses, strict=True)
        if response["execution_mode"] != "participant_operated"
    ]
    if non_participant_records:
        raise UsabilityStudyError(
            "formal aggregate accepts only participant-operated sessions; "
            f"pilot records={non_participant_records}"
        )
    participant_ids = [str(response["participant_id"]) for response in responses]
    if len(participant_ids) != len(set(participant_ids)):
        raise UsabilityStudyError("participant IDs must be unique")

    participant_count = len(responses)
    starts = [int(response["start_to_healthy_seconds"]) for response in responses]
    confidences = [int(response["confidence_1_to_5"]) for response in responses]
    completed = [task for response in responses for task in response["completed_task_ids"]]
    operating_systems = Counter(str(response["operating_system"]) for response in responses)
    failed_checks = Counter(
        check_id for response in responses for check_id in response["doctor_failed_check_ids"]
    )
    blocking_steps = Counter(
        str(response["blocking_step"])
        for response in responses
        if response["blocking_step"] is not None
    )
    gap_codes = Counter(
        gap
        for response in responses
        for gap in response["documentation_gap_codes"]
        if gap != "none"
    )
    task_completion_counts = Counter(str(task) for task in completed)
    median_start = statistics.median(starts)

    return {
        "schema_version": "0.1.0",
        "participant_count": participant_count,
        "median_start_to_healthy_seconds": median_start,
        "median_start_goal_seconds": 600,
        "median_start_goal_met": median_start <= 600,
        "task_completion_rate": round(len(completed) / (participant_count * len(TASK_IDS)), 4),
        "task_completion_counts": dict(sorted(task_completion_counts.items())),
        "median_confidence_1_to_5": statistics.median(confidences),
        "total_hints_given": sum(int(response["hint_count"]) for response in responses),
        "operating_system_counts": dict(sorted(operating_systems.items())),
        "doctor_failed_check_counts": dict(sorted(failed_checks.items())),
        "blocking_step_counts": dict(sorted(blocking_steps.items())),
        "documentation_gap_counts": dict(sorted(gap_codes.items())),
        "privacy": {
            "participant_rows_included": False,
            "free_text_included": False,
            "all_records_consented": True,
            "all_sessions_participant_operated": True,
        },
    }


def main() -> int:
    """CLI entry point for the external usability-study operator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    input_dir = arguments.input_dir.resolve()
    output = arguments.output.resolve()
    if output.exists() and not arguments.force:
        parser.error(f"output already exists: {output}")
    if output.is_relative_to(input_dir):
        parser.error("output must stay outside the raw response directory")
    try:
        summary = aggregate_usability_study(input_dir)
    except UsabilityStudyError as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
