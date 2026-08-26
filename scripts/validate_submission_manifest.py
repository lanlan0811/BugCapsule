"""Validate the final competition submission manifest and optional release readiness."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MANIFEST = Path("output/submission/submission-manifest.json")
ALLOWED_STATUSES = {"verified", "partially_verified", "external_pending"}
REQUIRED_DELIVERABLE_IDS = {
    "source_repositories",
    "bilingual_documentation",
    "reproducible_evidence",
    "project_pdf",
    "demo_video",
    "offline_demo",
    "open_source_supply_chain",
    "review_evidence_index",
}
COMMIT_PATTERN = re.compile(r"[a-f0-9]{40}")


class SubmissionManifestError(RuntimeError):
    """Explain why submission materials are inconsistent or not release-ready."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SubmissionManifestError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SubmissionManifestError(f"{label} must be non-empty text")
    return value.strip()


def _safe_path(raw_path: Any, *, project_root: Path, label: str, must_exist: bool) -> Path:
    text = _text(raw_path, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise SubmissionManifestError(f"{label} must be repository-relative and safe")
    destination = project_root.joinpath(*path.parts)
    if must_exist and not destination.exists():
        raise SubmissionManifestError(f"{label} does not exist: {text}")
    return destination


def validate_submission_manifest(
    manifest_path: Path,
    *,
    project_root: Path,
    require_ready: bool = False,
) -> dict[str, Any]:
    """Validate scope, path evidence, honest blockers, and optional freeze readiness."""
    try:
        document = _object(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    except (OSError, json.JSONDecodeError) as exc:
        raise SubmissionManifestError(f"cannot read submission manifest: {exc}") from exc

    if document.get("schema_version") != "0.1.0":
        raise SubmissionManifestError("schema_version must be 0.1.0")
    if document.get("release_tag") != "v0.1.0":
        raise SubmissionManifestError("release_tag must be v0.1.0")
    release_commit = document.get("release_commit")
    if release_commit is not None and (
        not isinstance(release_commit, str) or COMMIT_PATTERN.fullmatch(release_commit) is None
    ):
        raise SubmissionManifestError("release_commit must be null or a full lowercase Git SHA")

    raw_deliverables = document.get("deliverables")
    if not isinstance(raw_deliverables, list):
        raise SubmissionManifestError("deliverables must be a list")
    statuses: dict[str, str] = {}
    evidence_path_count = 0
    blockers: list[str] = []
    for position, raw_deliverable in enumerate(raw_deliverables, start=1):
        deliverable = _object(raw_deliverable, f"deliverable {position}")
        deliverable_id = _text(deliverable.get("id"), f"deliverable {position} id")
        status = _text(deliverable.get("status"), f"deliverable {deliverable_id} status")
        if deliverable_id in statuses or status not in ALLOWED_STATUSES:
            raise SubmissionManifestError(
                f"deliverable {deliverable_id} has invalid identity/status"
            )
        statuses[deliverable_id] = status
        _text(deliverable.get("label"), f"deliverable {deliverable_id} label")

        raw_paths = deliverable.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise SubmissionManifestError(f"deliverable {deliverable_id} must have evidence paths")
        for path_index, raw_path in enumerate(raw_paths, start=1):
            _safe_path(
                raw_path,
                project_root=project_root,
                label=f"deliverable {deliverable_id} path {path_index}",
                must_exist=True,
            )
            evidence_path_count += 1

        raw_blockers = deliverable.get("blockers", [])
        if not isinstance(raw_blockers, list):
            raise SubmissionManifestError(f"deliverable {deliverable_id} blockers must be a list")
        normalized_blockers = [
            _text(blocker, f"deliverable {deliverable_id} blocker") for blocker in raw_blockers
        ]
        if status == "verified" and normalized_blockers:
            raise SubmissionManifestError(
                f"verified deliverable {deliverable_id} cannot have blockers"
            )
        if status != "verified" and not normalized_blockers:
            raise SubmissionManifestError(
                f"unfinished deliverable {deliverable_id} must explain blockers"
            )
        blockers.extend(f"{deliverable_id}: {blocker}" for blocker in normalized_blockers)

        raw_outputs = deliverable.get("expected_outputs", [])
        if not isinstance(raw_outputs, list):
            raise SubmissionManifestError(
                f"deliverable {deliverable_id} expected_outputs must be a list"
            )
        for output_index, raw_output in enumerate(raw_outputs, start=1):
            _safe_path(
                raw_output,
                project_root=project_root,
                label=f"deliverable {deliverable_id} output {output_index}",
                must_exist=require_ready and status == "verified",
            )

    if set(statuses) != REQUIRED_DELIVERABLE_IDS:
        missing = sorted(REQUIRED_DELIVERABLE_IDS - set(statuses))
        extra = sorted(set(statuses) - REQUIRED_DELIVERABLE_IDS)
        raise SubmissionManifestError(
            f"deliverable scope mismatch; missing={missing}, extra={extra}"
        )
    if require_ready:
        unfinished = sorted(item for item, status in statuses.items() if status != "verified")
        if unfinished:
            raise SubmissionManifestError(
                f"release is blocked by unfinished deliverables: {unfinished}"
            )
        if release_commit is None:
            raise SubmissionManifestError("release_commit must be frozen before release")

    return {
        "deliverable_count": len(statuses),
        "evidence_path_count": evidence_path_count,
        "statuses": statuses,
        "blocker_count": len(blockers),
        "ready": not blockers and release_commit is not None,
    }


def main() -> int:
    """CLI entry point used by maintainers and the tag release workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project-root", type=Path, default=Path())
    parser.add_argument("--require-ready", action="store_true")
    arguments = parser.parse_args()
    try:
        summary = validate_submission_manifest(
            arguments.manifest.resolve(),
            project_root=arguments.project_root.resolve(),
            require_ready=arguments.require_ready,
        )
    except SubmissionManifestError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
