"""Tests for privacy-preserving first-user study aggregation."""

import json
from pathlib import Path

import pytest
from scripts.aggregate_usability_study import UsabilityStudyError, aggregate_usability_study


def _response(participant_id: str, *, start: int, tasks: list[int]) -> dict[str, object]:
    return {
        "participant_id": participant_id,
        "operating_system": "windows_11",
        "start_to_healthy_seconds": start,
        "doctor_failed_check_ids": [],
        "completed_task_ids": tasks,
        "hint_count": 0,
        "blocking_step": None,
        "documentation_gap_codes": ["none"],
        "confidence_1_to_5": 4,
        "consent_to_publish_anonymized": True,
    }


def _write(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_aggregate_usability_study_is_deterministic_and_contains_no_rows(tmp_path: Path) -> None:
    responses = tmp_path / "responses"
    _write(responses, "z.json", _response("P03", start=600, tasks=[1, 2, 3, 4, 5]))
    _write(responses, "a.json", _response("P01", start=420, tasks=[1, 2, 3, 4, 5, 6, 7]))
    second = _response("P02", start=480, tasks=[1, 2, 3, 4, 5, 6])
    second["doctor_failed_check_ids"] = ["docker_engine"]
    second["hint_count"] = 1
    second["blocking_step"] = 6
    second["documentation_gap_codes"] = ["patch_approval"]
    _write(responses, "m.json", second)

    first = aggregate_usability_study(responses)
    repeated = aggregate_usability_study(responses)

    assert first == repeated
    assert first["participant_count"] == 3
    assert first["median_start_to_healthy_seconds"] == 480
    assert first["median_start_goal_met"] is True
    assert first["task_completion_rate"] == pytest.approx(18 / 21, abs=0.0001)
    assert first["doctor_failed_check_counts"] == {"docker_engine": 1}
    assert first["blocking_step_counts"] == {"6": 1}
    assert first["documentation_gap_counts"] == {"patch_approval": 1}
    assert first["privacy"]["participant_rows_included"] is False
    assert "participant_id" not in json.dumps(first)


def test_aggregate_usability_study_requires_three_to_five_records(tmp_path: Path) -> None:
    responses = tmp_path / "responses"
    _write(responses, "p1.json", _response("P01", start=420, tasks=[1]))
    _write(responses, "p2.json", _response("P02", start=480, tasks=[1]))

    with pytest.raises(UsabilityStudyError, match="3-5"):
        aggregate_usability_study(responses)


def test_aggregate_usability_study_rejects_duplicate_participant_ids(tmp_path: Path) -> None:
    responses = tmp_path / "responses"
    for index in range(1, 4):
        _write(responses, f"p{index}.json", _response("P01", start=400 + index, tasks=[1]))

    with pytest.raises(UsabilityStudyError, match="must be unique"):
        aggregate_usability_study(responses)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("consent_to_publish_anonymized", False, "lacks consent"),
        ("documentation_gap_codes", ["none", "docker_startup"], "cannot combine"),
        ("participant_id", "Alice", "P00"),
        ("notes", "contains free text", "field mismatch"),
    ],
)
def test_aggregate_usability_study_rejects_privacy_and_schema_violations(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    responses = tmp_path / "responses"
    for index in range(1, 4):
        payload = _response(f"P{index:02d}", start=400 + index, tasks=[1])
        if index == 1:
            payload[field] = value
        _write(responses, f"p{index}.json", payload)

    with pytest.raises(UsabilityStudyError, match=message):
        aggregate_usability_study(responses)
