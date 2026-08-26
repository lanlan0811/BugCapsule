"""Generate, validate, and atomically persist one evidence-bound Patch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from bugcapsule.analysis.client import InvalidModelResponseError, ModelClientError
from bugcapsule.capsule.archive import CapsuleArchive, CapsuleArchiveError, create_manifest
from bugcapsule.capsule.identifiers import canonical_json, sha256_hex
from bugcapsule.capsule.schema import (
    EvidenceKind,
    PatchCandidate,
    RootCauseCandidate,
    validate_evidence_references,
)
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex, CapsuleIndexError
from bugcapsule.patching.client import OpenAICompatiblePatchClient, PatchModelClient
from bugcapsule.patching.replay import PatchReplayError, PatchReplayStore
from bugcapsule.patching.request import PatchRequestError, build_patch_request
from bugcapsule.patching.safety import PatchSafetyError, PatchSafetyValidator, SafePatch
from bugcapsule.patching.schema import ModelPatchResponse, PatchArtifact

PATCH_DIFF_PATH = "patches/candidate.diff"
PATCH_METADATA_PATH = "patches/candidate.json"


class PatchGenerationError(RuntimeError):
    """Safe Patch generation error for CLI and Web presentation."""


@dataclass(frozen=True)
class PatchGenerationResult:
    """Outcome of a requested Patch generation operation."""

    status: Literal["completed", "model_off"]
    mode: Literal["live", "replay", "off"]
    artifact: PatchArtifact | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": self.mode,
            "artifact": self.artifact.model_dump(mode="json") if self.artifact else None,
        }


class PatchGenerationService:
    """Keep model suggestion separate from deterministic Patch authority."""

    def __init__(
        self,
        settings: Settings,
        *,
        index: CapsuleIndex | None = None,
        archive: CapsuleArchive | None = None,
        client: PatchModelClient | None = None,
        replay_store: PatchReplayStore | None = None,
        validator: PatchSafetyValidator | None = None,
    ) -> None:
        self.settings = settings
        self.index = index or CapsuleIndex.from_settings(settings)
        self.archive = archive or CapsuleArchive()
        self.client = client
        self.replay_store = replay_store or PatchReplayStore(settings.replay_dir)
        self.validator = validator or PatchSafetyValidator(
            source_root=settings.source_root,
            allowed_roots=settings.patch_allowed_roots,
            protected_paths=settings.patch_protected_paths,
            max_bytes=settings.patch_max_bytes,
        )

    def generate(
        self,
        capsule_id: str,
        *,
        root_cause_id: str | None = None,
        mode: Literal["live", "replay", "off"] | None = None,
    ) -> PatchGenerationResult:
        selected_mode = mode or self.settings.model_mode
        if selected_mode == "off":
            return PatchGenerationResult(status="model_off", mode="off")
        if not self.settings.model_name:
            raise PatchGenerationError("Patch generation requires BUGCAPSULE_MODEL_NAME")
        try:
            detail = self.index.get_detail(capsule_id)
            if detail is None:
                raise PatchGenerationError(f"capsule does not exist: {capsule_id}")
            if detail.analysis is None:
                raise PatchGenerationError(
                    "Patch generation requires completed root-cause analysis"
                )
            root_cause = self._select_root_cause(detail.analysis.root_causes, root_cause_id)
            request = build_patch_request(
                detail.manifest,
                detail.evidence,
                root_cause,
                provider=self.settings.model_provider,
                model=self.settings.model_name,
                api_style=self.settings.model_api_style,
                max_input_bytes=self.settings.model_max_input_bytes,
            )
            source_paths = {
                str(item.content["path"])
                for item in detail.evidence.items
                if item.kind is EvidenceKind.SOURCE and isinstance(item.content.get("path"), str)
            }
            if selected_mode == "live":
                client = self.client or OpenAICompatiblePatchClient(self.settings)
                artifact: PatchArtifact | None = None
                response: ModelPatchResponse | None = None
                safe_patch: SafePatch | None = None
                for attempt in range(2):
                    try:
                        response = client.generate(request)
                        artifact, safe_patch = self._validate_response(
                            response=response,
                            mode="live",
                            request_sha256=request.request_sha256,
                            root_cause=root_cause,
                            included_evidence_ids=set(request.included_evidence_ids),
                            source_paths=source_paths,
                            completed_at=datetime.now(timezone.utc),
                        )
                        break
                    except (InvalidModelResponseError, ValueError):
                        if attempt == 1:
                            raise
                if artifact is None or response is None or safe_patch is None:
                    raise PatchGenerationError("model did not produce a valid Patch")
                self.replay_store.save(
                    request_sha256=request.request_sha256,
                    provider=self.settings.model_provider,
                    model=self.settings.model_name,
                    completed_at=artifact.completed_at,
                    response=response,
                )
            else:
                replay = self.replay_store.load(
                    request.request_sha256,
                    provider=self.settings.model_provider,
                    model=self.settings.model_name,
                )
                artifact, safe_patch = self._validate_response(
                    response=replay.response,
                    mode="replay",
                    request_sha256=request.request_sha256,
                    root_cause=root_cause,
                    included_evidence_ids=set(request.included_evidence_ids),
                    source_paths=source_paths,
                    completed_at=replay.completed_at,
                )
            imported = self.archive.import_capsule(detail.archive_path)
            payloads = dict(imported.payloads)
            payloads[PATCH_DIFF_PATH] = safe_patch.diff.encode("utf-8")
            payloads[PATCH_METADATA_PATH] = canonical_json(artifact.model_dump(mode="json")) + b"\n"
            media_types = {item.path: item.media_type for item in imported.manifest.files}
            media_types[PATCH_DIFF_PATH] = "text/x-diff"
            media_types[PATCH_METADATA_PATH] = "application/json"
            manifest = create_manifest(
                capsule_id=imported.manifest.capsule_id,
                created_at=imported.manifest.created_at,
                service=imported.manifest.service,
                trace=imported.manifest.trace,
                git=imported.manifest.git,
                environment=imported.manifest.environment,
                payloads=payloads,
                media_types=media_types,
                analysis_status=imported.manifest.analysis_status,
                verification_status=imported.manifest.verification_status,
            )
            self.archive.export(detail.archive_path, manifest, payloads)
            self.index.upsert(detail.archive_path)
            return PatchGenerationResult(status="completed", mode=selected_mode, artifact=artifact)
        except PatchGenerationError:
            raise
        except (
            CapsuleArchiveError,
            CapsuleIndexError,
            InvalidModelResponseError,
            ModelClientError,
            OSError,
            PatchReplayError,
            PatchRequestError,
            PatchSafetyError,
            ValueError,
        ) as exc:
            raise PatchGenerationError(str(exc)) from exc

    def _validate_response(
        self,
        *,
        response: ModelPatchResponse,
        mode: Literal["live", "replay"],
        request_sha256: str,
        root_cause: RootCauseCandidate,
        included_evidence_ids: set[str],
        source_paths: set[str],
        completed_at: datetime,
    ) -> tuple[PatchArtifact, SafePatch]:
        validate_evidence_references(response.evidence_refs, included_evidence_ids)
        safe_patch = self.validator.validate(
            response.unified_diff,
            source_evidence_paths=source_paths,
        )
        diff_sha256 = sha256_hex(safe_patch.diff.encode("utf-8"))
        candidate = PatchCandidate.create(
            root_cause_id=root_cause.root_cause_id,
            summary=response.summary,
            diff_path=PATCH_DIFF_PATH,
            sha256=diff_sha256,
            modified_files=safe_patch.modified_files,
            evidence_refs=response.evidence_refs,
            safety_checks=safe_patch.safety_checks,
        )
        return (
            PatchArtifact(
                mode=mode,
                provider=self.settings.model_provider,
                model=self.settings.model_name,
                request_sha256=request_sha256,
                completed_at=completed_at,
                candidate=candidate,
            ),
            safe_patch,
        )

    @staticmethod
    def _select_root_cause(
        candidates: tuple[RootCauseCandidate, ...],
        root_cause_id: str | None,
    ) -> RootCauseCandidate:
        if root_cause_id is None:
            return candidates[0]
        for candidate in candidates:
            if candidate.root_cause_id == root_cause_id:
                return candidate
        raise PatchGenerationError(f"root cause does not exist: {root_cause_id}")
