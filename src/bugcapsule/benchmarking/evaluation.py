"""Measured root-cause evaluation over the packaged annotated dataset."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from bugcapsule.analysis.client import ModelClient, OpenAICompatibleClient
from bugcapsule.analysis.replay import ReplayRecord, ReplayStore
from bugcapsule.analysis.request import AnalysisRequest, build_analysis_request
from bugcapsule.analysis.schema import ModelAnalysisResponse, ModelRootCause
from bugcapsule.analysis.service import AnalysisError, AnalysisService
from bugcapsule.benchmarking.dataset import BASE_TIME, BenchmarkDatasetBuilder
from bugcapsule.benchmarking.schema import (
    BenchmarkCase,
    EvaluationCaseResult,
    EvaluationMetrics,
    EvaluationReport,
)
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.capsule.schema import EvidenceItem
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex


class EvaluationError(RuntimeError):
    """Raised when an evaluation cannot be started or persisted."""


class TimedModelClient:
    """Measure only the provider boundary without changing its response."""

    def __init__(self, client: ModelClient) -> None:
        self.client = client
        self.elapsed_ns = 0

    def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
        started = perf_counter_ns()
        try:
            return self.client.analyze(request)
        finally:
            self.elapsed_ns += perf_counter_ns() - started


class TimedReplayStore(ReplayStore):
    """Measure replay retrieval separately from deterministic processing."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory)
        self.elapsed_ns = 0

    def load(self, request_sha256: str, *, provider: str, model: str) -> ReplayRecord:
        started = perf_counter_ns()
        try:
            return super().load(request_sha256, provider=provider, model=model)
        finally:
            self.elapsed_ns += perf_counter_ns() - started


