"""Atomic root-cause analysis workflow for indexed capsules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from bugcapsule.analysis.client import (
    InvalidModelResponseError,
    ModelClient,
    ModelClientError,
    OpenAICompatibleClient,
)
from bugcapsule.analysis.replay import ReplayError, ReplayStore
from bugcapsule.analysis.request import AnalysisRequestError, build_analysis_request
from bugcapsule.analysis.schema import AnalysisArtifact, create_artifact
from bugcapsule.capsule.archive import CapsuleArchive, CapsuleArchiveError, create_manifest
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex, CapsuleIndexError

ANALYSIS_PATH = "analysis/root-causes.json"


class AnalysisError(RuntimeError):
    """Safe analysis failure suitable for CLI and Web output."""


@dataclass(frozen=True)
class AnalysisResult:
    """Outcome of one requested analysis operation."""

    status: Literal["completed", "model_off"]
    mode: Literal["live", "replay", "off"]
    artifact: AnalysisArtifact | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": self.mode,
            "artifact": self.artifact.model_dump(mode="json") if self.artifact else None,
        }


class AnalysisService:
    """Coordinate prompt construction, model/replay, validation, and persistence."""

    def __init__(
        self,
        settings: Settings,
        *,
        index: CapsuleIndex | None = None,
        archive: CapsuleArchive | None = None,
        client: ModelClient | None = None,
        replay_store: ReplayStore | None = None,
    ) -> None:
        self.settings = settings
        self.index = index or CapsuleIndex.from_settings(settings)
        self.archive = archive or CapsuleArchive()
        self.client = client
        self.replay_store = replay_store or ReplayStore(settings.replay_dir)

    def analyze(
        self,
        capsule_id: str,
        *,
        mode: Literal["live", "replay", "off"] | None = None,
    ) -> AnalysisResult:
        selected_mode = mode or self.settings.model_mode
        if selected_mode == "off":
            return AnalysisResult(status="model_off", mode="off")
        if not self.settings.model_name:
            raise AnalysisError("analysis requires BUGCAPSULE_MODEL_NAME")
        try:
            detail = self.index.get_detail(capsule_id)
            if detail is None:
                raise AnalysisError(f"capsule does not exist: {capsule_id}")
            imported = self.archive.import_capsule(detail.archive_path)
            request = build_analysis_request(
                detail.manifest,
                detail.evidence,
                provider=self.settings.model_provider,
                model=self.settings.model_name,
                api_style=self.settings.model_api_style,
                max_input_bytes=self.settings.model_max_input_bytes,
            )
            if selected_mode == "live":
                client = self.client or OpenAICompatibleClient(self.settings)
                artifact: AnalysisArtifact | None = None
                response = None
                for attempt in range(2):
                    try:
                        response = client.analyze(request)
                        completed_at = datetime.now(timezone.utc)
                        artifact = create_artifact(
                            mode="live",
                            provider=self.settings.model_provider,
                            model=self.settings.model_name,
                            request_sha256=request.request_sha256,
                            completed_at=completed_at,
                            response=response,
                            available_evidence_ids=set(request.included_evidence_ids),
                        )
                        break
                    except (InvalidModelResponseError, ValueError):
                        if attempt == 1:
                            raise
                if artifact is None or response is None:
                    raise AnalysisError("model did not produce a valid analysis")
            else:
                record = self.replay_store.load(
                    request.request_sha256,
                    provider=self.settings.model_provider,
                    model=self.settings.model_name,
                )
                response = record.response
                completed_at = record.completed_at
                artifact = create_artifact(
                    mode="replay",
                    provider=self.settings.model_provider,
                    model=self.settings.model_name,
                    request_sha256=request.request_sha256,
                    completed_at=completed_at,
                    response=response,
                    available_evidence_ids=set(request.included_evidence_ids),
                )
            if selected_mode == "live":
                self.replay_store.save(
                    request_sha256=request.request_sha256,
                    provider=self.settings.model_provider,
                    model=self.settings.model_name,
                    completed_at=completed_at,
                    response=response,
                )
            payloads = dict(imported.payloads)
            payloads[ANALYSIS_PATH] = canonical_json(artifact.model_dump(mode="json")) + b"\n"
            media_types = {item.path: item.media_type for item in imported.manifest.files}
            media_types[ANALYSIS_PATH] = "application/json"
            manifest = create_manifest(
                capsule_id=imported.manifest.capsule_id,
                created_at=imported.manifest.created_at,
                service=imported.manifest.service,
                trace=imported.manifest.trace,
                git=imported.manifest.git,
                environment=imported.manifest.environment,
                payloads=payloads,
                media_types=media_types,
                analysis_status="completed",
                verification_status=imported.manifest.verification_status,
            )
            self.archive.export(detail.archive_path, manifest, payloads)
            self.index.upsert(detail.archive_path)
            return AnalysisResult(status="completed", mode=selected_mode, artifact=artifact)
        except AnalysisError:
            raise
        except (
            AnalysisRequestError,
            CapsuleArchiveError,
            CapsuleIndexError,
            ModelClientError,
            ReplayError,
            OSError,
            ValueError,
        ) as exc:
            raise AnalysisError(str(exc)) from exc
