"""Safe, advisory-only client for the Evolus Digital Maintenance Foreman.

The client intentionally has no access to Factory Inspector state mutation,
maintenance approval, execution, or safety certification.  It only returns a
validated recommendation that the workflow can present to a human reviewer.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import PROJECT_ROOT


# The FastAPI application imports app.config during startup. Loading here too
# keeps this focused client usable in a worker, script, or graph unit test.
load_dotenv(PROJECT_ROOT / ".env")


class EvolusConfigurationError(ValueError):
    """Raised when the required Evolus environment settings are absent."""


class EvolusRequestError(RuntimeError):
    """A safe remote-service failure that never contains credentials."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class EvolusRateLimitError(EvolusRequestError):
    """Raised for 429 responses without retrying a conversation request."""


class EvolusAgentResponse(BaseModel):
    """The documented response envelope returned by ``/agents/{id}/ask``."""

    model_config = ConfigDict(extra="ignore")

    question: str | None = None
    answer: str = Field(min_length=1)
    title: str | None = None
    citations: list[Any] = Field(default_factory=list)
    agent_id: str | None = Field(default=None, alias="agentId")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    total_token_count: int | None = Field(default=None, alias="totalTokenCount")


AssessmentValue = str | dict[str, Any]


class EvolusMaintenanceAssessment(BaseModel):
    """Strict advisory payload accepted from the agent response."""

    model_config = ConfigDict(extra="ignore")

    incident_id: str = Field(min_length=1)
    equipment_id: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    observed_evidence: list[AssessmentValue]
    possible_causes: list[AssessmentValue]
    recommended_actions: list[AssessmentValue]
    required_parts: list[AssessmentValue]
    safety_precautions: list[AssessmentValue]
    human_approval_required: bool = True
    next_steps: list[AssessmentValue]

    @field_validator("incident_id", "equipment_id", "severity")
    @classmethod
    def _non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    def advisory_dump(self) -> dict[str, Any]:
        """Apply Factory Inspector policy after validating the AI response."""

        data = self.model_dump(mode="json")
        # This policy is owned by the backend, never by the agent response.
        data["human_approval_required"] = True
        data["safety_certified"] = False
        return data


