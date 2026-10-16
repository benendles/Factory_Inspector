from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.services.incident_service import (
    Incident,
    IncidentSeverity,
)


class MaintenanceStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class MaintenanceRecommendation:
    """A recommended action for addressing a factory incident."""

    action: str
    reason: str
    priority: str
    requires_qualified_technician: bool = True


@dataclass
class MaintenanceTask:
    """A proposed maintenance task associated with an incident."""

    task_id: str
    incident_id: str
    machine_id: str
    title: str
    problem: str
    severity: str
    recommended_actions: list[MaintenanceRecommendation]
    status: MaintenanceStatus = MaintenanceStatus.PENDING_APPROVAL
    requires_human_approval: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MaintenanceService:
    """
    Create and manage maintenance recommendations.

    This initial implementation uses in-memory storage.
    It does not execute physical maintenance or create real
    work orders in an external maintenance system.
    """

    def __init__(self):
        self._tasks: dict[str, MaintenanceTask] = {}

    @staticmethod
    def _get_recommendations(
        incident: Incident,
    ) -> list[MaintenanceRecommendation]:
        """Generate recommendations from the incident's evidence."""

        recommendations = []

        severity = incident.severity

        # Critical incidents require prompt human assessment.
        if severity == IncidentSeverity.CRITICAL:
            recommendations.append(
                MaintenanceRecommendation(
                    action=(
                        "Request immediate assessment by qualified "
                        "site safety and maintenance personnel."
                    ),
                    reason=(
                        "The incident is classified as critical. "
                        "The actual hazard and appropriate response "
                        "must be assessed by qualified personnel."
                    ),
                    priority="critical",
                )
            )

        # Analyze visual evidence.
        for observation in incident.visual_evidence:
            anomaly_type = str(
                observation.get("anomaly_type", "")
            ).lower()

            if anomaly_type in {
                "structural_deformation",
                "structural_damage",
                "collapse",
            }:
                recommendations.append(
                    MaintenanceRecommendation(
                        action=(
                            "Restrict access to the potentially affected "
                            "area and request a qualified structural "
                            "assessment before re-entry."
                        ),
                        reason=(
                            "Visual inspection reported possible "
                            "structural damage."
                        ),
                        priority="critical",
                    )
                )

            elif anomaly_type in {
                "smoke",
                "fire",
                "sparking",
            }:
                recommendations.append(
                    MaintenanceRecommendation(
                        action=(
                            "Follow the site's emergency response "
                            "procedure and have qualified personnel "
                            "assess the hazard."
                        ),
                        reason=(
                            "Visual inspection reported a potential "
                            "fire or electrical hazard."
                        ),
                        priority="critical",
                    )
                )

            else:
                recommendations.append(
                    MaintenanceRecommendation(
                        action=(
                            "Have a qualified technician inspect the "
                            "reported visual anomaly."
                        ),
                        reason=(
                            "Visual inspection reported: "
                            f"{observation.get('description', anomaly_type)}"
                        ),
                        priority="high",
                    )
                )

        # Analyze sensor evidence.
        for observation in incident.sensor_evidence:
            sensor = str(
                observation.get("sensor", "unknown")
            ).lower()

            value = observation.get("value")
            unit = observation.get("unit", "")

            description = observation.get(
                "description",
                "An abnormal sensor reading was reported.",
            )

            if sensor == "temperature":
                action = (
                    "Have a qualified technician inspect the machine's "
                    "thermal conditions and review its operating limits."
                )

            elif sensor == "vibration":
                action = (
                    "Have a qualified technician inspect vibration trends "
                    "and check relevant components according to the "
                    "manufacturer's maintenance procedure."
                )

            elif sensor == "pressure":
                action = (
                    "Have qualified personnel verify the pressure reading "
                    "and inspect the system against its specified "
                    "operating limits."
                )

            elif sensor == "moisture":
                action = (
                    "Verify the moisture reading and inspect the relevant "
                    "area for conditions consistent with the measurement."
                )

            else:
                action = (
                    "Verify the sensor reading and have qualified personnel "
                    "investigate the reported abnormal condition."
                )

            recommendations.append(
                MaintenanceRecommendation(
                    action=action,
                    reason=(
                        f"{description} Reported value: {value} {unit}."
                    ),
                    priority=(
                        "critical"
                        if str(
                            observation.get("severity", "")
                        ).lower() == "critical"
                        else "high"
                    ),
                )
            )

        # Provide a safe fallback if evidence is incomplete.
        if not recommendations:
            recommendations.append(
                MaintenanceRecommendation(
                    action=(
                        "Review the incident evidence and determine "
                        "whether a maintenance inspection is required."
                    ),
                    reason=(
                        "No specific actionable observation was available."
                    ),
                    priority="medium",
                )
            )

        return recommendations

    def create_task(self, incident: Incident) -> MaintenanceTask:
        """
        Create a maintenance task from an incident.

        Creating a task records a recommendation. It does not
        authorize or execute physical maintenance.
        """

        if not incident.incident_id:
            raise ValueError("Incident must have an incident_id.")

        if not incident.machine_id:
            raise ValueError("Incident must have a machine_id.")

        # Prevent duplicate tasks for the same incident.
        for task in self._tasks.values():
            if task.incident_id == incident.incident_id:
                return task

        recommendations = self._get_recommendations(incident)

        task = MaintenanceTask(
            task_id=f"MT-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            machine_id=incident.machine_id,
            title=f"Maintenance investigation: {incident.title}",
            problem=incident.description,
            severity=incident.severity.value,
            recommended_actions=recommendations,
        )

        self._tasks[task.task_id] = task

        return task

    def get_task(self, task_id: str) -> MaintenanceTask | None:
        """Retrieve a maintenance task by its ID."""

        return self._tasks.get(task_id)

    def restore_task(self, payload: dict[str, object]) -> MaintenanceTask:
        """Rehydrate a checkpointed task without bypassing status rules."""

        task_id = str(payload.get("task_id") or "")
        if not task_id:
            raise ValueError("Cannot restore a maintenance task without task_id.")

        existing = self._tasks.get(task_id)
        if existing is not None:
            return existing

        try:
            task_status = MaintenanceStatus(
                str(payload.get("status") or MaintenanceStatus.PENDING_APPROVAL.value)
            )
        except ValueError as exc:
            raise ValueError("Checkpointed task has an invalid status.") from exc

        recommendations: list[MaintenanceRecommendation] = []
        raw_recommendations = payload.get("recommended_actions") or []
        if not isinstance(raw_recommendations, list):
            raise ValueError("Checkpointed task recommendations must be a list.")

        for item in raw_recommendations:
            if not isinstance(item, dict):
                continue
            action = item.get("action")
            if not isinstance(action, str) or not action:
                continue
            recommendations.append(
                MaintenanceRecommendation(
                    action=action,
                    reason=str(item.get("reason") or action),
                    priority=str(item.get("priority") or "medium"),
                    requires_qualified_technician=bool(
                        item.get("requires_qualified_technician", True)
                    ),
                )
            )

        task = MaintenanceTask(
            task_id=task_id,
            incident_id=str(payload.get("incident_id") or ""),
            machine_id=str(payload.get("machine_id") or ""),
            title=str(payload.get("title") or "Maintenance investigation"),
            problem=str(payload.get("problem") or ""),
            severity=str(payload.get("severity") or "medium"),
            recommended_actions=recommendations,
            status=task_status,
            requires_human_approval=bool(
                payload.get("requires_human_approval", True)
            ),
            created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(payload.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )
        self._tasks[task_id] = task
        return task

    def list_tasks(self) -> list[MaintenanceTask]:
        """Return maintenance tasks, newest first."""

        return sorted(
            self._tasks.values(),
            key=lambda task: task.created_at,
            reverse=True,
        )

    def update_status(
        self,
        task_id: str,
        status: MaintenanceStatus,
    ) -> MaintenanceTask:
        """
        Update a task's status while enforcing valid transitions.

        Workflow:
            PENDING_APPROVAL -> APPROVED
            PENDING_APPROVAL -> REJECTED
            PENDING_APPROVAL -> CANCELLED
            APPROVED -> IN_PROGRESS
            APPROVED -> CANCELLED
            IN_PROGRESS -> COMPLETED
            IN_PROGRESS -> CANCELLED
        """

        task = self.get_task(task_id)

        if task is None:
            raise ValueError(
                f"Maintenance task not found: {task_id}"
            )

        # Define the permitted transitions from each status.
        allowed_transitions = {
            MaintenanceStatus.PENDING_APPROVAL: {
                MaintenanceStatus.APPROVED,
                MaintenanceStatus.REJECTED,
                MaintenanceStatus.CANCELLED,
            },
            MaintenanceStatus.APPROVED: {
                MaintenanceStatus.IN_PROGRESS,
                MaintenanceStatus.CANCELLED,
            },
            MaintenanceStatus.IN_PROGRESS: {
                MaintenanceStatus.COMPLETED,
                MaintenanceStatus.CANCELLED,
            },
            MaintenanceStatus.COMPLETED: set(),
            MaintenanceStatus.REJECTED: set(),
            MaintenanceStatus.CANCELLED: set(),
        }

        permitted = allowed_transitions[task.status]

        if status not in permitted:
            raise ValueError(
                "Invalid maintenance status transition: "
                f"{task.status.value} -> {status.value}"
            )

        # Update the task only after validating the transition.
        task.status = status
        task.updated_at = datetime.now(timezone.utc).isoformat()

        return task
