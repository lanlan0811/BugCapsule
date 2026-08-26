import re
from pathlib import Path

import pytest

from bugcapsule.analysis.request import AnalysisRequest
from bugcapsule.analysis.schema import ModelAnalysisResponse, ModelRootCause
from bugcapsule.benchmarking.evaluation import EvaluationError, EvaluationRunner
from bugcapsule.benchmarking.schema import EvaluationReport
from bugcapsule.config import Settings


def test_annotated_replay_measures_all_cases_and_persists_bound_report(tmp_path: Path) -> None:
    output = tmp_path / "evaluation"
    report = EvaluationRunner(Settings()).run(output, mode="replay")

    assert report.mode == "replay"
    assert report.provider == "bugcapsule-annotated-replay"
    assert report.metrics.case_count == 12
    assert report.metrics.completed_count == 12
    assert report.metrics.top1_accuracy == 1
    assert report.metrics.citation_validity_rate == 1
    assert report.metrics.required_evidence_coverage_rate == 1
    assert all(result.citation_count == 3 for result in report.cases)
    assert all(result.valid_citation_count == 3 for result in report.cases)
    assert all(result.total_ms >= result.model_or_replay_ms for result in report.cases)
    persisted = EvaluationReport.model_validate_json((output / "evaluation.json").read_bytes())
    assert persisted == report


def test_live_evaluation_requires_explicit_model_and_matching_is_deterministic(
    tmp_path: Path,
) -> None:
    runner = EvaluationRunner(Settings())
    with pytest.raises(EvaluationError, match="MODEL_NAME"):
        runner.run(tmp_path / "live", mode="live")
    assert runner._matches("Connection was not released", (("connection",), ("released",)))
    assert not runner._matches("Connection timeout", (("connection",), ("released",)))


def test_live_evaluation_measures_injected_model_boundary(tmp_path: Path) -> None:
    dataset_runner = EvaluationRunner(Settings())

    class FakeLiveClient:
        def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
            case = next(
                case
                for case in dataset_runner.builder.dataset.cases
                if case.capsule_id in request.input_text
            )
            references = tuple(dict.fromkeys(re.findall(r"EV-[A-F0-9]{12}", request.input_text)))
            return ModelAnalysisResponse(
                root_causes=(
                    ModelRootCause(
                        rank=1,
                        hypothesis=case.expected_hypothesis,
                        confidence=0.9,
                        evidence_refs=(references[0],),
                        unknowns=(),
                    ),
                )
            )

    settings = Settings(model_name="live-test", model_api_key="test-key")
    runner = EvaluationRunner(settings, client_factory=lambda _: FakeLiveClient())
    report = runner.run(tmp_path / "live-evaluation", mode="live")

    assert report.mode == "live"
    assert report.metrics.completed_count == 12
    assert report.metrics.top1_accuracy == 1
    assert report.metrics.citation_validity_rate == 1
    assert report.metrics.required_evidence_coverage_rate == 0
