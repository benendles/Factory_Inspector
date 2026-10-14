from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from app.agents.state import FactoryAgentState

from app.services.sensor_analysis import (
    SensorAnalysisService,
    SensorReadings,
)

from app.services.image_inspection import ImageInspectionService

from app.services.incident_service import (
    Incident,
    IncidentService,
    IncidentSeverity,
    IncidentStatus,
)

from app.services.maintenance_service import (
    MaintenanceService,
    MaintenanceStatus,
)

from app.services.verification_service import (
    VerificationService,
    VerificationOutcome,
)


# =========================================================
# SERVICE INSTANCES
# =========================================================

sensor_service = SensorAnalysisService()
image_service = ImageInspectionService()
incident_service = IncidentService()
maintenance_service = MaintenanceService()
verification_service = VerificationService()


# =========================================================
# GENERAL HELPERS
# =========================================================

def to_dict(value: Any) -> Any:
    """Convert dataclasses, enums, dictionaries, and lists to serializable data."""

    if is_dataclass(value) and not isinstance(value, type):
        return to_dict(asdict(value))

    if isinstance(value, dict):
        return {
            key: to_dict(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            to_dict(item)
            for item in value
        ]

    if hasattr(value, "value"):
        return value.value

    return value


def enum_value(value: Any) -> Any:
    """Return an enum's underlying value when applicable."""
    return value.value if hasattr(value, "value") else value


def append_message(
    state: FactoryAgentState,
    message: str,
) -> list[str]:
    """Append a message without mutating the existing state."""

    messages = list(state.get("messages", []))
    messages.append(message)

    return messages


def error_result(
    state: FactoryAgentState,
    error: str,
) -> dict[str, Any]:
    """Return a consistent workflow error response."""

    return {
        "status": "error",
        "error": error,
        "resolved": False,
        "messages": append_message(
            state,
            f"ERROR: {error}",
        ),
    }


def get_incident_id(
    state: FactoryAgentState,
) -> str | None:
    """Retrieve the incident ID from the workflow state."""

    incident_id = state.get("incident_id")

    if incident_id:
        return incident_id

    incident = state.get("incident", {})

    if isinstance(incident, dict):
        return (
            incident.get("incident_id")
            or incident.get("id")
        )

    return getattr(incident, "incident_id", None)


def incident_from_state(value: Any) -> Incident:
    """
    Reconstruct an Incident dataclass from LangGraph state.

    LangGraph state stores serializable dictionaries, while the incident
    and maintenance services expect an Incident object with enum values.
    """

    if isinstance(value, Incident):
        return value

    if not isinstance(value, dict):
        raise TypeError(
            "Incident must be an Incident object or dictionary."
        )

    allowed_fields = Incident.__dataclass_fields__

    incident_data = {
        key: item
        for key, item in value.items()
        if key in allowed_fields
    }

    required_fields = (
        "incident_id",
        "machine_id",
        "title",
        "description",
        "severity",
        "status",
    )

    missing_fields = [
        field
        for field in required_fields
        if field not in incident_data
    ]

    if missing_fields:
        raise ValueError(
            f"Incident is missing required fields: {missing_fields}"
        )

    # FIX 1:
    # Convert serialized severity strings back into IncidentSeverity enums.
    severity = incident_data["severity"]

    if not isinstance(severity, IncidentSeverity):
        incident_data["severity"] = IncidentSeverity(severity)

    # FIX 2:
    # Convert serialized status strings back into IncidentStatus enums.
    status = incident_data["status"]

    if not isinstance(status, IncidentStatus):
        incident_data["status"] = IncidentStatus(status)

    return Incident(**incident_data)


# =========================================================
# NODE 1: ACQUIRE DATA
# =========================================================

def acquire_data(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Validate and prepare incoming sensor readings."""

    machine_id = state.get("machine_id")
    readings = state.get("sensor_readings")

    if not machine_id:
        return error_result(
            state,
            "machine_id is required.",
        )

    if not isinstance(readings, dict):
        return error_result(
            state,
            "sensor_readings must be provided as a dictionary.",
        )

    readings = dict(readings)

    provided_machine_id = readings.get("machine_id")

    if provided_machine_id and provided_machine_id != machine_id:
        return error_result(
            state,
            "Sensor readings machine_id does not match the requested machine.",
        )

    readings["machine_id"] = machine_id

    timestamp = state.get("timestamp") or datetime.now(
        timezone.utc
    ).isoformat()

    return {
        "machine_id": machine_id,
        "sensor_readings": readings,
        "timestamp": timestamp,
        "status": "data_acquired",
        "error": None,
        "messages": append_message(
            state,
            f"Sensor data acquired for machine {machine_id}.",
        ),
    }


# =========================================================
# NODE 2: ANALYZE SENSORS
# =========================================================

def analyze_sensors(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Analyze readings for potential sensor anomalies."""

    try:
        readings_data = state.get("sensor_readings")

        if not isinstance(readings_data, dict):
            return error_result(
                state,
                "Sensor readings are missing or invalid.",
            )

        readings = SensorReadings(**readings_data)

        result = sensor_service.analyze(readings)
        result_data = to_dict(result)

        anomalies = result_data.get("anomalies", [])

        severities = [
            str(
                enum_value(item.get("severity", ""))
            ).lower()
            for item in anomalies
        ]

        if "critical" in severities:
            severity = "critical"
        elif "high" in severities:
            severity = "high"
        elif anomalies:
            severity = "medium"
        else:
            severity = "low"

        return {
            "sensor_analysis": result_data,
            "severity": severity,
            "status": "sensors_analyzed",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Sensor analysis completed for "
                    f"{state['machine_id']}. "
                    f"Anomalies: {len(anomalies)}. "
                    f"Severity: {severity}."
                ),
            ),
        }

    except (TypeError, ValueError, KeyError) as exc:
        return error_result(
            state,
            f"Sensor analysis failed: {exc}",
        )