class EvaluationRunner:
    """Materialize fresh capsules, analyze each one, and report measured facts."""

    def __init__(
        self,
        settings: Settings,
        *,
        builder: BenchmarkDatasetBuilder | None = None,
        client_factory: Callable[[Settings], ModelClient] | None = None,
    ) -> None:
        self.settings = settings
        self.builder = builder or BenchmarkDatasetBuilder()
        self.client_factory = client_factory or OpenAICompatibleClient

    def run(
        self,
        output_dir: Path,
        *,
        mode: Literal["live", "replay"],
        overwrite: bool = False,
    ) -> EvaluationReport:
        started_at = datetime.now(timezone.utc)
        provider, model = self._model_identity(mode)
        build = self.builder.build(output_dir, overwrite=overwrite)
        runtime_settings = self.settings.model_copy(
            update={
                "data_dir": build.output_dir,
                "replay_dir": build.output_dir / "replay",
                "model_mode": mode,
                "model_provider": provider,
                "model_name": model,
            }
        )
        index = CapsuleIndex.from_settings(runtime_settings)
        rebuilt = index.rebuild()
        if rebuilt.indexed_count != len(self.builder.dataset.cases) or rebuilt.issues:
            raise EvaluationError("benchmark capsules failed authoritative index validation")
        if mode == "replay":
            self._prepare_annotated_replay(runtime_settings, index)

        results = tuple(
            self._evaluate_case(case, runtime_settings, index, mode)
            for case in self.builder.dataset.cases
        )
        metrics = self._metrics(results)
        report = EvaluationReport(
            dataset_name=self.builder.dataset.name,
            annotation_sha256=build.annotation_sha256,
            mode=mode,
            provider=provider,
            model=model,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            cases=results,
            metrics=metrics,
        )
        (build.output_dir / "evaluation.json").write_bytes(
            canonical_json(report.model_dump(mode="json")) + b"\n"
        )
        return report

    def _model_identity(self, mode: Literal["live", "replay"]) -> tuple[str, str]:
        if mode == "replay":
            return "bugcapsule-annotated-replay", "root-cause-v1"
        if not self.settings.model_name:
            raise EvaluationError("live evaluation requires BUGCAPSULE_MODEL_NAME")
        return self.settings.model_provider, self.settings.model_name

    def _prepare_annotated_replay(self, settings: Settings, index: CapsuleIndex) -> None:
        store = ReplayStore(settings.replay_dir)
        for case in self.builder.dataset.cases:
            detail = index.get_detail(case.capsule_id)
            if detail is None:
                raise EvaluationError(f"benchmark capsule missing: {case.capsule_id}")
            request = build_analysis_request(
                detail.manifest,
                detail.evidence,
                provider=settings.model_provider,
                model=settings.model_name,
                api_style=settings.model_api_style,
                max_input_bytes=settings.model_max_input_bytes,
            )
            evidence_refs = self._required_references(case, detail.evidence.items)
            store.save(
                request_sha256=request.request_sha256,
                provider=settings.model_provider,
                model=settings.model_name,
                completed_at=BASE_TIME.replace(tzinfo=timezone.utc),
                response=ModelAnalysisResponse(
                    root_causes=(
                        ModelRootCause(
                            rank=1,
                            hypothesis=case.expected_hypothesis,
                            confidence=0.99,
                            evidence_refs=evidence_refs,
                            unknowns=(),
                        ),
                    )
                ),
            )

    @staticmethod
    def _required_references(
        case: BenchmarkCase, evidence: tuple[EvidenceItem, ...]
    ) -> tuple[str, ...]:
        references: list[str] = []
        for kind in case.required_evidence_kinds:
            match = next(
                (item for item in evidence if item.kind == kind),
                None,
            )
            if match is None:
                raise EvaluationError(f"{case.case_id} is missing required {kind.value} evidence")
            references.append(match.evidence_id)
        return tuple(references)

    def _evaluate_case(
        self,
        case: BenchmarkCase,
        settings: Settings,
        index: CapsuleIndex,
        mode: Literal["live", "replay"],
    ) -> EvaluationCaseResult:
        timed_client: TimedModelClient | None = None
        timed_replay: TimedReplayStore | None = None
        if mode == "live":
            timed_client = TimedModelClient(self.client_factory(settings))
        else:
            timed_replay = TimedReplayStore(settings.replay_dir)
        service = AnalysisService(
            settings,
            index=index,
            client=timed_client,
            replay_store=timed_replay,
        )
        started = perf_counter_ns()
        try:
            result = service.analyze(case.capsule_id, mode=mode)
            artifact = result.artifact
            if artifact is None:
                raise EvaluationError("analysis returned no artifact")
            detail = index.get_detail(case.capsule_id)
            if detail is None:
                raise EvaluationError("analyzed capsule disappeared from index")
            candidate = artifact.root_causes[0]
            available = {item.evidence_id: item.kind for item in detail.evidence.items}
            valid = sum(reference in available for reference in candidate.evidence_refs)
            cited_kinds = {
                available[reference]
                for reference in candidate.evidence_refs
                if reference in available
            }
            status: Literal["completed", "failed"] = "completed"
            error = None
            top1 = self._matches(candidate.hypothesis, case.expected_term_groups)
            required = set(case.required_evidence_kinds).issubset(cited_kinds)
            citations = len(candidate.evidence_refs)
        except (AnalysisError, EvaluationError, OSError, ValueError) as exc:
            status = "failed"
            error = str(exc)[:500]
            top1 = False
            required = False
            citations = 0
            valid = 0
        total_ns = perf_counter_ns() - started
        boundary_ns = (
            timed_client.elapsed_ns
            if timed_client is not None
            else timed_replay.elapsed_ns
            if timed_replay is not None
            else 0
        )
        return EvaluationCaseResult(
            case_id=case.case_id,
            capsule_id=case.capsule_id,
            fault_type=case.fault_type,
            status=status,
            top1_match=top1,
            citation_count=citations,
            valid_citation_count=valid,
            required_evidence_covered=required,
            deterministic_ms=round(max(0, total_ns - boundary_ns) / 1_000_000, 3),
            model_or_replay_ms=round(boundary_ns / 1_000_000, 3),
            total_ms=round(total_ns / 1_000_000, 3),
            error=error,
        )

    @staticmethod
    def _matches(hypothesis: str, groups: tuple[tuple[str, ...], ...]) -> bool:
        normalized = hypothesis.casefold()
        return all(any(term.casefold() in normalized for term in group) for group in groups)

    @classmethod
    def _metrics(cls, results: tuple[EvaluationCaseResult, ...]) -> EvaluationMetrics:
        case_count = len(results)
        citations = sum(item.citation_count for item in results)
        return EvaluationMetrics(
            case_count=case_count,
            completed_count=sum(item.status == "completed" for item in results),
            top1_accuracy=sum(item.top1_match for item in results) / case_count,
            citation_validity_rate=(
                sum(item.valid_citation_count for item in results) / citations if citations else 0
            ),
            required_evidence_coverage_rate=(
                sum(item.required_evidence_covered for item in results) / case_count
            ),
            deterministic_p50_ms=cls._percentile(results, "deterministic_ms", 0.50),
            deterministic_p95_ms=cls._percentile(results, "deterministic_ms", 0.95),
            model_or_replay_p50_ms=cls._percentile(results, "model_or_replay_ms", 0.50),
            model_or_replay_p95_ms=cls._percentile(results, "model_or_replay_ms", 0.95),
            total_p50_ms=cls._percentile(results, "total_ms", 0.50),
            total_p95_ms=cls._percentile(results, "total_ms", 0.95),
        )

    @staticmethod
    def _percentile(
        results: tuple[EvaluationCaseResult, ...], field: str, quantile: float
    ) -> float:
        values = sorted(float(getattr(item, field)) for item in results)
        return values[max(0, math.ceil(quantile * len(values)) - 1)]
