"""Minimal OpenAI-compatible HTTP client with strict structured output."""

from __future__ import annotations

from typing import Any, Protocol, cast

import httpx
from pydantic import ValidationError

from bugcapsule.analysis.request import AnalysisRequest
from bugcapsule.analysis.schema import ModelAnalysisResponse
from bugcapsule.config import Settings


class ModelClientError(RuntimeError):
    """A safe diagnostic for model transport or response failures."""


class InvalidModelResponseError(ModelClientError):
    """A structured response failed local parsing or schema validation."""


class ModelClient(Protocol):
    """Injectable model boundary used by live analysis."""

    def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse: ...


class OpenAICompatibleClient:
    """Call Responses API or Chat Completions without retaining raw output."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.model_name:
            raise ModelClientError("live mode requires BUGCAPSULE_MODEL_NAME")
        if settings.model_api_key is None or not settings.model_api_key.get_secret_value():
            raise ModelClientError("live mode requires BUGCAPSULE_MODEL_API_KEY")
        self.settings = settings
        self._api_key = settings.model_api_key.get_secret_value()
        self._client = httpx.Client(
            timeout=settings.model_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
        url, body = self._request_payload(request)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ModelClientError(f"model request failed: {type(exc).__name__}") from exc
        if not response.is_success:
            raise ModelClientError(f"model request failed with HTTP {response.status_code}")
        try:
            payload = cast(dict[str, Any], response.json())
            output_text = self._extract_output_text(payload)
            return ModelAnalysisResponse.model_validate_json(output_text)
        except (ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            raise InvalidModelResponseError(
                "model returned an invalid structured response"
            ) from exc

    def _request_payload(self, request: AnalysisRequest) -> tuple[str, dict[str, Any]]:
        base_url = str(self.settings.model_base_url).rstrip("/")
        if self.settings.model_api_style == "responses":
            return (
                f"{base_url}/responses",
                {
                    "model": self.settings.model_name,
                    "instructions": request.instructions,
                    "input": request.input_text,
                    "max_output_tokens": self.settings.model_max_output_tokens,
                    "store": False,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "bugcapsule_root_causes",
                            "strict": True,
                            "schema": request.output_schema,
                        }
                    },
                },
            )
        return (
            f"{base_url}/chat/completions",
            {
                "model": self.settings.model_name,
                "messages": [
                    {"role": "system", "content": request.instructions},
                    {"role": "user", "content": request.input_text},
                ],
                "max_tokens": self.settings.model_max_output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "bugcapsule_root_causes",
                        "strict": True,
                        "schema": request.output_schema,
                    },
                },
            },
        )

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        if self.settings.model_api_style == "chat_completions":
            value = payload["choices"][0]["message"]["content"]
            if not isinstance(value, str) or not value:
                raise ValueError("missing chat content")
            return value
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        for output in payload.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        return text
        raise ValueError("missing response output text")
