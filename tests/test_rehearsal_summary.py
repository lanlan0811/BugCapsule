"""Contract tests for real three-run demo rehearsal evidence."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.validate_rehearsal_summary import (
    RehearsalSummaryError,
    validate_rehearsal_summary,
)

COMMIT = "a" * 40
SHA256 = "b" * 64


def _summary() -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for position, duration in enumerate((179, 180, 181), start=1):
        started = datetime(2026, 8, 26, 2, position, tzinfo=timezone.utc)
        runs.append(
            {
                "id": f"rehearsal-{position:02d}",
                "started_at": started.isoformat(),
                "completed_at": (started + timedelta(seconds=duration)).isoformat(),
                "duration_seconds": duration,
                "network_mode": "offline" if position == 3 else "online",
                "model_mode": "replay",
                "fault_http_statuses": [500, 500, 503],
                "fault_code": "database_pool_exhausted",
                "capsule_sha256": SHA256,
                "report_sha256": "c" * 64,
                "verification_before_exit_code": 1,
                "verification_after_exit_code": 0,
                "workspace_unchanged": True,
                "offline_replay_passed": True,
                "operator_observation_codes": ["none"],
                "failed_checkpoint": None,
            }
        )
    return {
        "schema_version": "0.1.0",
        "project_commit_sha": COMMIT,
        "operating_system": "Windows 10 22H2",
        "docker_version": "Docker Engine test-version",
        "docker_compose_version": "Docker Compose test-version",
        "runs": runs,
    }


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_valid_rehearsal_summary_proves_three_runs_and_offline_fallback(tmp_path: Path) -> None:
    path = tmp_path / "rehearsal-summary.json"
    _write(path, _summary())

    result = validate_rehearsal_summary(path, expected_commit=COMMIT)

    assert result == {
        "project_commit_sha": COMMIT,
        "rehearsal_count": 3,
        "offline_rehearsal_count": 1,
        "minimum_duration_seconds": 179,
        "median_duration_seconds": 180,
        "maximum_duration_seconds": 181,
        "ready_for_final_recording": True,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value["runs"].pop(), "exactly three"),
        (lambda value: value["runs"][0].update(duration_seconds=190), "timestamps"),
        (lambda value: value["runs"][1].update(fault_http_statuses=[500, 503]), "500/500/503"),
        (lambda value: value["runs"][2].update(network_mode="online"), "offline"),
        (lambda value: value["runs"][0].update(operator_notes="free text"), "field mismatch"),
    ],
)
def test_rehearsal_summary_rejects_incomplete_or_unverifiable_claims(
    tmp_path: Path,
    mutate: object,
    message: str,
) -> None:
    document = _summary()
    assert callable(mutate)
    mutate(document)
    path = tmp_path / "rehearsal-summary.json"
    _write(path, document)

    with pytest.raises(RehearsalSummaryError, match=message):
        validate_rehearsal_summary(path, expected_commit=COMMIT)


def test_rehearsal_summary_must_match_the_frozen_commit(tmp_path: Path) -> None:
    path = tmp_path / "rehearsal-summary.json"
    _write(path, _summary())

    with pytest.raises(RehearsalSummaryError, match="frozen commit"):
        validate_rehearsal_summary(path, expected_commit="d" * 40)