# =========================================================
# NODE 3: INSPECT IMAGE
# =========================================================

def inspect_image(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Inspect an optional image for potential visual anomalies."""

    image_path = state.get("image_path")

    if not image_path:
        return {
            "vision_analysis": {
                "status": "skipped",
                "observations": [],
                "summary": (
                    "No image was supplied for visual inspection."
                ),
            },
            "status": "image_inspection_skipped",
            "error": None,
            "messages": append_message(
                state,
                "Visual inspection skipped because no image was supplied.",
            ),
        }

    path = Path(image_path)

    if not path.is_file():
        return error_result(
            state,
            f"Image file does not exist: {path}",
        )

    try:
        result = image_service.inspect_image(
            image_path=str(path),
            machine_id=state["machine_id"],
        )

        result_data = to_dict(result)

        return {
            "vision_analysis": result_data,
            "status": "image_inspected",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Visual inspection completed for "
                    f"{state['machine_id']}."
                ),
            ),
        }

    except Exception as exc:
        return error_result(
            state,
            f"Image inspection failed: {exc}",
        )


# =========================================================
# NODE 4: TRIAGE FINDINGS
# =========================================================

def triage_incident(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Determine whether the configured checks found potential anomalies."""

    sensor_analysis = state.get("sensor_analysis", {})
    vision_analysis = state.get("vision_analysis", {})

    sensor_anomalies = sensor_analysis.get("anomalies", [])
    visual_observations = vision_analysis.get("observations", [])

    anomalies_detected = bool(
        sensor_anomalies or visual_observations
    )

    severity = state.get("severity", "low")

    severities = [
        str(
            enum_value(item.get("severity", ""))
        ).lower()
        for item in sensor_anomalies
    ]

    if "critical" in severities:
        severity = "critical"
    elif "high" in severities:
        severity = "high"
    elif anomalies_detected and severity == "low":
        severity = "medium"

    if anomalies_detected:
        message = (
            f"Potential anomaly detected for machine "
            f"{state['machine_id']}. "
            "Creating an incident for investigation."
        )
    else:
        message = (
            f"No anomalies were identified for machine "
            f"{state['machine_id']} by the current checks."
        )

    return {
        "anomalies_detected": anomalies_detected,
        "severity": severity,
        "status": "triage_completed",
        "error": None,
        "messages": append_message(state, message),
    }


# =========================================================
# NODE 5: LOG NORMAL OPERATION
# =========================================================

def log_normal_operation(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Record that the configured checks found no anomalies."""

    return {
        "status": "normal_operation",
        "resolved": False,
        "error": None,
        "messages": append_message(
            state,
            (
                f"No anomalies were detected by the current checks for "
                f"{state['machine_id']}. "
                "This does not certify equipment safety."
            ),
        ),
    }


# =========================================================
# NODE 6: CREATE INCIDENT
# =========================================================

def create_incident(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Create an incident using the individual evidence items."""

    sensor_analysis = state.get("sensor_analysis", {})
    vision_analysis = state.get("vision_analysis", {})

    sensor_evidence = sensor_analysis.get("anomalies", [])
    visual_evidence = vision_analysis.get("observations", [])

    if not sensor_evidence and not visual_evidence:
        return error_result(
            state,
            "Cannot create an incident without sensor or visual evidence.",
        )

    try:
        incident = incident_service.create_incident(
            machine_id=state["machine_id"],
            sensor_evidence=sensor_evidence,
            visual_evidence=visual_evidence,
            requires_human_review=True,
        )

        incident_data = to_dict(incident)
        incident_id = incident_data.get("incident_id")

        if not incident_id:
            return error_result(
                state,
                "IncidentService returned an incident without an ID.",
            )

        return {
            "incident_id": incident_id,
            "incident": incident_data,
            "incident_created": True,
            "requires_human_approval": True,
            "approval_status": "pending",
            "status": "incident_created",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Incident {incident_id} created or updated "
                    "for human review."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError) as exc:
        return error_result(
            state,
            f"Incident creation failed: {exc}",
        )


# =========================================================
# NODE 7: INVESTIGATE INCIDENT
# =========================================================

def investigate_incident(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Summarize incident evidence for investigation."""

    incident = state.get("incident", {})

    if not isinstance(incident, dict) or not incident:
        return error_result(
            state,
            "Cannot investigate because incident data is missing.",
        )

    incident_id = get_incident_id(state)

    if not incident_id:
        return error_result(
            state,
            "Cannot investigate because the incident ID is missing.",
        )

    sensor_evidence = incident.get("sensor_evidence", [])
    visual_evidence = incident.get("visual_evidence", [])

    investigation = {
        "incident_id": incident_id,
        "machine_id": state["machine_id"],
        "sensor_findings": sensor_evidence,
        "visual_findings": visual_evidence,
        "evidence_count": (
            len(sensor_evidence) + len(visual_evidence)
        ),
        "requires_human_review": True,
        "summary": (
            "Review the findings against the machine's operating "
            "conditions and applicable maintenance procedures "
            "before deciding on action."
        ),
    }

    return {
        "investigation": investigation,
        "status": "investigation_completed",
        "error": None,
        "messages": append_message(
            state,
            f"Initial investigation completed for incident {incident_id}.",
        ),
    }


# =========================================================
# NODE 8: GENERATE MAINTENANCE TASK
# =========================================================

def generate_maintenance_task(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Create a proposed maintenance task requiring explicit approval."""

    incident_data = state.get("incident")

    if not isinstance(incident_data, dict) or not incident_data:
        return error_result(
            state,
            "Cannot generate a maintenance task without an incident.",
        )

    try:
        # Reconstruct the Incident object and restore its enum fields.
        incident = incident_from_state(incident_data)

        task = maintenance_service.create_task(incident)
        task_data = to_dict(task)

        task_id = (
            task_data.get("task_id")
            or task_data.get("id")
        )

        if not task_id:
            return error_result(
                state,
                "MaintenanceService returned a task without an ID.",
            )

        recommendation = task_data.get("recommendation", {})

        actions = (
            recommendation.get("actions", [])
            if isinstance(recommendation, dict)
            else []
        )

        return {
            "maintenance_task_id": task_id,
            "maintenance_status": enum_value(
                task_data.get("status")
            ),
            "action_plan": actions,
            "requires_human_approval": True,
            "approval_status": "pending",
            "status": "awaiting_approval",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Maintenance task {task_id} generated. "
                    "Explicit human approval is required before work begins."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Maintenance task creation failed: {exc}",
        )


# =========================================================
# NODE 9: HUMAN APPROVAL
# =========================================================

def process_approval(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Pause the graph until a human approval decision is submitted."""

    task_id = state.get("maintenance_task_id")

    if not task_id:
        return error_result(
            state,
            "Cannot request approval because the maintenance task ID is missing.",
        )

    decision = interrupt(
        {
            "type": "maintenance_approval_required",
            "maintenance_task_id": task_id,
            "incident_id": get_incident_id(state),
            "machine_id": state.get("machine_id"),
            "action_plan": state.get("action_plan", []),
            "message": (
                "Review the proposed maintenance actions. "
                "Approve or reject before work begins."
            ),
        }
    )

    if not isinstance(decision, dict):
        return error_result(
            state,
            "Approval response must be a dictionary.",
        )

    approval_status = decision.get("approval_status")
    approval_user = decision.get("approval_user")
    approval_comment = decision.get("approval_comment", "")

    if approval_status not in ("approved", "rejected"):
        return error_result(
            state,
            "Approval decision must be 'approved' or 'rejected'.",
        )

    if (
        not isinstance(approval_user, str)
        or not approval_user.strip()
    ):
        return error_result(
            state,
            "A reviewer identity is required for the approval decision.",
        )

    if not isinstance(approval_comment, str):
        return error_result(
            state,
            "approval_comment must be a string.",
        )

    try:
        target_status = (
            MaintenanceStatus.APPROVED
            if approval_status == "approved"
            else MaintenanceStatus.REJECTED
        )

        task = maintenance_service.update_status(
            task_id,
            target_status,
        )

        message = (
            f"Maintenance task {task_id} {approval_status} by "
            f"{approval_user.strip()}."
        )

        if approval_comment.strip():
            message += (
                f" Reviewer comment: {approval_comment.strip()}"
            )

        return {
            "approval_status": approval_status,
            "approval_user": approval_user.strip(),
            "approval_comment": approval_comment.strip(),
            "maintenance_status": enum_value(task.status),
            "status": approval_status,
            "error": None,
            "messages": append_message(state, message),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Could not process the approval decision: {exc}",
        )


# =========================================================
# NODE 10: START MAINTENANCE
# =========================================================

def start_maintenance(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Start simulated maintenance only after explicit approval."""

    if state.get("approval_status") != "approved":
        return error_result(
            state,
            "Maintenance cannot start without explicit human approval.",
        )

    task_id = state.get("maintenance_task_id")

    if not task_id:
        return error_result(
            state,
            "Cannot start maintenance because the task ID is missing.",
        )

    try:
        task = maintenance_service.update_status(
            task_id,
            MaintenanceStatus.IN_PROGRESS,
        )

        return {
            "maintenance_status": enum_value(task.status),
            "status": "maintenance_in_progress",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Simulated maintenance started for task {task_id}. "
                    "This does not represent real-world maintenance work."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Could not start maintenance: {exc}",
        )


# =========================================================
# NODE 11: COMPLETE SIMULATED MAINTENANCE
# =========================================================

def complete_maintenance(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Complete the simulated maintenance task."""

    if (
        state.get("maintenance_status")
        != MaintenanceStatus.IN_PROGRESS.value
    ):
        return error_result(
            state,
            "Cannot complete maintenance because the task is not in progress.",
        )

    task_id = state.get("maintenance_task_id")

    if not task_id:
        return error_result(
            state,
            "Cannot complete maintenance because the task ID is missing.",
        )

    try:
        task = maintenance_service.update_status(
            task_id,
            MaintenanceStatus.COMPLETED,
        )

        return {
            "maintenance_status": enum_value(task.status),
            "status": "maintenance_completed",
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Simulated maintenance task {task_id} marked completed. "
                    "Fresh evidence is still required to assess the incident."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Could not complete simulated maintenance: {exc}",
        )


# =========================================================
# NODE 12: VERIFY MAINTENANCE
# =========================================================

def verify_maintenance(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Verify maintenance using fresh post-maintenance sensor readings."""

    incident_id = get_incident_id(state)
    task_id = state.get("maintenance_task_id")

    if not incident_id:
        return error_result(
            state,
            "Cannot verify maintenance because the incident ID is missing.",
        )

    if not task_id:
        return error_result(
            state,
            "Cannot verify maintenance because the task ID is missing.",
        )

    try:
        incident = incident_service.get_incident(incident_id)
        task = maintenance_service.get_task(task_id)

        if incident is None:
            return error_result(
                state,
                f"Incident {incident_id} could not be retrieved.",
            )

        if task is None:
            return error_result(
                state,
                f"Maintenance task {task_id} could not be retrieved.",
            )

        result = verification_service.verify(
            incident=incident,
            maintenance_task=task,
            post_maintenance_readings=state.get(
                "post_maintenance_readings"
            ),
        )

        result_data = to_dict(result)
        outcome = enum_value(result_data.get("outcome"))

        resolved = (
            outcome == VerificationOutcome.VERIFIED.value
        )

        if resolved:
            message = (
                f"Configured verification checks passed for incident "
                f"{incident_id}. This does not certify equipment safety."
            )
        else:
            message = (
                f"Verification did not establish resolution for incident "
                f"{incident_id}. Outcome: {outcome}."
            )

        return {
            "verification_result": result_data,
            "resolved": resolved,
            "status": "verification_completed",
            "error": None,
            "messages": append_message(state, message),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Maintenance verification failed: {exc}",
        )


# =========================================================
# NODE 13: CLOSE INCIDENT
# =========================================================

def close_incident(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Close an incident only after configured verification passes."""

    verification_result = state.get("verification_result", {})
    outcome = enum_value(
        verification_result.get("outcome")
    )

    if outcome != VerificationOutcome.VERIFIED.value:
        return error_result(
            state,
            "Incident cannot be closed without a verified outcome.",
        )

    incident_id = get_incident_id(state)

    if not incident_id:
        return error_result(
            state,
            "Cannot close the incident because the incident ID is missing.",
        )

    try:
        incident = incident_service.update_status(
            incident_id,
            IncidentStatus.RESOLVED,
        )

        return {
            "incident": to_dict(incident),
            "status": "incident_resolved",
            "resolved": True,
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Incident {incident_id} closed after configured checks passed. "
                    "Qualified personnel must still determine whether equipment "
                    "can safely return to service."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Could not close incident: {exc}",
        )


# =========================================================
# NODE 14: ESCALATE INCIDENT
# =========================================================

def escalate_incident(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Escalate an incident when verification cannot establish resolution."""

    incident_id = get_incident_id(state)

    if not incident_id:
        return error_result(
            state,
            "Cannot escalate because the incident ID is missing.",
        )

    verification_result = state.get("verification_result", {})

    outcome = enum_value(
        verification_result.get("outcome", "inconclusive")
    )

    try:
        incident = incident_service.update_status(
            incident_id,
            IncidentStatus.ESCALATED,
        )

        return {
            "incident": to_dict(incident),
            "status": "incident_escalated",
            "resolved": False,
            "error": None,
            "messages": append_message(
                state,
                (
                    f"Incident {incident_id} escalated. "
                    f"Verification outcome: {outcome}. "
                    "Human assessment and additional evidence are required."
                ),
            ),
        }

    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return error_result(
            state,
            f"Could not escalate incident: {exc}",
        )


# =========================================================
# NODE 15: HANDLE ERRORS
# =========================================================

def handle_error(
    state: FactoryAgentState,
) -> dict[str, Any]:
    """Stop the workflow safely when an error occurs."""

    error = state.get("error") or (
        "An unknown workflow error occurred."
    )

    return {
        "status": "error",
        "resolved": False,
        "error": error,
        "messages": append_message(
            state,
            (
                f"Workflow stopped: {error} "
                "No conclusion about equipment safety should be inferred."
            ),
        ),
    }