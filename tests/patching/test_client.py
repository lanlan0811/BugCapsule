import json
from typing import Any, cast

import httpx
import pytest

from bugcapsule.analysis.client import InvalidModelResponseError
from bugcapsule.config import Settings
from bugcapsule.patching.client import OpenAICompatiblePatchClient
from bugcapsule.patching.request import PatchRequest


def request() -> PatchRequest:
    return PatchRequest(
        instructions="instructions",
        input_text="input",
        output_schema={"type": "object"},
        included_evidence_ids=frozenset({"EV-AAAAAAAAAAAA"}),
        request_sha256="a" * 64,
    )


def test_patch_client_uses_patch_schema_name_and_rejects_invalid_output() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(incoming: httpx.Request) -> httpx.Response:
        bodies.append(cast(dict[str, Any], json.loads(incoming.content)))
        return httpx.Response(
            200,
            json={
                "output_text": json.dumps(
                    {
                        "summary": "修复连接归还",
                        "unified_diff": "diff",
                        "evidence_refs": ["EV-AAAAAAAAAAAA"],
                        "safety_notes": [],
                    }
                )
            },
        )

    settings = Settings(
        model_name="gpt-test",
        model_api_key="test-key",
        model_base_url="https://models.example/v1",
    )
    client = OpenAICompatiblePatchClient(settings, transport=httpx.MockTransport(handler))
    assert client.generate(request()).summary == "修复连接归还"
    assert bodies[0]["text"]["format"]["name"] == "bugcapsule_patch"

    invalid = OpenAICompatiblePatchClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"output_text": "{}"})),
    )
    with pytest.raises(InvalidModelResponseError, match="invalid Patch"):
        invalid.generate(request())
