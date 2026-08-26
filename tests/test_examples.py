"""Integrity and provenance checks for committed review examples."""

import hashlib
import json
from pathlib import Path

from bugcapsule.benchmarking.dataset import load_benchmark_dataset
from bugcapsule.capsule import CapsuleArchive

PROJECT_ROOT = Path(__file__).parents[1]
EXAMPLE_DIR = PROJECT_ROOT / "examples"
EXAMPLE_PATH = EXAMPLE_DIR / "connection-leak-simulated.bugcapsule"


def test_committed_example_matches_checksum_schema_and_dataset_origin() -> None:
    checksum_parts = (EXAMPLE_DIR / "SHA256SUMS").read_text(encoding="ascii").split()
    assert checksum_parts[1] == EXAMPLE_PATH.name
    assert hashlib.sha256(EXAMPLE_PATH.read_bytes()).hexdigest() == checksum_parts[0]

    imported = CapsuleArchive().import_capsule(EXAMPLE_PATH)
    case = load_benchmark_dataset().cases[0]
    assert imported.manifest.capsule_id == case.capsule_id == "cap_eval_001"
    assert imported.manifest.environment.simulated_data is True
    assert imported.manifest.analysis_status == "not_run"
    assert imported.manifest.verification_status == "not_run"
    assert imported.manifest.service.name == case.service_name
    assert imported.manifest.service.entrypoint == case.entrypoint

    source_evidence = json.loads(imported.read("evidence/source-snippets.json"))
    source = next(item for item in source_evidence if item["kind"] == "source")
    assert source["content"]["path"] == case.source_path
    assert source["content"]["line"] == case.source_line
    assert source["content"]["text"] == case.source_text
