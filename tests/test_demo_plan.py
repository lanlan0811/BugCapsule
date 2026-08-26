"""Contract tests for the deterministic 180-second competition demo plan."""

import json
from pathlib import Path

import pytest
from scripts.validate_demo_plan import DemoPlanError, validate_demo_plan

PROJECT_ROOT = Path(__file__).parents[1]
PLAN_PATH = PROJECT_ROOT / "output" / "video" / "demo-shot-list.json"


def test_committed_demo_plan_is_contiguous_honest_and_fully_linked() -> None:
    summary = validate_demo_plan(PLAN_PATH, project_root=PROJECT_ROOT)

    assert summary["duration_seconds"] == 180
    assert summary["shot_count"] == 10
    assert summary["evidence_reference_count"] >= 20
    assert summary["modes"] == ["live_runtime", "offline_artifact", "structured_replay"]
    assert summary["asset_statuses"]["final_video"] == "external_pending"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda plan: plan.update(target_duration_seconds=179), "180 seconds"),
        (lambda plan: plan["shots"][1].update(start_second=13), "contiguous"),
        (lambda plan: plan["shots"][1].update(id="shot-01"), "duplicate"),
        (lambda plan: plan["assets"][-1].update(status="verified"), "does not exist"),
    ],
)
def test_demo_plan_rejects_timing_identity_and_status_regressions(
    tmp_path: Path,
    mutate: object,
    message: str,
) -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(document)
    candidate = tmp_path / "plan.json"
    candidate.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DemoPlanError, match=message):
        validate_demo_plan(candidate, project_root=PROJECT_ROOT)
