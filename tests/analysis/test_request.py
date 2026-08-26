from pathlib import Path

import pytest

from bugcapsule.analysis.request import AnalysisRequestError, build_analysis_request
from bugcapsule.capsule import CapsuleArchive
from bugcapsule.capsule.evidence import EvidenceCorrelator
from tests.capsule.factories import make_stage_three_capsule


def test_prompt_is_deterministic_bounded_and_contains_only_selected_evidence(
    tmp_path: Path,
) -> None:
    first_path, _ = make_stage_three_capsule(tmp_path, filename="first.bugcapsule")
    second_path, _ = make_stage_three_capsule(
        tmp_path,
        filename="second.bugcapsule",
        reverse_runtime=True,
    )
    archive = CapsuleArchive()
    first = archive.import_capsule(first_path)
    second = archive.import_capsule(second_path)
    correlator = EvidenceCorrelator()

    first_request = build_analysis_request(
        first.manifest,
        correlator.build(first),
        provider="test",
        model="test-model",
        api_style="responses",
        max_input_bytes=4096,
    )
    second_request = build_analysis_request(
        second.manifest,
        correlator.build(second),
        provider="test",
        model="test-model",
        api_style="responses",
        max_input_bytes=4096,
    )
    assert first_request.request_sha256 == second_request.request_sha256
    assert len(first_request.input_text.encode("utf-8")) <= 4096
    for evidence_id in first_request.included_evidence_ids:
        assert evidence_id in first_request.input_text

    with pytest.raises(AnalysisRequestError, match="too small"):
        build_analysis_request(
            first.manifest,
            correlator.build(first),
            provider="test",
            model="test-model",
            api_style="responses",
            max_input_bytes=10,
        )
