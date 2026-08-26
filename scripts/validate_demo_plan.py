"""Validate the competition demo shot list and its repository evidence links."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_PLAN = Path("output/video/demo-shot-list.json")
ALLOWED_MODES = {"live_runtime", "structured_replay", "offline_artifact"}
ALLOWED_ASSET_STATUSES = {"verified", "ready_to_record", "external_pending"}
SHOT_ID_PATTERN = re.compile(r"shot-[0-9]{2}")


class DemoPlanError(RuntimeError):
    """Explain why a demo plan cannot be used for recording."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DemoPlanError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DemoPlanError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DemoPlanError(f"{label} must be an integer")
    return value


def _repository_path(root: Path, raw_path: Any, label: str) -> Path:
    text = _text(raw_path, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise DemoPlanError(f"{label} must be a safe repository-relative path")
    destination = root.joinpath(*path.parts)
    if not destination.exists():
        raise DemoPlanError(f"{label} does not exist: {text}")
    return destination


def validate_demo_plan(plan_path: Path, *, project_root: Path) -> dict[str, Any]:
    """Validate timing, recording modes, evidence links, and honest asset states."""
    try:
        document = _object(json.loads(plan_path.read_text(encoding="utf-8")), "plan")
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoPlanError(f"cannot read demo plan: {exc}") from exc

    if document.get("schema_version") != "0.1.0":
        raise DemoPlanError("schema_version must be 0.1.0")
    target_seconds = _integer(document.get("target_duration_seconds"), "target duration")
    if target_seconds != 180:
        raise DemoPlanError("target duration must be exactly 180 seconds")

    raw_shots = document.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) != 10:
        raise DemoPlanError("shots must contain the ten planned roadshow steps")

    expected_start = 0
    shot_ids: set[str] = set()
    evidence_count = 0
    modes: set[str] = set()
    for position, raw_shot in enumerate(raw_shots, start=1):
        shot = _object(raw_shot, f"shot {position}")
        shot_id = _text(shot.get("id"), f"shot {position} id")
        if SHOT_ID_PATTERN.fullmatch(shot_id) is None or shot_id in shot_ids:
            raise DemoPlanError(f"shot {position} has an invalid or duplicate id")
        shot_ids.add(shot_id)

        start = _integer(shot.get("start_second"), f"{shot_id} start")
        end = _integer(shot.get("end_second"), f"{shot_id} end")
        if start != expected_start or end <= start:
            raise DemoPlanError(
                f"{shot_id} must be positive and contiguous at second {expected_start}"
            )
        expected_start = end

        mode = _text(shot.get("mode"), f"{shot_id} mode")
        if mode not in ALLOWED_MODES:
            raise DemoPlanError(f"{shot_id} uses unsupported mode: {mode}")
        modes.add(mode)
        for field in ("title", "screen", "operator_action", "narration", "success_cue"):
            _text(shot.get(field), f"{shot_id} {field}")

        raw_paths = shot.get("evidence_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise DemoPlanError(f"{shot_id} must link repository evidence")
        for path_index, raw_path in enumerate(raw_paths, start=1):
            _repository_path(project_root, raw_path, f"{shot_id} evidence {path_index}")
            evidence_count += 1

    if expected_start != target_seconds:
        raise DemoPlanError(f"shot timeline ends at {expected_start}, expected {target_seconds}")
    if "live_runtime" not in modes or "structured_replay" not in modes:
        raise DemoPlanError("plan must distinguish runtime proof from structured model replay")

    raw_assets = document.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise DemoPlanError("assets must be a non-empty list")
    asset_statuses: dict[str, str] = {}
    for position, raw_asset in enumerate(raw_assets, start=1):
        asset = _object(raw_asset, f"asset {position}")
        asset_id = _text(asset.get("id"), f"asset {position} id")
        status = _text(asset.get("status"), f"asset {asset_id} status")
        if asset_id in asset_statuses or status not in ALLOWED_ASSET_STATUSES:
            raise DemoPlanError(f"asset {asset_id} has an invalid id or status")
        asset_statuses[asset_id] = status
        raw_path = asset.get("path")
        if status == "verified":
            _repository_path(project_root, raw_path, f"asset {asset_id} path")
        elif raw_path is not None:
            _text(raw_path, f"asset {asset_id} path")

    if asset_statuses.get("final_video") != "external_pending":
        raise DemoPlanError(
            "final_video must remain external_pending until an actual recording exists"
        )

    return {
        "duration_seconds": target_seconds,
        "shot_count": len(raw_shots),
        "evidence_reference_count": evidence_count,
        "modes": sorted(modes),
        "asset_statuses": asset_statuses,
    }


def main() -> int:
    """CLI entry point for local and CI validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--project-root", type=Path, default=Path())
    arguments = parser.parse_args()
    try:
        summary = validate_demo_plan(
            arguments.plan.resolve(),
            project_root=arguments.project_root.resolve(),
        )
    except DemoPlanError as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
