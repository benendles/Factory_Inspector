"""Conservative repair diagnosis from inspected, simulated evidence."""

from __future__ import annotations

import json
import os
from typing import Any

from app.services.amd_token_factory import AMDTokenFactory


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


class RepairDiagnosisService:
    """Create a preliminary diagnosis without asserting a component failure.

    The deterministic baseline is always retained.  An opt-in AMD text-model
    pass may add carefully validated hypotheses, but it cannot establish a
    defect, fitment, replacement justification, cost, or maintenance approval.
    """

    def __init__(
        self,
        *,
        model_client: Any | None = None,
        model_enabled: bool | None = None,
    ) -> None:
        self._model_client = model_client
        self._model_enabled = (
            _env_flag("AMD_REPAIR_DIAGNOSIS_ENABLED")
            if model_enabled is None
            else model_enabled
        )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _text(value: Any, maximum: int = 600) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        return normalized[:maximum] or None

    @classmethod
    def _sensor_findings(cls, state: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        analysis = cls._as_dict(state.get("sensor_analysis"))
        for anomaly in analysis.get("anomalies", []):
            item = cls._as_dict(anomaly)
            sensor = cls._text(item.get("sensor"), 80)
            value = item.get("value")
            threshold = item.get("threshold")
            if sensor and value is not None and threshold is not None:
                findings.append(
                    f"Simulated {sensor} reading {value} exceeds configured threshold {threshold}."
                )
        return findings

    @classmethod
    def _observation_findings(cls, state: dict[str, Any]) -> list[str]:
        inspection = cls._as_dict(
            state.get("image_inspection_result") or state.get("vision_analysis")
        )
        findings: list[str] = []
        for observation in inspection.get("observations", []):
            if isinstance(observation, str):
                text = cls._text(observation)
            else:
                item = cls._as_dict(observation)
                text = cls._text(
                    item.get("description") or item.get("observation")
                )
            if text:
                findings.append(text)
        return findings

    @classmethod
    def _model_hypotheses(
        cls,
        content: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int | str]]:
        """Accept only concise, non-binding JSON hypotheses from the model."""

        metadata: dict[str, int | str] = {
            "response_format": "invalid",
            "hypotheses_proposed": 0,
            "hypotheses_accepted": 0,
            "actions_proposed": 0,
            "actions_accepted": 0,
        }
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return [], [], metadata

        if not isinstance(payload, dict):
            return [], [], metadata

        metadata["response_format"] = "valid"

        causes: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        raw_causes = payload.get("possible_causes", [])
        if not isinstance(raw_causes, list):
            raw_causes = []

        for item in raw_causes:
            item_data = cls._as_dict(item)
            cause = cls._text(item_data.get("cause"), 180)
            if cause:
                metadata["hypotheses_proposed"] = int(
                    metadata["hypotheses_proposed"]
                ) + 1
            if cause and cls._is_safe_hypothesis(cause) and len(causes) < 3:
                causes.append({
                    "cause": cause,
                    "evidence": [],
                    "confirmation_required": True,
                    "source": "amd_model_hypothesis",
                })

        raw_actions = payload.get("recommended_actions", [])
        if not isinstance(raw_actions, list):
            raw_actions = []

        for item in raw_actions:
            item_data = cls._as_dict(item)
            action = cls._text(item_data.get("action"), 180)
            if action:
                metadata["actions_proposed"] = int(
                    metadata["actions_proposed"]
                ) + 1
            if action and cls._is_safe_inspection_action(action) and len(actions) < 3:
                actions.append({
                    "action": action,
                    "action_type": "inspection",
                    "priority": "medium",
                    "requires_qualified_technician": True,
                    "source": "amd_model_hypothesis",
                })

        metadata["hypotheses_accepted"] = len(causes)
        metadata["actions_accepted"] = len(actions)
        return causes, actions, metadata

    @staticmethod
    def _is_safe_hypothesis(value: str) -> bool:
        """Reject model output that tries to introduce procurement claims."""

        normalized = value.casefold()
        prohibited = (
            "price",
            "cost",
            "supplier",
            "quote",
            "purchase",
            "order",
            "part number",
        )
        return not any(term in normalized for term in prohibited)

    @staticmethod
    def _is_safe_inspection_action(value: str) -> bool:
        """Only retain technician inspection actions from model output."""

        normalized = value.casefold().lstrip()
        allowed_prefixes = (
            "inspect",
            "test",
            "measure",
            "verify",
            "assess",
            "check",
            "review",
        )
        prohibited = (
            "replace",
            "purchase",
            "order",
            "quote",
            "price",
            "cost",
            "supplier",
        )
        return (
            normalized.startswith(allowed_prefixes)
            and not any(term in normalized for term in prohibited)
        )

    @classmethod
    def _prompt(cls, diagnosis: dict[str, Any], equipment: dict[str, Any]) -> str:
        return (
            "You are assisting a factory technician. Return JSON only with "
            "possible_causes and recommended_actions. Every cause must be a "
            "hypothesis, never a confirmed failure. Every action must be an "
            "inspection action; do not name parts, prices, suppliers, repair "
            "authorization, or replacement recommendations.\n"
            f"Verified equipment context: {json.dumps(equipment, default=str)}\n"
            f"Observed/simulated evidence: {json.dumps(diagnosis['confirmed_findings'])}"
        )

    def diagnose(self, state: dict[str, Any]) -> dict[str, Any]:
        registry_match = self._as_dict(state.get("registry_match"))
        equipment = self._as_dict(registry_match.get("candidate"))
        sensor_findings = self._sensor_findings(state)
        observation_findings = self._observation_findings(state)
        confirmed_findings = sensor_findings + observation_findings

        temperature_issue = any(
            "temperature" in finding.casefold()
            for finding in sensor_findings
        )
        contamination = any(
            term in finding.casefold()
            for finding in observation_findings
            for term in ("dust", "contamination", "grime", "cooling fin")
        )

        causes: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        if temperature_issue or contamination:
            evidence = observation_findings[:2] if contamination else sensor_findings[:1]
            causes.append({
                "cause": "Restricted cooling airflow",
                "evidence": evidence,
                "confirmation_required": True,
                "source": "evidence_grounded_rule",
            })
            actions.append({
                "action": "Inspect cooling fins, airflow, and guards.",
                "action_type": "inspection",
                "priority": "high" if temperature_issue else "medium",
                "requires_qualified_technician": True,
                "source": "evidence_grounded_rule",
            })
        if temperature_issue:
            causes.append({
                "cause": "Cooling fan or related cooling component malfunction",
                "evidence": [],
                "confirmation_required": True,
                "source": "evidence_grounded_rule",
            })

        diagnosis: dict[str, Any] = {
            "diagnosis_status": "preliminary",
            "provider": "evidence_grounded_rules",
            "confirmed_findings": confirmed_findings,
            "possible_causes": causes,
            "recommended_actions": actions,
            "replacement_justified": False,
            "requires_technician_review": True,
            "amd_enrichment": {
                "status": "disabled",
                "response_format": "not_requested",
                "hypotheses_proposed": 0,
                "hypotheses_accepted": 0,
                "actions_proposed": 0,
                "actions_accepted": 0,
            },
            "limitations": [
                "The diagnosis distinguishes simulated readings and visual observations from technician-confirmed defects.",
                "No component failure or replacement need has been established.",
            ],
        }

        if not self._model_enabled:
            diagnosis["limitations"].append(
                "AMD diagnosis enrichment is disabled."
            )
            return diagnosis

        try:
            client = self._model_client or AMDTokenFactory()
            model_causes, model_actions, model_metadata = self._model_hypotheses(
                client.chat(self._prompt(diagnosis, equipment))
            )
        except Exception:
            diagnosis["amd_enrichment"] = {
                "status": "unavailable",
                "response_format": "not_available",
                "hypotheses_proposed": 0,
                "hypotheses_accepted": 0,
                "actions_proposed": 0,
                "actions_accepted": 0,
            }
            diagnosis["limitations"].append(
                "AMD diagnosis enrichment was unavailable; the evidence-grounded preliminary diagnosis was retained."
            )
            return diagnosis

        if model_causes:
            diagnosis["possible_causes"].extend(model_causes)
        if model_actions:
            diagnosis["recommended_actions"].extend(model_actions)
        diagnosis["amd_enrichment"] = {
            "status": "completed",
            **model_metadata,
        }
        if model_causes or model_actions:
            diagnosis["provider"] = (
                "evidence_grounded_rules_with_amd_hypotheses"
            )
        else:
            diagnosis["provider"] = "evidence_grounded_rules_with_amd_reviewed"
        return diagnosis
