import json
from typing import Any, Literal, cast

import httpx
import pytest

from bugcapsule.analysis.client import ModelClientError, OpenAICompatibleClient
from bugcapsule.analysis.request import AnalysisRequest
from bugcapsule.config import Settings

MODEL_OUTPUT = {
    "root_causes": [
        {
            "rank": 1,
            "hypothesis": "连接泄漏导致连接池耗尽",
            "confidence": 0.9,
            "evidence_refs": ["EV-AAAAAAAAAAAA"],
            "unknowns": [],
        }
    ]
}


def request() -> AnalysisRequest:
    return AnalysisRequest(
        instructions="instructions",
        input_text="input",
        output_schema={"type": "object"},
        included_evidence_ids=frozenset({"EV-AAAAAAAAAAAA"}),
        request_sha256="a" * 64,
    )


def settings(
    *,
    model_api_style: Literal["responses", "chat_completions"] = "responses",
    model_name: str = "gpt-test",
    model_api_key: str | None = "top-secret-key",
) -> Settings:
    return Settings(
        model_name=model_name,
        model_api_key=model_api_key,
        model_base_url="https://models.example/v1",
        model_api_style=model_api_style,
    )


def test_responses_request_uses_strict_schema_and_store_false() -> None:
    captured: dict[str, object] = {}

    def handler(incoming: httpx.Request) -> httpx.Response:
        captured["url"] = str(incoming.url)
        captured["authorization"] = incoming.headers["authorization"]
        captured["body"] = json.loads(incoming.content)
        return httpx.Response(200, json={"output_text": json.dumps(MODEL_OUTPUT)})

    client = OpenAICompatibleClient(settings(), transport=httpx.MockTransport(handler))
    result = client.analyze(request())

    body = cast(dict[str, Any], captured["body"])
    assert captured["url"] == "https://models.example/v1/responses"
    assert captured["authorization"] == "Bearer top-secret-key"
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert result.root_causes[0].rank == 1


def test_chat_completions_request_and_nested_responses_output_are_supported() -> None:
    bodies: list[dict[str, object]] = []

    def chat_handler(incoming: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(incoming.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(MODEL_OUTPUT)}}]},
        )

    chat = OpenAICompatibleClient(
        settings(model_api_style="chat_completions"),
        transport=httpx.MockTransport(chat_handler),
    )
    assert chat.analyze(request()).root_causes[0].confidence == 0.9
    response_format = cast(dict[str, Any], bodies[0]["response_format"])
    json_schema = cast(dict[str, Any], response_format["json_schema"])
    assert json_schema["strict"] is True

    nested = OpenAICompatibleClient(
        settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "output": [
                        {"content": [{"type": "output_text", "text": json.dumps(MODEL_OUTPUT)}]}
                    ]
                },
            )
        ),
    )
    assert nested.analyze(request()).root_causes[0].rank == 1


def test_client_errors_do_not_expose_response_body_or_api_key() -> None:
    client = OpenAICompatibleClient(
        settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, text="top-secret-key provider detail")
        ),
    )
    with pytest.raises(ModelClientError) as caught:
        client.analyze(request())
    assert str(caught.value) == "model request failed with HTTP 401"

    malformed = OpenAICompatibleClient(
        settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"output_text": "{}"})),
    )
    with pytest.raises(ModelClientError, match="invalid structured response"):
        malformed.analyze(request())


def test_live_client_requires_model_and_api_key() -> None:
    with pytest.raises(ModelClientError, match="MODEL_NAME"):
        OpenAICompatibleClient(settings(model_name=""))
    with pytest.raises(ModelClientError, match="API_KEY"):
        OpenAICompatibleClient(settings(model_api_key=None))
