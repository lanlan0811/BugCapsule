"""Strict schemas for the versioned benchmark dataset."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from bugcapsule.capsule.schema import CapsuleModel, EvidenceKind, Sha256


class BenchmarkCase(CapsuleModel):
    """One simulated failure and its human-authored evaluation annotation."""

    case_id: Annotated[str, StringConstraints(pattern=r"^BC-EVAL-[0-9]{3}$")]
    capsule_id: Annotated[
        str,
        StringConstraints(pattern=r"^cap_eval_[a-z0-9][a-z0-9_]{2,40}$"),
    ]
    fault_type: Literal["connection_leak", "database_unreachable", "slow_query"]
    service_name: str = Field(min_length=1, max_length=120)
    entrypoint: str = Field(min_length=1, max_length=240)
    span_name: str = Field(min_length=1, max_length=240)
    log_message: str = Field(min_length=1, max_length=1000)
    stacktrace: str = Field(min_length=1, max_length=4000)
    source_path: str = Field(pattern=r"^src/[a-zA-Z0-9_./-]+$", max_length=500)
    source_line: int = Field(ge=1, le=1_000_000)
    source_text: str = Field(min_length=1, max_length=20_000)
    expected_hypothesis: str = Field(min_length=1, max_length=4000)
    expected_term_groups: tuple[tuple[str, ...], ...] = Field(min_length=1)
    required_evidence_kinds: tuple[EvidenceKind, ...] = Field(min_length=1)

    @field_validator("expected_term_groups")
    @classmethod
    def validate_terms(cls, groups: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
        if any(not group for group in groups):
            raise ValueError("expected term groups must not be empty")
        if any(not term.strip() or term != term.strip() for group in groups for term in group):
            raise ValueError("expected terms must be non-empty and trimmed")
        return groups

    @field_validator("required_evidence_kinds")
    @classmethod
    def validate_required_kinds(cls, values: tuple[EvidenceKind, ...]) -> tuple[EvidenceKind, ...]:
        if len(values) != len(set(values)):
            raise ValueError("required evidence kinds must be unique")
        return values


class BenchmarkDataset(CapsuleModel):
    """Versioned benchmark manifest checked before any capsule is written."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    name: Literal["bugcapsule-simulated-root-cause-v1"]
    simulated_data: Literal[True] = True
    cases: tuple[BenchmarkCase, ...] = Field(min_length=12)

    @model_validator(mode="after")
    def validate_coverage(self) -> BenchmarkDataset:
        case_ids = [case.case_id for case in self.cases]
        capsule_ids = [case.capsule_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)) or len(capsule_ids) != len(set(capsule_ids)):
            raise ValueError("benchmark case and capsule IDs must be unique")
        counts = {
            fault: sum(case.fault_type == fault for case in self.cases)
            for fault in ("connection_leak", "database_unreachable", "slow_query")
        }
        if any(count < 4 for count in counts.values()):
            raise ValueError("benchmark requires at least four cases for every fault type")
        return self


class EvaluationCaseResult(CapsuleModel):
    """Measured result for one annotated capsule."""

    case_id: str
    capsule_id: str
    fault_type: str
    status: Literal["completed", "failed"]
    top1_match: bool
    citation_count: int = Field(ge=0)
    valid_citation_count: int = Field(ge=0)
    required_evidence_covered: bool
    deterministic_ms: float = Field(ge=0)
    model_or_replay_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)
    error: str | None = Field(default=None, max_length=500)


class EvaluationMetrics(CapsuleModel):
    """Aggregate accuracy, validity and measured latency percentiles."""

    case_count: int = Field(ge=1)
    completed_count: int = Field(ge=0)
    top1_accuracy: float = Field(ge=0, le=1)
    citation_validity_rate: float = Field(ge=0, le=1)
    required_evidence_coverage_rate: float = Field(ge=0, le=1)
    deterministic_p50_ms: float = Field(ge=0)
    deterministic_p95_ms: float = Field(ge=0)
    model_or_replay_p50_ms: float = Field(ge=0)
    model_or_replay_p95_ms: float = Field(ge=0)
    total_p50_ms: float = Field(ge=0)
    total_p95_ms: float = Field(ge=0)


class EvaluationReport(CapsuleModel):
    """Versioned result bound to exact annotations and model identity."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    dataset_name: str
    annotation_sha256: Sha256
    simulated_data: Literal[True] = True
    mode: Literal["live", "replay"]
    provider: str
    model: str
    started_at: AwareDatetime
    completed_at: AwareDatetime
    cases: tuple[EvaluationCaseResult, ...] = Field(min_length=12)
    metrics: EvaluationMetrics

    @model_validator(mode="after")
    def validate_case_count(self) -> EvaluationReport:
        if self.metrics.case_count != len(self.cases):
            raise ValueError("evaluation metrics case_count must match cases")
        return self
