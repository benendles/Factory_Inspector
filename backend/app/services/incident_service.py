from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass
class Incident:
    incident_id: str
    machine_id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    visual_evidence: list[dict[str, Any]] = field(default_factory=list)
    sensor_evidence: list[dict[str, Any]] = field(default_factory=list)
    requires_human_review: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class IncidentService:
    """
    Create and manage factory incidents.

    This version uses in-memory storage. Incidents will be lost when
    the application restarts. Database persistence will be added later.
    """

    def __init__(self):
        self._incidents: dict[str, Incident] = {}

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        """Convert a Pydantic model, dataclass, or dictionary to a dictionary."""

        if isinstance(value, dict):
            return value

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        if hasattr(value, "__dataclass_fields__"):
            from dataclasses import asdict

            return asdict(value)

        raise TypeError(
            f"Unsupported evidence type: {type(value).__name__}"
        )

    @staticmethod
    def _get_severity(
        sensor_evidence: list[dict[str, Any]],
        visual_evidence: list[dict[str, Any]],
    ) -> IncidentSeverity:
        """Determine incident severity from the available evidence."""

        # Sensor severity uses deterministic rules.
        sensor_severities = [
            str(item.get("severity", "")).lower()
            for item in sensor_evidence
        ]

        if "critical" in sensor_severities:
            return IncidentSeverity.CRITICAL

        if "high" in sensor_severities:
            return IncidentSeverity.HIGH

        if "medium" in sensor_severities:
            return IncidentSeverity.MEDIUM

        if "low" in sensor_severities:
            return IncidentSeverity.LOW

        # Visual confidence is not a calibrated severity score.
        # Do not treat a model's confidence alone as incident severity.
        if visual_evidence:
            return IncidentSeverity.MEDIUM

        return IncidentSeverity.LOW

    @staticmethod
    def _build_title(
        visual_evidence: list[dict[str, Any]],
        sensor_evidence: list[dict[str, Any]],
    ) -> str:
        """Generate a short incident title."""

        if visual_evidence and sensor_evidence:
            return "Factory anomaly detected: visual and sensor evidence"

        if visual_evidence:
            anomaly_type = visual_evidence[0].get(
                "anomaly_type", "visual anomaly"
            )
            return f"Visual anomaly detected: {anomaly_type}"

        if sensor_evidence:
            sensor = sensor_evidence[0].get("sensor", "sensor")
            return f"Sensor anomaly detected: {sensor}"

        return "Factory inspection requires review"

    @staticmethod
    def _build_description(
        visual_evidence: list[dict[str, Any]],
        sensor_evidence: list[dict[str, Any]],
    ) -> str:
        """Summarize the evidence without inventing a diagnosis."""

        descriptions = []

        for item in visual_evidence:
            description = item.get("description")
            if description:
                descriptions.append(f"Visual observation: {description}")

        for item in sensor_evidence:
            description = item.get("description")
            if description:
                descriptions.append(f"Sensor observation: {description}")

        if not descriptions:
            return "An inspection requires human review."

        return " ".join(descriptions)

    def create_incident(
        self,
        machine_id: str,
        visual_evidence: list[Any] | None = None,
        sensor_evidence: list[Any] | None = None,
        requires_human_review: bool = True,
    ) -> Incident:
        """
        Create an incident from visual and sensor evidence.

        Reuses an existing active incident when the same machine has
        matching evidence. Resolved and escalated incidents are not
        considered active for deduplication.
        """

        if not machine_id or not machine_id.strip():
            raise ValueError("machine_id cannot be empty.")

        visual = [
            self._to_dict(item) for item in (visual_evidence or [])
        ]
        sensors = [
            self._to_dict(item) for item in (sensor_evidence or [])
        ]

        if not visual and not sensors:
            raise ValueError(
                "Cannot create an incident without visual or sensor evidence."
            )

        # Require evidence to belong to the machine being inspected.
        for item in visual:
            evidence_machine = item.get("machine_id")
            if evidence_machine and evidence_machine != machine_id:
                raise ValueError(
                    "Visual evidence machine_id does not match the incident."
                )

        for item in sensors:
            evidence_machine = item.get("machine_id")
            if evidence_machine and evidence_machine != machine_id:
                raise ValueError(
                    "Sensor evidence machine_id does not match the incident."
                )

        # A simple deduplication key: same machine and same evidence types.
        # We will improve this later to track individual anomaly fingerprints.
        evidence_key = (
            machine_id,
            tuple(sorted(
                str(item.get("anomaly_type", item.get("sensor", "unknown")))
                for item in visual + sensors
            )),
        )

        for existing in self._incidents.values():
            if existing.machine_id != machine_id:
                continue

            if existing.status in {
                IncidentStatus.RESOLVED,
                IncidentStatus.ESCALATED,
            }:
                continue

            existing_key = (
                existing.machine_id,
                tuple(sorted(
                    str(item.get("anomaly_type", item.get("sensor", "unknown")))
                    for item in (
                        existing.visual_evidence + existing.sensor_evidence
                    )
                )),
            )

            if existing_key == evidence_key:
                # Update timestamps and retain newly received evidence.
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                existing.requires_human_review = (
                    existing.requires_human_review or requires_human_review
                )
                existing.visual_evidence = visual
                existing.sensor_evidence = sensors
                existing.severity = self._get_severity(visual, sensors)
                existing.description = self._build_description(visual, sensors)
                existing.title = self._build_title(visual, sensors)
                return existing

        incident = Incident(
            incident_id=f"INC-{uuid4().hex[:8].upper()}",
            machine_id=machine_id,
            title=self._build_title(visual, sensors),
            description=self._build_description(visual, sensors),
            severity=self._get_severity(sensors, visual),
            status=IncidentStatus.OPEN,
            visual_evidence=visual,
            sensor_evidence=sensors,
            requires_human_review=requires_human_review,
        )

        self._incidents[incident.incident_id] = incident
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        """Retrieve an incident by ID."""

        return self._incidents.get(incident_id)

    def list_incidents(self) -> list[Incident]:
        """Return all incidents, newest first."""

        return sorted(
            self._incidents.values(),
            key=lambda incident: incident.created_at,
            reverse=True,
        )

    def update_status(
        self,
        incident_id: str,
        status: IncidentStatus,
    ) -> Incident:
        """Update an incident's lifecycle status."""

        incident = self.get_incident(incident_id)

        if incident is None:
            raise ValueError(f"Incident not found: {incident_id}")

        incident.status = status
        incident.updated_at = datetime.now(timezone.utc).isoformat()

        return incident