class EvolusClient:
    """Asynchronous Evolus API client with bounded, non-mutating requests."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        application_id: str,
        agent_id: str,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        required = {
            "EVOLUS_BASE_URL": base_url,
            "EVOLUS_API_KEY": api_key,
            "EVOLUS_APPLICATION_ID": application_id,
            "EVOLUS_AGENT_ID": agent_id,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise EvolusConfigurationError(
                "Missing Evolus configuration: " + ", ".join(missing)
            )

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.application_id = application_id
        self.agent_id = agent_id
        self.timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0))
        self.transport = transport

    @classmethod
    def from_environment(cls) -> "EvolusClient":
        """Build a client from root ``.env`` values loaded by app config."""

        enabled = os.getenv("EVOLUS_ENABLED", "true").strip().casefold()
        if enabled in {"0", "false", "no", "off"}:
            raise EvolusConfigurationError("The Evolus integration is disabled.")

        try:
            timeout_seconds = float(os.getenv("EVOLUS_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise EvolusConfigurationError(
                "EVOLUS_TIMEOUT_SECONDS must be a number."
            ) from exc

        return cls(
            base_url=os.getenv("EVOLUS_BASE_URL", "https://api.evolus.ai"),
            api_key=os.getenv("EVOLUS_API_KEY", ""),
            application_id=os.getenv("EVOLUS_APPLICATION_ID", ""),
            agent_id=os.getenv("EVOLUS_AGENT_ID", ""),
            timeout_seconds=timeout_seconds,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-ApiKey": self.api_key,
            "X-Application-Id": self.application_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            seconds = int(value)
            return max(seconds, 0)
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
            except (TypeError, ValueError, IndexError, OverflowError):
                return None

    @staticmethod
    def _safe_detail(response: httpx.Response) -> str:
        """Keep errors useful without logging headers, tokens, or huge bodies."""

        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("title") or body.get("errorCode")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()[:300]
        return f"Evolus returned HTTP {response.status_code}."

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue one request; POST requests are never automatically retried."""

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, json=payload)
        except httpx.TimeoutException as exc:
            raise EvolusRequestError(
                "The Evolus request timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise EvolusRequestError(
                "The Evolus service could not be reached.",
            ) from exc

        if response.status_code == 429:
            raise EvolusRateLimitError(
                "Evolus rate limited the request.",
                status_code=429,
                retry_after_seconds=self._retry_after(response),
            )
        if not response.is_success:
            raise EvolusRequestError(
                self._safe_detail(response),
                status_code=response.status_code,
            )
        return response

    async def get_agent(self) -> dict[str, Any]:
        """Retrieve the configured agent and verify that it is the target agent."""

        response = await self._request("GET", f"/api/v1/agents/{self.agent_id}")
        try:
            data = response.json()
        except ValueError as exc:
            raise EvolusRequestError("Evolus returned invalid agent JSON.") from exc
        if not isinstance(data, dict):
            raise EvolusRequestError("Evolus returned an invalid agent payload.")
        if str(data.get("agentId")) != self.agent_id:
            raise EvolusRequestError("Evolus returned a different agent identity.")
        return data

    async def test_connection(self) -> dict[str, Any]:
        """Perform a read-only authentication and configured-agent check."""

        agent = await self.get_agent()
        return {
            "status": "connected",
            "agent_id": agent.get("agentId"),
            "agent_name": agent.get("name"),
        }

    async def ask_agent(
        self,
        content: str,
        conversation_id: str | None = None,
    ) -> EvolusAgentResponse:
        """Ask the configured agent a single question without retries."""

        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        payload: dict[str, Any] = {
            "content": content,
            "skipChatHistory": conversation_id is None,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id

        response = await self._request(
            "POST",
            f"/api/v1/agents/{self.agent_id}/ask",
            payload=payload,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise EvolusRequestError("Evolus returned invalid response JSON.") from exc
        try:
            result = EvolusAgentResponse.model_validate(data)
        except ValidationError as exc:
            raise EvolusRequestError("Evolus returned an incomplete agent response.") from exc
        if result.agent_id and result.agent_id != self.agent_id:
            raise EvolusRequestError("Evolus response agent ID did not match configuration.")
        return result

    @staticmethod
    def _json_from_answer(answer: str) -> dict[str, Any] | None:
        """Parse a JSON object from plain text or a Markdown JSON fence."""

        candidates = [answer.strip()]
        candidates.extend(
            match.group(1).strip()
            for match in re.finditer(r"```(?:json)?\s*(.*?)```", answer, re.IGNORECASE | re.DOTALL)
        )
        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            for start, character in enumerate(candidate):
                if character != "{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(candidate[start:])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return None

    @staticmethod
    def _looks_like_refusal(answer: str) -> bool:
        normalized = answer.casefold()
        return any(
            phrase in normalized
            for phrase in ("cannot assist", "can't assist", "unable to assist", "i must refuse")
        )

    @staticmethod
    def _incident_prompt(incident: dict[str, Any]) -> str:
        payload = json.dumps(incident, ensure_ascii=False, default=str)
        return (
            "You are the advisory Digital Maintenance Foreman for a simulated "
            "Factory Inspector workflow. Analyze only the supplied evidence. "
            "Do not retrieve documents, browse, call tools, or wait for external "
            "information. Use only the evidence in this prompt. "
            "Do not claim a physical repair, verified compatibility, approval, "
            "or safety certification. Return one JSON object only, with exactly "
            "these fields: incident_id, equipment_id, severity, observed_evidence, "
            "possible_causes, recommended_actions, required_parts, "
            "safety_precautions, human_approval_required, next_steps. "
            "All list fields must be arrays. human_approval_required must be true. "
            "Use only the source-labelled observed_evidence from this prompt. "
            "AMD Vision equipment_identification_candidate and nameplate OCR "
            "fields are unverified candidates, not physical identity proof. "
            "A SQL registry candidate is also not physical identity proof. "
            "Keep observed_evidence factual and separate every unconfirmed "
            "cause or action as a hypothesis/recommendation; never present a "
            "hypothesis as an observed fact. "
            "Unknown parts, prices, availability, or fitment must be identified as "
            "unverified rather than invented.\n\n"
            f"Factory Inspector evidence:\n{payload}"
        )

    async def analyze_incident(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Return a validated advisory assessment without mutating an incident."""

        try:
            response = await self.ask_agent(self._incident_prompt(incident))
        except EvolusRateLimitError as exc:
            return {
                "status": "rate_limited",
                "assessment": None,
                "raw_answer": None,
                "requires_human_approval": True,
                "safety_certified": False,
                "retry_after_seconds": exc.retry_after_seconds,
                "limitations": ["Evolus research is temporarily rate limited."],
            }
        except EvolusRequestError as exc:
            return {
                "status": "unavailable",
                "assessment": None,
                "raw_answer": None,
                "requires_human_approval": True,
                "safety_certified": False,
                "limitations": [str(exc)],
            }

        raw_answer = response.answer[:12_000]
        if self._looks_like_refusal(raw_answer):
            return {
                "status": "refused",
                "assessment": None,
                "raw_answer": raw_answer,
                "conversation_id": response.conversation_id,
                "requires_human_approval": True,
                "safety_certified": False,
                "limitations": ["Evolus did not provide a maintenance assessment."],
            }

        parsed = self._json_from_answer(raw_answer)
        if parsed is None:
            return {
                "status": "invalid_assessment",
                "assessment": None,
                "raw_answer": raw_answer,
                "conversation_id": response.conversation_id,
                "requires_human_approval": True,
                "safety_certified": False,
                "limitations": ["Evolus response did not contain a JSON assessment."],
            }

        try:
            assessment = EvolusMaintenanceAssessment.model_validate(parsed)
        except ValidationError as exc:
            missing_or_invalid = [".".join(str(item) for item in error["loc"]) for error in exc.errors()]
            return {
                "status": "invalid_assessment",
                "assessment": None,
                "raw_answer": raw_answer,
                "conversation_id": response.conversation_id,
                "requires_human_approval": True,
                "safety_certified": False,
                "limitations": [
                    "Evolus response did not satisfy the maintenance assessment schema: "
                    + ", ".join(missing_or_invalid[:8])
                ],
            }

        return {
            "status": "completed",
            "assessment": assessment.advisory_dump(),
            "raw_answer": raw_answer,
            "conversation_id": response.conversation_id,
            "agent_id": response.agent_id or self.agent_id,
            "requires_human_approval": True,
            "safety_certified": False,
            "limitations": [
                "Evolus output is an advisory recommendation and cannot approve maintenance or certify physical safety."
            ],
        }
