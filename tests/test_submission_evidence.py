"""Contract tests for the competition evidence index."""

import json
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).parents[1]
EVIDENCE_INDEX = PROJECT_ROOT / "docs" / "submission-evidence.json"
ALLOWED_STATUSES = {"verified", "partially_verified", "external_pending"}


def test_submission_evidence_weights_statuses_and_paths_are_valid() -> None:
    document = json.loads(EVIDENCE_INDEX.read_text(encoding="utf-8"))
    assert document["schema_version"] == "0.1.0"
    dimensions = document["dimensions"]
    assert len(dimensions) == 4
    assert sum(dimension["weight_percent"] for dimension in dimensions) == 100
    assert len({dimension["id"] for dimension in dimensions}) == len(dimensions)

    for dimension in dimensions:
        assert dimension["label"]
        assert dimension["items"]
        for item in dimension["items"]:
            assert item["claim"]
            assert item["verification"]
            assert item["status"] in ALLOWED_STATUSES
            assert item["paths"]
            for raw_path in item["paths"]:
                path = PurePosixPath(raw_path)
                assert not path.is_absolute()
                assert ".." not in path.parts
                assert (PROJECT_ROOT / Path(*path.parts)).exists(), raw_path
