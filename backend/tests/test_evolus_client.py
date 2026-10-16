"""Unit tests for the Evolus client; all HTTP requests use MockTransport."""

import asyncio
import json

import httpx
import pytest

from app.services.evolus_client import (
    EvolusClient,
    EvolusConfigurationError,
    EvolusRateLimitError,
    EvolusRequestError,
)


AGENT_ID = "380292fc-e07d-49c7-8b49-867c6a75ea43"


def run(coroutine):
    return asyncio.run(coroutine)


def client(handler) -> EvolusClient:
    return EvolusClient(
        base_url="https://evolus.example",
        api_key="test-key",
        application_id="test-application",
        agent_id=AGENT_ID,
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )


def assessment(**overrides):
    return {
        "incident_id": "FI-DEMO-001",
        "equipment_id": "HACKATHON-SIEMENS-001",
        "severity": "critical",
        "observed_evidence": ["Simulated temperature 95 C"],
        "possible_causes": ["Restricted cooling airflow"],
        "recommended_actions": ["Inspect cooling paths"],
        "required_parts": [],
        "safety_precautions": ["Use qualified technicians"],
        "human_approval_required": False,
        "next_steps": ["Await human review"],
        **overrides,
    }


def test_environment_configuration_requires_all_values(monkeypatch):
    monkeypatch.setenv("EVOLUS_ENABLED", "true")
    for name in (
        "EVOLUS_BASE_URL",
        "EVOLUS_API_KEY",
        "EVOLUS_APPLICATION_ID",
        "EVOLUS_AGENT_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(EvolusConfigurationError, match="EVOLUS_API_KEY"):
        EvolusClient.from_environment()


def test_get_agent_verifies_configured_identity():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/api/v1/agents/{AGENT_ID}"
        assert request.headers["X-ApiKey"] == "test-key"
        return httpx.Response(200, json={"agentId": AGENT_ID, "name": "Digital Maintenance Foreman"})

    result = run(client(handler).get_agent())

    assert result["agentId"] == AGENT_ID


def test_connection_uses_read_only_agent_lookup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"agentId": AGENT_ID, "name": "Digital Maintenance Foreman"})

    result = run(client(handler).test_connection())

    assert result == {
        "status": "connected",
        "agent_id": AGENT_ID,
        "agent_name": "Digital Maintenance Foreman",
    }


def test_ask_uses_documented_post_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/api/v1/agents/{AGENT_ID}/ask"
        assert json.loads(request.content) == {
            "content": "Hello Digital Maintenance Foreman.",
            "skipChatHistory": True,
        }
        return httpx.Response(200, json={"answer": "Acknowledged.", "agentId": AGENT_ID})

    response = run(client(handler).ask_agent("Hello Digital Maintenance Foreman."))

    assert response.answer == "Acknowledged."


@pytest.mark.parametrize("status_code", [401, 405, 422, 500])
def test_http_errors_are_preserved_without_leaking_request_data(status_code):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"title": "Remote failure"})

    with pytest.raises(EvolusRequestError) as raised:
        run(client(handler).ask_agent("diagnostic"))

    assert raised.value.status_code == status_code
    assert "test-key" not in str(raised.value)


def test_rate_limit_surfaces_retry_after_without_replaying_the_ask_request():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "17"})

    with pytest.raises(EvolusRateLimitError) as raised:
        run(client(handler).ask_agent("diagnostic"))

    assert raised.value.retry_after_seconds == 17
    assert calls == 1


def test_timeout_is_safe_and_does_not_retry():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow provider")

    with pytest.raises(EvolusRequestError, match="timed out"):
        run(client(handler).ask_agent("diagnostic"))

    assert calls == 1


def test_incident_prompt_forbids_external_retrieval():
    prompt = EvolusClient._incident_prompt({"incident_id": "FI-DEMO-001"})

    assert "Do not retrieve documents, browse, call tools" in prompt
    assert "Use only the evidence in this prompt." in prompt
    assert '"incident_id": "FI-DEMO-001"' in prompt


def test_incident_analysis_validates_fenced_json_and_enforces_human_approval():
    answer = "```json\n" + json.dumps(assessment()) + "\n```"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": answer, "agentId": AGENT_ID, "conversationId": "conversation-1"})

    result = run(client(handler).analyze_incident({"incident_id": "FI-DEMO-001"}))

    assert result["status"] == "completed"
    assert result["assessment"]["human_approval_required"] is True
    assert result["assessment"]["safety_certified"] is False
    assert result["conversation_id"] == "conversation-1"


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        json.dumps(assessment(next_steps=None)),
        json.dumps({"incident_id": "FI-DEMO-001"}),
    ],
)
def test_malformed_or_incomplete_model_json_is_not_promoted(answer):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": answer, "agentId": AGENT_ID})

    result = run(client(handler).analyze_incident({"incident_id": "FI-DEMO-001"}))

    assert result["status"] == "invalid_assessment"
    assert result["assessment"] is None
    assert result["requires_human_approval"] is True
    assert result["safety_certified"] is False
