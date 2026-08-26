"""Contract tests for the final competition submission manifest."""

import json
from pathlib import Path

import pytest
from scripts.validate_submission_manifest import (
    SubmissionManifestError,
    validate_submission_manifest,
)

PROJECT_ROOT = Path(__file__).parents[1]
MANIFEST = PROJECT_ROOT / "output" / "submission" / "submission-manifest.json"


def test_committed_submission_manifest_covers_all_deliverables_and_is_honest() -> None:
    summary = validate_submission_manifest(MANIFEST, project_root=PROJECT_ROOT)

    assert summary["deliverable_count"] == 8
    assert summary["evidence_path_count"] >= 25
    assert summary["blocker_count"] == 4
    assert summary["ready"] is False
    assert summary["statuses"]["project_pdf"] == "verified"
    assert summary["statuses"]["demo_video"] == "external_pending"


def test_release_readiness_refuses_current_external_blockers() -> None:
    with pytest.raises(SubmissionManifestError, match="unfinished deliverables"):
        validate_submission_manifest(MANIFEST, project_root=PROJECT_ROOT, require_ready=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest["deliverables"].pop(), "scope mismatch"),
        (
            lambda manifest: manifest["deliverables"][1]["paths"].append("../secret"),
            "repository-relative",
        ),
        (
            lambda manifest: manifest["deliverables"][1]["blockers"].append("unexpected"),
            "cannot have blockers",
        ),
    ],
)
def test_submission_manifest_rejects_scope_path_and_status_regressions(
    tmp_path: Path,
    mutate: object,
    message: str,
) -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(document)
    candidate = tmp_path / "manifest.json"
    candidate.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SubmissionManifestError, match=message):
        validate_submission_manifest(candidate, project_root=PROJECT_ROOT)
