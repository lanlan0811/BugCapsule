"""Structured Patch client over the shared OpenAI-compatible transport."""

from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import ValidationError

from bugcapsule.analysis.client import InvalidModelResponseError, OpenAICompatibleClient
from bugcapsule.config import Settings
from bugcapsule.patching.request import PatchRequest
from bugcapsule.patching.schema import ModelPatchResponse


class PatchModelClient(Protocol):
    """Injectable boundary for Patch proposal tests and live providers."""

    def generate(self, request: PatchRequest) -> ModelPatchResponse: ...


class OpenAICompatiblePatchClient:
    """Parse the Patch-specific Schema over the common safe HTTP transport."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = OpenAICompatibleClient(settings, transport=transport)

    def generate(self, request: PatchRequest) -> ModelPatchResponse:
        output = self.client.request_structured(request, schema_name="bugcapsule_patch")
        try:
            return ModelPatchResponse.model_validate_json(output)
        except ValidationError as exc:
            raise InvalidModelResponseError("model returned an invalid Patch response") from exc
