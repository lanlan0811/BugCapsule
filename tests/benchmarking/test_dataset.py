from pathlib import Path

import pytest

from bugcapsule.benchmarking.dataset import (
    BenchmarkDatasetBuilder,
    BenchmarkDatasetError,
    load_benchmark_dataset,
)
from bugcapsule.capsule import CapsuleArchive
from bugcapsule.index import CapsuleIndex


def test_packaged_dataset_has_required_size_fault_coverage_and_annotations() -> None:
    dataset = load_benchmark_dataset()

    assert len(dataset.cases) == 12
    assert dataset.simulated_data is True
    assert {case.fault_type for case in dataset.cases} == {
        "connection_leak",
        "database_unreachable",
        "slow_query",
    }
    for fault_type in {case.fault_type for case in dataset.cases}:
        assert sum(case.fault_type == fault_type for case in dataset.cases) == 4
    assert all(case.expected_hypothesis for case in dataset.cases)
    assert all(case.expected_term_groups for case in dataset.cases)


def test_builder_materializes_deterministic_importable_capsules_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    builder = BenchmarkDatasetBuilder()
    first = builder.build(first_dir)
    second = builder.build(second_dir)

    assert first.case_count == 12
    assert first.annotation_sha256 == second.annotation_sha256
    assert first.fault_counts == {
        "connection_leak": 4,
        "database_unreachable": 4,
        "slow_query": 4,
    }
    first_capsules = sorted((first_dir / "capsules").glob("*.bugcapsule"))
    second_capsules = sorted((second_dir / "capsules").glob("*.bugcapsule"))
    assert len(first_capsules) == 12
    assert [path.read_bytes() for path in first_capsules] == [
        path.read_bytes() for path in second_capsules
    ]
    imported = CapsuleArchive().import_capsule(first_capsules[0])
    assert imported.manifest.environment.simulated_data is True
    assert imported.manifest.capsule_id == "cap_eval_001"

    index = CapsuleIndex(first_dir / "index.sqlite3", first_dir / "capsules")
    rebuilt = index.rebuild()
    assert rebuilt.indexed_count == 12
    assert rebuilt.issues == ()

    with pytest.raises(BenchmarkDatasetError, match="already exists"):
        builder.build(first_dir)
    overwritten = builder.build(first_dir, overwrite=True)
    assert overwritten.annotation_sha256 == first.annotation_sha256


def test_loader_reports_missing_or_invalid_dataset(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkDatasetError, match="not found"):
        load_benchmark_dataset(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(BenchmarkDatasetError, match="unreadable or invalid"):
        load_benchmark_dataset(invalid)
