"""LangGraph nodes for the Factory Inspector AI workflow."""

from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from enum import Enum
from uuid import UUID
import re

from langgraph.types import interrupt
from app.simulator.scenarios import get_scenario
from app.agents.state import FactoryAgentState

from app.services.sensor_analysis import (
    SensorAnalysisService,
    SensorReadings,
)
from app.services.image_inspection import ImageInspectionService
from app.services.nameplate_ocr import NameplateOCRService
from app.services.incident_service import (
    IncidentService,
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

from app.database.session import SessionLocal
from app.services.sql_equipment_matcher import SQLEquipmentMatcher


# ---------------------------------------------------------------------------
# SERVICE INSTANCES
# ---------------------------------------------------------------------------

sensor_service = SensorAnalysisService()
image_service = ImageInspectionService()
nameplate_ocr_service = NameplateOCRService()

incident_service = IncidentService()
maintenance_service = MaintenanceService()
verification_service = VerificationService()


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

REGISTRY_VERIFIED = "verified_match"
REGISTRY_POSSIBLE = "possible_match"

IDENTITY_AUDIT_ID_FIELD = "physical_identity_verification_audit_id"
IDENTITY_REGISTRY_ID_FIELD = "physical_identity_verified_registry_id"


# ---------------------------------------------------------------------------
# SERIALIZATION AND STATE HELPERS
# ---------------------------------------------------------------------------

def _to_dict(value):
    """Convert supported Python objects into dictionaries."""

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, Enum):
        return value.value

    if hasattr(value, "model_dump"):
        try:
            result = value.model_dump(mode="json")
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return result if isinstance(result, dict) else {}

    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    if hasattr(value, "dict"):
        result = value.dict()
        return result if isinstance(result, dict) else {}

    return {}


def _json_safe(value):
    """Convert nested data into JSON-compatible values."""

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))

    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump(mode="json"))
        except Exception:
            return str(value)

    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except Exception:
            pass

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return value


def _get_value(data, *keys, default=None):
    """Return the first non-empty dictionary value."""

    if not isinstance(data, dict):
        return default

    for key in keys:
        value = data.get(key)

        if value is not None and value != "":
            return value

    return default


def _normalise_identifier(value):
    """Normalize an identifier for comparison."""

    if value is None:
        return None

    normalized = re.sub(
        r"[\s\-_:./]+",
        "",
        str(value),
    ).upper()

    return normalized or None


def _append_message(state, message):
    """Return an updated message list without mutating the old list."""

    messages = list(state.get("messages") or [])
    messages.append(_json_safe(message))
    return messages


def _error(state, node, message):
    """Record a workflow error without claiming resolution."""

    state["status"] = "error"
    state["resolved"] = False
    state["error"] = str(message)

    state["messages"] = _append_message(
        state,
        {
            "node": node,
            "status": "error",
            "error": str(message),
        },
    )

    return state


def _get_registry_status(match):
    """Extract a registry status from a dictionary or object."""

    if match is None:
        return "no_match"

    if isinstance(match, dict):
        status = match.get("status", "no_match")
    else:
        status = getattr(match, "status", "no_match")

    return getattr(status, "value", status)


def _record_identifier_conflicts(visual_data, ocr_data):
    """Record disagreements between visual identification and OCR."""

    conflicts = []

    aliases = {
        "manufacturer": (),
        "model_number": ("model",),
        "serial_number": ("serial",),
        "asset_tag": ("asset_id",),
    }

    for field, alternate_keys in aliases.items():
        visual_value = _get_value(
            visual_data,
            field,
            *alternate_keys,
        )

        ocr_value = _get_value(
            ocr_data,
            field,
            *alternate_keys,
        )

        if not visual_value or not ocr_value:
            continue

        if (
            _normalise_identifier(visual_value)
            != _normalise_identifier(ocr_value)
        ):
            conflicts.append(
                {
                    "field": field,
                    "visual_value": _json_safe(visual_value),
                    "ocr_value": _json_safe(ocr_value),
                    "reason": (
                        "Visual identification and nameplate OCR "
                        "returned different values."
                    ),
                }
            )

    return conflicts


def _build_registry_candidate(visual_data, ocr_data):
    """Build an equipment candidate without treating evidence as verified."""

    candidate = {
        "equipment_type": (
            _get_value(visual_data, "equipment_type", "type")
            or _get_value(ocr_data, "equipment_type", "type")
        ),
        "manufacturer": (
            _get_value(visual_data, "manufacturer")
            or _get_value(ocr_data, "manufacturer")
        ),
        "model_number": (
            _get_value(visual_data, "model_number", "model")
            or _get_value(ocr_data, "model_number", "model")
        ),
        "serial_number": (
            _get_value(visual_data, "serial_number", "serial")
            or _get_value(ocr_data, "serial_number", "serial")
        ),
        "asset_tag": (
            _get_value(visual_data, "asset_tag", "asset_id")
            or _get_value(ocr_data, "asset_tag", "asset_id")
        ),
    }

    return {
        key: _json_safe(value)
        for key, value in candidate.items()
        if value is not None and value != ""
    }


def _get_incident_and_task(state):
    """Retrieve the actual incident and maintenance-task objects."""

    incident_id = state.get("incident_id")
    task_id = state.get("maintenance_task_id")

    if not incident_id:
        raise ValueError("The incident ID is missing.")

    if not task_id:
        raise ValueError("The maintenance task ID is missing.")

    incident = incident_service.get_incident(incident_id)
    task = maintenance_service.get_task(task_id)

    if incident is None:
        raise ValueError(
            f"Incident {incident_id} could not be retrieved."
        )

    if task is None:
        raise ValueError(
            f"Maintenance task {task_id} could not be retrieved."
        )

    return incident, task


def _identifier_conflicts(state):
    """Return both conflict collections, preserving missing-data detection."""

    return (
        state.get("equipment_identifier_conflicts"),
        state.get("identifier_conflicts"),
    )


def _has_valid_physical_identity_confirmation(state):
    """
    Fail closed unless physical identity confirmation is backed by audit data.

    A registry match is not physical confirmation. The trusted verification
    endpoint must set the confirmation fields after recording the audit.
    """

    if state.get("physical_identity_confirmed") is not True:
        return False

    if state.get("physical_verification_required") is not False:
        return False

    if state.get("registry_requires_physical_verification") is not False:
        return False

    if state.get("registry_match_status") != REGISTRY_VERIFIED:
        return False

    registry_match = state.get("registry_match")

    if not isinstance(registry_match, dict):
        return False

    if registry_match.get("status") != REGISTRY_VERIFIED:
        return False

    candidate = registry_match.get("candidate")

    if not isinstance(candidate, dict):
        return False

    candidate_id = candidate.get("id")

    if not candidate_id:
        return False

    verified_registry_id = state.get(IDENTITY_REGISTRY_ID_FIELD)
    audit_id = state.get(IDENTITY_AUDIT_ID_FIELD)

    if not verified_registry_id or not audit_id:
        return False

    if str(verified_registry_id) != str(candidate_id):
        return False

    try:
        UUID(str(audit_id))
    except (TypeError, ValueError, AttributeError):
        return False

    equipment_conflicts, registry_conflicts = _identifier_conflicts(state)

    if not isinstance(equipment_conflicts, list):
        return False

    if not isinstance(registry_conflicts, list):
        return False

    if equipment_conflicts or registry_conflicts:
        return False

    return True


def _task_status_value(task):
    """Return a maintenance task's status as a string."""

    status = getattr(task, "status", None)

    if isinstance(status, Enum):
        return status.value

    return status


def _serialize_task(task):
    """Serialize a canonical maintenance task into JSON-safe data."""

    if task is None:
        return {}

    if is_dataclass(task) and not isinstance(task, type):
        task_data = _json_safe(asdict(task))
    else:
        task_data = _json_safe(_to_dict(task))

    if not isinstance(task_data, dict):
        task_data = {}

    status = _task_status_value(task)

    if status is not None:
        task_data["status"] = status

    recommendations = []

    for recommendation in (
        getattr(task, "recommended_actions", None) or []
    ):
        if is_dataclass(recommendation) and not isinstance(
            recommendation,
            type,
        ):
            recommendation_data = asdict(recommendation)
        else:
            recommendation_data = _to_dict(recommendation)

        recommendations.append(_json_safe(recommendation_data))

    task_data["recommended_actions"] = recommendations

    return task_data


def _format_proposed_actions(recommendations):
    """Format recommendations for the human approval interface."""

    proposed_actions = []

    for recommendation in recommendations:
        recommendation = _json_safe(recommendation)

        if not isinstance(recommendation, dict):
            continue

        action = recommendation.get("action")

        if not action:
            continue

        reason = recommendation.get("reason", action)

        proposed_actions.append(
            {
                "action": action,
                "description": reason,
                "reason": reason,
                "priority": recommendation.get("priority", "normal"),
                "requires_qualified_technician": (
                    recommendation.get(
                        "requires_qualified_technician",
                        True,
                    )
                ),
                "requires_human_review": True,
            }
        )

    return proposed_actions


def _maintenance_identity_gate(state, node_name):
    """
    Apply the physical identity gate before maintenance actions.

    This workflow simulates maintenance; this gate does not authorize
    real-world physical work.
    """

    if _has_valid_physical_identity_confirmation(state):
        return True

    _error(
        state,
        node_name,
        (
            "Maintenance blocked: valid audit-backed physical identity "
            "confirmation is required. The registry match alone is not "
            "sufficient. Confirm the physical machine through the identity "
            "verification workflow before continuing."
        ),
    )

    return False


# ---------------------------------------------------------------------------
# NODE 1: ACQUIRE DATA
# ---------------------------------------------------------------------------

def acquire_data(state: FactoryAgentState) -> FactoryAgentState:
    """Initialize inspection metadata and default workflow fields."""

    state["timestamp"] = state.get("timestamp") or datetime.now(
        timezone.utc
    ).isoformat()

    state.setdefault("sensor_readings", {})
    state.setdefault("sensor_analysis", {})
    state.setdefault("vision_analysis", {})
    state.setdefault("equipment_identification", {})
    state.setdefault("registry_match", {})
    state.setdefault("registry_match_status", "not_checked")
    state.setdefault("registry_asset_id", None)
    state.setdefault("registry_requires_physical_verification", True)
    state.setdefault("physical_identity_confirmed", False)
    state.setdefault("physical_verification_required", True)
    state.setdefault(IDENTITY_AUDIT_ID_FIELD, None)
    state.setdefault(IDENTITY_REGISTRY_ID_FIELD, None)
    state.setdefault("equipment_identifier_conflicts", [])
    state.setdefault("identifier_conflicts", [])
    state.setdefault("anomalies_detected", [])
    state.setdefault("messages", [])
    state.setdefault("resolved", False)
    state.setdefault("error", None)
    state.setdefault("post_maintenance_readings", {})

    state["status"] = "inspection_started"

    return state


# ---------------------------------------------------------------------------
# NODE 2: ANALYZE SENSORS
# ---------------------------------------------------------------------------

def analyze_sensors(state: FactoryAgentState) -> FactoryAgentState:
    """Analyze sensor readings using SensorAnalysisService."""

    try:
        raw = state.get("sensor_readings", {})

        if isinstance(raw, SensorReadings):
            readings = raw

        elif isinstance(raw, dict):
            required = (
                "machine_id",
                "temperature_c",
                "vibration_mm_s",
                "pressure_bar",
                "moisture_percent",
            )

            missing = [
                key for key in required
                if key not in raw
            ]

            if missing:
                raise ValueError(
                    "Missing required sensor fields: "
                    + ", ".join(missing)
                )

            readings = SensorReadings(
                machine_id=str(raw["machine_id"]),
                temperature_c=float(raw["temperature_c"]),
                vibration_mm_s=float(raw["vibration_mm_s"]),
                pressure_bar=float(raw["pressure_bar"]),
                moisture_percent=float(raw["moisture_percent"]),
            )

        else:
            raise TypeError(
                "sensor_readings must be a dictionary or SensorReadings."
            )

        result = sensor_service.analyze(readings)
        analysis = _json_safe(_to_dict(result))

        if not isinstance(analysis, dict):
            raise TypeError(
                "Sensor analysis returned an invalid result."
            )

        state["sensor_analysis"] = analysis

        anomalies = analysis.get("anomalies", [])

        if not isinstance(anomalies, list):
            anomalies = []

        state["anomalies_detected"] = [
            _json_safe(_to_dict(item))
            for item in anomalies
        ]

        state["messages"] = _append_message(
            state,
            {
                "node": "analyze_sensors",
                "status": "success",
                "anomalies_found": len(state["anomalies_detected"]),
                "sensor_status": analysis.get("status", "unknown"),
            },
        )

    except Exception as exc:
        state["sensor_analysis"] = {
            "status": "error",
            "error": str(exc),
        }

        # Fail closed: a failed analysis must not be interpreted as
        # proof that no anomaly exists.
        state["anomalies_detected"] = []
        state["status"] = "error"
        state["resolved"] = False
        state["error"] = str(exc)

        state["messages"] = _append_message(
            state,
            {
                "node": "analyze_sensors",
                "status": "error",
                "error": str(exc),
            },
        )

    return state


# ---------------------------------------------------------------------------
# NODE 3: INSPECT IMAGE
# ---------------------------------------------------------------------------

def inspect_image(state: FactoryAgentState) -> FactoryAgentState:
    """Inspect the supplied factory image."""

    image_path = state.get("image_path")
    machine_id = state.get("machine_id", "unknown")

    if not image_path:
        state["vision_analysis"] = {
            "status": "skipped",
            "reason": "No image path was provided.",
        }

        state["equipment_identification"] = {}

        state["messages"] = _append_message(
            state,
            {
                "node": "inspect_image",
                "status": "skipped",
            },
        )

        return state

    try:
        result = image_service.inspect_image(
            image_path=image_path,
            machine_id=machine_id,
        )

        result_data = _json_safe(_to_dict(result))

        if not isinstance(result_data, dict):
            raise TypeError(
                "Image inspection returned an invalid result."
            )

        state["vision_analysis"] = result_data

        equipment = result_data.get("equipment", {})

        if not equipment and hasattr(result, "equipment"):
            equipment = _json_safe(_to_dict(result.equipment))

        state["equipment_identification"] = _to_dict(equipment)

        state["messages"] = _append_message(
            state,
            {
                "node": "inspect_image",
                "status": "success",
            },
        )

    except Exception as exc:
        state["vision_analysis"] = {
            "status": "error",
            "error": str(exc),
        }

        state["equipment_identification"] = {}

        state["messages"] = _append_message(
            state,
            {
                "node": "inspect_image",
                "status": "error",
                "error": str(exc),
            },
        )

    return state


# ---------------------------------------------------------------------------
# NODE 4: IDENTIFY EQUIPMENT
# ---------------------------------------------------------------------------

def identify_equipment(state: FactoryAgentState) -> FactoryAgentState:
    """
    Identify equipment using visual evidence, nameplate OCR, and PostgreSQL.

    A registry lookup does not prove the physical identity of the machine.
    Human identity verification remains mandatory before approval.
    """

    image_path = state.get("image_path")

    visual_data = _to_dict(
        state.get("equipment_identification", {})
    )

    if not visual_data:
        vision = _to_dict(state.get("vision_analysis", {}))
        visual_data = _to_dict(vision.get("equipment", {}))

    ocr_data = {}
    ocr_status = "skipped"
    ocr_notes = []

    # OCR is attempted only when an accessible image exists.
    if image_path and Path(image_path).is_file():
        try:
            result = nameplate_ocr_service.inspect(str(image_path))
            result_data = _json_safe(_to_dict(result))

            ocr_data = _to_dict(result_data.get("fields", {}))
            ocr_status = result_data.get("status", "unknown")
            ocr_notes = result_data.get("notes", [])

            state["nameplate_ocr_result"] = {
                "image_path": str(image_path),
                "status": ocr_status,
                "raw_text": result_data.get("raw_text", ""),
                "fields": _json_safe(ocr_data),
                "confidence": result_data.get("confidence", 0.0),
                "requires_human_review": True,
                "notes": _json_safe(ocr_notes),
            }

        except Exception as exc:
            ocr_status = "error"
            ocr_notes = [str(exc)]

            state["nameplate_ocr_result"] = {
                "image_path": str(image_path),
                "status": "error",
                "fields": {},
                "requires_human_review": True,
                "notes": ocr_notes,
            }

    else:
        state["nameplate_ocr_result"] = {
            "image_path": str(image_path) if image_path else None,
            "status": "skipped",
            "fields": {},
            "requires_human_review": True,
            "notes": [
                "No accessible image file was available for OCR."
            ],
        }

    visual_ocr_conflicts = _record_identifier_conflicts(
        visual_data,
        ocr_data,
    )

    candidate = _build_registry_candidate(
        visual_data,
        ocr_data,
    )

    state["equipment_identification"] = {
        **_json_safe(visual_data),
        "candidate": candidate,
        "nameplate_ocr_status": ocr_status,
        "identifier_conflicts": visual_ocr_conflicts,
        "requires_human_review": True,
        "physical_identity_confirmed": False,
    }

    # Each identification attempt invalidates prior identity confirmation.
    state["physical_identity_confirmed"] = False
    state["physical_verification_required"] = True
    state["registry_requires_physical_verification"] = True
    state[IDENTITY_AUDIT_ID_FIELD] = None
    state[IDENTITY_REGISTRY_ID_FIELD] = None

    state["identifier_conflicts"] = []
    state["equipment_identifier_conflicts"] = visual_ocr_conflicts

    machine_id = state.get("machine_id")

    has_machine_id = (
        isinstance(machine_id, str)
        and bool(machine_id.strip())
    )

    if not candidate and not has_machine_id:
        state["registry_match"] = {
            "status": "not_checked",
            "candidate": None,
            "candidates": [],
            "confidence": 0.0,
            "matched_identifiers": [],
            "identifier_conflicts": [],
            "physical_identity_confirmed": False,
            "physical_verification_required": True,
            "notes": [
                "No usable equipment identifiers or machine ID were provided.",
                "Physical identity confirmation is required.",
            ],
        }

        state["registry_match_status"] = "not_checked"
        state["registry_asset_id"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "identify_equipment",
                "status": "no_candidate",
                "ocr_status": ocr_status,
            },
        )

        return state

    db = None

    try:
        db = SessionLocal()
        matcher = SQLEquipmentMatcher(db)

        match_data = matcher.match(
            machine_id=machine_id,
            serial_number=candidate.get("serial_number"),
            asset_tag=candidate.get("asset_tag"),
            manufacturer=candidate.get("manufacturer"),
            model_number=candidate.get("model_number"),
        )

        match_data = _json_safe(_to_dict(match_data))

        if not isinstance(match_data, dict):
            raise TypeError(
                "The SQL equipment matcher returned an invalid result."
            )

        match_status = match_data.get("status", "no_match")

        registry_conflicts = match_data.get(
            "identifier_conflicts",
            [],
        )

        if not isinstance(registry_conflicts, list):
            registry_conflicts = [
                {
                    "reason": (
                        "The registry matcher returned an invalid "
                        "identifier-conflict result."
                    )
                }
            ]

        combined_conflicts = (
            visual_ocr_conflicts + registry_conflicts
        )

        if (
            visual_ocr_conflicts
            and match_status == REGISTRY_VERIFIED
        ):
            match_status = REGISTRY_POSSIBLE

        registry_candidate = match_data.get("candidate")

        if not isinstance(registry_candidate, dict):
            registry_candidate = None

        match_data["candidate"] = registry_candidate
        match_data["status"] = match_status
        match_data["identifier_conflicts"] = registry_conflicts
        match_data["physical_identity_confirmed"] = False
        match_data["physical_verification_required"] = True
        match_data["requires_human_physical_verification"] = True
        match_data["nameplate_ocr_status"] = ocr_status
        match_data["visual_ocr_conflicts"] = visual_ocr_conflicts

        notes = match_data.get("notes", [])

        if not isinstance(notes, list):
            notes = [str(notes)]

        match_data["notes"] = notes + [
            (
                "A registry match is only a candidate match. It does not "
                "prove the physical machine has the listed identity."
            ),
            (
                "Physical identity must be confirmed through the "
                "audit-backed human verification workflow before "
                "asset-specific maintenance can be approved."
            ),
        ]

        registry_id = (
            registry_candidate.get("id")
            if registry_candidate
            else None
        )

        state["registry_match"] = match_data
        state["registry_match_status"] = match_status
        state["registry_asset_id"] = (
            str(registry_id)
            if registry_id is not None
            else None
        )

        state["identifier_conflicts"] = registry_conflicts
        state["equipment_identifier_conflicts"] = combined_conflicts

        state["messages"] = _append_message(
            state,
            {
                "node": "identify_equipment",
                "status": "success",
                "machine_id_lookup_used": has_machine_id,
                "registry_match_status": match_status,
                "registry_asset_id": state["registry_asset_id"],
                "registry_conflict_count": len(registry_conflicts),
                "visual_ocr_conflict_count": len(visual_ocr_conflicts),
                "ocr_status": ocr_status,
                "physical_identity_confirmed": False,
            },
        )

    except Exception as exc:
        state["registry_match"] = {
            "status": "error",
            "candidate": None,
            "candidates": [],
            "confidence": 0.0,
            "matched_identifiers": [],
            "identifier_conflicts": [],
            "physical_identity_confirmed": False,
            "physical_verification_required": True,
            "notes": [
                "PostgreSQL equipment registry lookup failed.",
                str(exc),
                "Physical identity remains unverified.",
            ],
        }

        state["registry_match_status"] = "error"
        state["registry_asset_id"] = None
        state["identifier_conflicts"] = []

        state["messages"] = _append_message(
            state,
            {
                "node": "identify_equipment",
                "status": "error",
                "error": str(exc),
            },
        )

    finally:
        if db is not None:
            db.close()

    return state


# ---------------------------------------------------------------------------
# NODE 5: TRIAGE INCIDENT
# ---------------------------------------------------------------------------

def triage_incident(state: FactoryAgentState) -> FactoryAgentState:
    """Determine whether available evidence warrants an incident."""

    anomalies = state.get("anomalies_detected", [])

    if not isinstance(anomalies, list):
        anomalies = []

    vision = _to_dict(state.get("vision_analysis", {}))
    observations = vision.get("observations", [])

    if not isinstance(observations, list):
        observations = []

    visual_concerns = [
        item
        for item in observations
        if (
            isinstance(item, dict)
            and item.get("is_anomaly") is True
        )
    ]

    requires_incident = bool(anomalies or visual_concerns)

    state["triage_result"] = {
        "requires_incident": requires_incident,
        "sensor_anomaly_count": len(anomalies),
        "visual_concern_count": len(visual_concerns),
        "sensor_analysis_status": _to_dict(
            state.get("sensor_analysis", {})
        ).get("status", "unknown"),
        "registry_match_status": state.get(
            "registry_match_status",
            "not_checked",
        ),
        "physical_identity_confirmed": False,
        "requires_human_review": True,
    }

    state["messages"] = _append_message(
        state,
        {
            "node": "triage_incident",
            "requires_incident": requires_incident,
        },
    )

    return state


# ---------------------------------------------------------------------------
# NODE 6: LOG NORMAL OPERATION
# ---------------------------------------------------------------------------

def log_normal_operation(state: FactoryAgentState) -> FactoryAgentState:
    """Record that current checks did not identify an incident."""

    state["status"] = "normal"
    state["resolved"] = False

    state["messages"] = _append_message(
        state,
        {
            "node": "log_normal_operation",
            "status": "normal",
            "note": (
                "No incident-triggering anomaly was identified by current "
                "checks. This does not certify the equipment safe."
            ),
        },
    )

    return state


# ---------------------------------------------------------------------------
# NODE 7: CREATE INCIDENT
# ---------------------------------------------------------------------------

def create_incident(state: FactoryAgentState) -> FactoryAgentState:
    """Create an incident from actual sensor or visual evidence."""

    try:
        machine_id = state.get("machine_id")

        if not isinstance(machine_id, str) or not machine_id.strip():
            raise ValueError(
                "machine_id must be a non-empty string."
            )

        sensor_analysis = _to_dict(
            state.get("sensor_analysis", {})
        )

        sensor_evidence = sensor_analysis.get("anomalies", [])

        visual_analysis = _to_dict(
            state.get("vision_analysis", {})
        )

        visual_evidence = visual_analysis.get("observations", [])

        if not isinstance(sensor_evidence, list):
            sensor_evidence = []

        if not isinstance(visual_evidence, list):
            visual_evidence = []

        sensor_evidence = [
            _json_safe(_to_dict(item))
            for item in sensor_evidence
        ]

        visual_evidence = [
            _json_safe(_to_dict(item))
            for item in visual_evidence
        ]

        if not sensor_evidence:
            detected = state.get("anomalies_detected", [])

            if isinstance(detected, list):
                sensor_evidence = [
                    _json_safe(_to_dict(item))
                    for item in detected
                ]

        if not sensor_evidence and not visual_evidence:
            raise ValueError(
                "Cannot create an incident without sensor or visual evidence."
            )

        for item in sensor_evidence + visual_evidence:
            if isinstance(item, dict):
                item.setdefault("machine_id", machine_id)

        incident = incident_service.create_incident(
            machine_id=machine_id,
            visual_evidence=visual_evidence,
            sensor_evidence=sensor_evidence,
            requires_human_review=True,
        )

        incident_data = _json_safe(_to_dict(incident))

        state["incident"] = incident_data
        state["incident_created"] = True
        state["incident_id"] = incident_data.get("incident_id")
        state["status"] = "incident_created"
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "create_incident",
                "status": "success",
                "incident_id": state["incident_id"],
            },
        )

    except Exception as exc:
        state["incident_created"] = False
        _error(state, "create_incident", exc)

    return state


# ---------------------------------------------------------------------------
# NODE 8: INVESTIGATE INCIDENT
# ---------------------------------------------------------------------------

def investigate_incident(state: FactoryAgentState) -> FactoryAgentState:
    """Prepare an evidence-based incident investigation."""

    state["investigation"] = {
        "incident_id": state.get("incident_id"),
        "machine_id": state.get("machine_id"),
        "sensor_analysis": _json_safe(
            state.get("sensor_analysis", {})
        ),
        "vision_analysis": _json_safe(
            state.get("vision_analysis", {})
        ),
        "equipment_identification": _json_safe(
            state.get("equipment_identification", {})
        ),
        "registry_match": _json_safe(
            state.get("registry_match", {})
        ),
        "registry_match_status": state.get(
            "registry_match_status",
            "not_checked",
        ),
        "identifier_conflicts": _json_safe(
            state.get("equipment_identifier_conflicts", [])
        ),
        "registry_identifier_conflicts": _json_safe(
            state.get("identifier_conflicts", [])
        ),
        "nameplate_ocr_result": _json_safe(
            state.get("nameplate_ocr_result", {})
        ),
        "anomalies_detected": _json_safe(
            state.get("anomalies_detected", [])
        ),
        "incident_details": _json_safe(
            state.get("incident", {})
        ),
        "requires_human_review": True,
        "physical_identity_confirmed": False,
    }

    state["messages"] = _append_message(
        state,
        {
            "node": "investigate_incident",
            "status": "success",
        },
    )

    return state


# ---------------------------------------------------------------------------
# NODE 9: GENERATE MAINTENANCE TASK
# ---------------------------------------------------------------------------

def generate_maintenance_task(
    state: FactoryAgentState,
) -> FactoryAgentState:
    """
    Create a maintenance task and serialize it for human review.

    Creating a task is only a proposal. It does not authorize physical work.
    """

    try:
        incident_id = state.get("incident_id")

        if not incident_id:
            raise ValueError(
                "Cannot create a maintenance task without an incident ID."
            )

        incident = incident_service.get_incident(incident_id)

        if incident is None:
            raise ValueError(
                f"Incident {incident_id} could not be retrieved."
            )

        task = maintenance_service.create_task(incident)
        task_id = getattr(task, "task_id", None)

        if not task_id:
            raise ValueError(
                "Maintenance service returned a task without a task ID."
            )

        task = maintenance_service.get_task(task_id)

        if task is None:
            raise ValueError(
                f"Maintenance task {task_id} could not be retrieved."
            )

        task_data = _serialize_task(task)

        proposed_actions = _format_proposed_actions(
            task_data.get("recommended_actions", [])
        )

        task_data["proposed_actions"] = proposed_actions

        state["incident"] = _json_safe(_to_dict(incident))
        state["maintenance_task"] = task_data
        state["maintenance_task_id"] = str(task.task_id)
        state["maintenance_task_description"] = task.problem
        state["maintenance_status"] = _task_status_value(task)
        state["action_plan"] = proposed_actions

        state["requires_human_approval"] = True
        state["approval_status"] = "pending"
        state["status"] = "awaiting_approval"
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "generate_maintenance_task",
                "status": "success",
                "maintenance_task_id": str(task.task_id),
                "proposed_action_count": len(proposed_actions),
                "requires_human_approval": True,
            },
        )

    except Exception as exc:
        _error(state, "generate_maintenance_task", exc)

    return state


# ---------------------------------------------------------------------------
# NODE 10: PROCESS HUMAN APPROVAL
# ---------------------------------------------------------------------------

def process_approval(state: FactoryAgentState) -> FactoryAgentState:
    """
    Pause the workflow for human approval.

    The approval payload cannot establish physical identity. Identity must
    already have been verified through the trusted audit-backed endpoint.
    """

    existing_decision = state.get("approval_status")

    if existing_decision in ("approved", "rejected"):
        return state

    task_id = state.get("maintenance_task_id")

    if not task_id:
        return _error(
            state,
            "process_approval",
            "Cannot request approval: maintenance_task_id is missing.",
        )

    task = maintenance_service.get_task(task_id)

    if task is None:
        return _error(
            state,
            "process_approval",
            f"Maintenance task '{task_id}' was not found.",
        )

    task_payload = _serialize_task(task)

    recommendations = task_payload.get("recommended_actions", [])
    proposed_actions = state.get("action_plan") or []

    if not proposed_actions:
        proposed_actions = _format_proposed_actions(recommendations)

    task_payload["proposed_actions"] = _json_safe(proposed_actions)

    state["maintenance_task"] = task_payload
    state["maintenance_status"] = _task_status_value(task)
    state["action_plan"] = proposed_actions

    physical_identity_confirmed = (
        _has_valid_physical_identity_confirmation(state)
    )

    decision = interrupt(
        {
            "type": "maintenance_approval_required",
            "incident_id": state.get("incident_id"),
            "maintenance_task_id": str(task_id),
            "maintenance_task": _json_safe(task_payload),
            "proposed_actions": _json_safe(proposed_actions),
            "registry_match": _json_safe(
                state.get("registry_match") or {}
            ),
            "registry_match_status": state.get(
                "registry_match_status",
                "not_checked",
            ),
            "identifier_conflicts": _json_safe(
                state.get("equipment_identifier_conflicts") or []
            ),
            "registry_identifier_conflicts": _json_safe(
                state.get("identifier_conflicts") or []
            ),
            "physical_identity_confirmed": physical_identity_confirmed,
            "physical_verification_required": (
                not physical_identity_confirmed
            ),
            "message": (
                "Review the evidence and proposed maintenance task. "
                "A registry match is not physical identity verification. "
                "Confirm the physical equipment identity through the "
                "trusted verification workflow before approving "
                "asset-specific maintenance."
            ),
        }
    )

    if not isinstance(decision, dict):
        return _error(
            state,
            "process_approval",
            (
                "Invalid approval response. An explicit decision and "
                "reviewer identifier are required."
            ),
        )

    approval_status = (
        decision.get("approval_status")
        or decision.get("decision")
    )

    approval_user = (
        decision.get("approval_user")
        or decision.get("user")
    )

    approval_comment = (
        decision.get("approval_comment")
        or decision.get("comment")
        or ""
    )

    if approval_status not in ("approved", "rejected"):
        return _error(
            state,
            "process_approval",
            "Invalid approval decision. Use 'approved' or 'rejected'.",
        )

    if not isinstance(approval_user, str) or not approval_user.strip():
        return _error(
            state,
            "process_approval",
            "An approval user is required to record the decision.",
        )

    approval_user = approval_user.strip()

    # Recheck identity after the interrupt resumes.
    identity_is_verified = _has_valid_physical_identity_confirmation(
        state
    )

    if approval_status == "approved" and not identity_is_verified:
        return _error(
            state,
            "process_approval",
            (
                "Maintenance approval blocked: physical equipment identity "
                "must be confirmed through the trusted audit-backed "
                "verification workflow before approval."
            ),
        )

    target_status = (
        MaintenanceStatus.APPROVED
        if approval_status == "approved"
        else MaintenanceStatus.REJECTED
    )

    try:
        updated_task = maintenance_service.update_status(
            task_id,
            target_status,
        )

    except Exception as exc:
        return _error(
            state,
            "process_approval",
            f"Could not record the maintenance approval decision: {exc}",
        )

    if updated_task is None:
        return _error(
            state,
            "process_approval",
            f"Could not update maintenance task '{task_id}'.",
        )

    updated_task_payload = _serialize_task(updated_task)
    updated_task_payload["proposed_actions"] = _json_safe(
        proposed_actions
    )

    state["maintenance_task"] = updated_task_payload
    state["maintenance_status"] = _task_status_value(updated_task)
    state["approval_status"] = approval_status
    state["approval_user"] = approval_user
    state["approval_comment"] = str(approval_comment)
    state["requires_human_approval"] = False
    state["error"] = None

    if approval_status == "approved":
        state["status"] = "maintenance_approved"

        state["messages"] = _append_message(
            state,
            {
                "node": "process_approval",
                "status": "approved",
                "maintenance_task_id": str(task_id),
                "approval_user": approval_user,
                "note": (
                    "Maintenance was approved for the simulated workflow. "
                    "Approval does not certify that the equipment is safe."
                ),
            },
        )

    else:
        state["status"] = "maintenance_rejected"

        state["messages"] = _append_message(
            state,
            {
                "node": "process_approval",
                "status": "rejected",
                "maintenance_task_id": str(task_id),
                "approval_user": approval_user,
            },
        )

    return state


# ---------------------------------------------------------------------------
# NODE 11: START SIMULATED MAINTENANCE
# ---------------------------------------------------------------------------

def start_maintenance(state: FactoryAgentState) -> FactoryAgentState:
    """Start simulated maintenance only after approval and identity checks."""

    if state.get("approval_status") != "approved":
        state["status"] = "rejected"

        state["messages"] = _append_message(
            state,
            {
                "node": "start_maintenance",
                "status": "blocked",
                "reason": "Maintenance has not been approved.",
            },
        )

        return state

    if not _maintenance_identity_gate(state, "start_maintenance"):
        return state

    task_id = state.get("maintenance_task_id")

    if not task_id:
        return _error(
            state,
            "start_maintenance",
            "The maintenance task ID is missing.",
        )

    try:
        task = maintenance_service.get_task(task_id)

        if task is None:
            raise ValueError(
                f"Maintenance task '{task_id}' was not found."
            )

        if _task_status_value(task) != MaintenanceStatus.APPROVED.value:
            raise ValueError(
                "The canonical maintenance task has not been approved."
            )

        task = maintenance_service.update_status(
            task_id,
            MaintenanceStatus.IN_PROGRESS,
        )

        if task is None:
            raise ValueError(
                f"Could not start maintenance task '{task_id}'."
            )

        state["maintenance_task"] = _serialize_task(task)
        state["maintenance_status"] = _task_status_value(task)
        state["status"] = "maintenance_in_progress"
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "start_maintenance",
                "status": "success",
                "note": (
                    "Simulated maintenance only. This does not represent "
                    "physical work on equipment."
                ),
            },
        )

    except Exception as exc:
        _error(state, "start_maintenance", exc)

    return state


# ---------------------------------------------------------------------------
# NODE 12: COMPLETE SIMULATED MAINTENANCE
# ---------------------------------------------------------------------------

def complete_maintenance(state: FactoryAgentState) -> FactoryAgentState:
    """
    Complete simulated maintenance and generate simulated follow-up readings.

    These readings are not real sensor measurements.
    """

    task_id = state.get("maintenance_task_id")
    machine_id = state.get("machine_id")
    scenario_id = state.get("simulation_scenario_id")

    if not task_id:
        return _error(
            state,
            "complete_maintenance",
            "The maintenance task ID is missing.",
        )

    if not machine_id:
        return _error(
            state,
            "complete_maintenance",
            "The machine ID is missing.",
        )

    if state.get("approval_status") != "approved":
        return _error(
            state,
            "complete_maintenance",
            "Maintenance cannot be completed without human approval.",
        )

    if not _maintenance_identity_gate(state, "complete_maintenance"):
        return state

    if (
        state.get("maintenance_status")
        != MaintenanceStatus.IN_PROGRESS.value
    ):
        return _error(
            state,
            "complete_maintenance",
            "The task must be in progress before it can be completed.",
        )

    try:
        scenario = get_scenario(scenario_id) if scenario_id else None

        task = maintenance_service.get_task(task_id)

        if task is None:
            raise ValueError(
                f"Maintenance task '{task_id}' was not found."
            )

        if (
            _task_status_value(task)
            != MaintenanceStatus.IN_PROGRESS.value
        ):
            raise ValueError(
                "The canonical maintenance task is not in progress."
            )

        task = maintenance_service.update_status(
            task_id,
            MaintenanceStatus.COMPLETED,
        )

        if task is None:
            raise ValueError(
                f"Could not complete maintenance task '{task_id}'."
            )

        # Always update both the nested task and top-level task status.
        state["maintenance_task"] = _serialize_task(task)
        state["maintenance_status"] = _task_status_value(task)

        if scenario:
            if scenario.get("maintenance_will_resolve") is True:
                post_readings = {
                    "temperature_c": 55.0,
                    "vibration_mm_s": 2.0,
                    "pressure_bar": 4.0,
                    "moisture_percent": 45.0,
                }
            else:
                post_readings = dict(
                    scenario.get("sensor_readings", {})
                )

            state["post_maintenance_readings"] = {
                "machine_id": machine_id,
                **post_readings,
                "simulated": True,
                "scenario_id": scenario_id,
                "captured_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

        else:
            state["post_maintenance_readings"] = {
                "machine_id": machine_id,
                "simulated": True,
                "scenario_id": None,
                "note": (
                    "No scenario-specific follow-up readings were available."
                ),
            }

        state["status"] = "maintenance_completed"
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "complete_maintenance",
                "status": "success",
                "note": (
                    "Simulated maintenance is complete. Follow-up readings "
                    "are simulated evidence and must be evaluated by the "
                    "verification service. They do not certify equipment "
                    "as safe."
                ),
            },
        )

    except Exception as exc:
        _error(state, "complete_maintenance", exc)

    return state


# ---------------------------------------------------------------------------
# NODE 13: VERIFY MAINTENANCE
# ---------------------------------------------------------------------------

def verify_maintenance(state: FactoryAgentState) -> FactoryAgentState:
    """Verify the completed task against post-maintenance evidence."""

    try:
        if state.get("maintenance_status") != MaintenanceStatus.COMPLETED.value:
            raise ValueError(
                "Verification requires a completed maintenance task."
            )

        incident, task = _get_incident_and_task(state)

        post_readings = state.get("post_maintenance_readings")

        if not isinstance(post_readings, dict):
            raise ValueError(
                "Post-maintenance evidence must be a dictionary."
            )

        if post_readings.get("simulated") is not True:
            raise ValueError(
                "Post-maintenance evidence is missing its simulated marker."
            )

        if post_readings.get("machine_id") != state.get("machine_id"):
            raise ValueError(
                "Post-maintenance evidence does not match the current machine."
            )

        result = verification_service.verify(
            incident=incident,
            maintenance_task=task,
            post_maintenance_readings=post_readings,
        )

        result_data = _json_safe(_to_dict(result))

        if not isinstance(result_data, dict):
            raise TypeError(
                "Verification service returned an invalid result."
            )

        outcome = result_data.get("outcome")

        if isinstance(outcome, Enum):
            outcome = outcome.value

        resolved = outcome == VerificationOutcome.VERIFIED.value

        state["verification_result"] = {
            **result_data,
            "outcome": outcome,
            "evidence_simulated": True,
            "safety_certified": False,
        }

        state["resolved"] = resolved
        state["status"] = (
            "verification_completed"
            if resolved
            else "verification_failed"
        )
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "verify_maintenance",
                "status": "success",
                "outcome": outcome,
                "resolved": resolved,
                "note": (
                    "Passing configured checks does not certify "
                    "the equipment safe."
                ),
            },
        )

    except Exception as exc:
        state["verification_result"] = {
            "outcome": VerificationOutcome.INCONCLUSIVE.value,
            "summary": f"Verification could not be completed: {exc}",
            "requires_human_review": True,
            "evidence_simulated": True,
            "safety_certified": False,
        }

        state["resolved"] = False
        state["status"] = "verification_failed"
        state["error"] = str(exc)

        state["messages"] = _append_message(
            state,
            {
                "node": "verify_maintenance",
                "status": "error",
                "error": str(exc),
            },
        )

    return state


# ---------------------------------------------------------------------------
# NODE 14: CLOSE INCIDENT
# ---------------------------------------------------------------------------

def close_incident(state: FactoryAgentState) -> FactoryAgentState:
    """Resolve the incident only after successful verification."""

    if state.get("resolved") is not True:
        state["status"] = "verification_failed"

        state["messages"] = _append_message(
            state,
            {
                "node": "close_incident",
                "status": "blocked",
                "reason": "Verification did not confirm resolution.",
            },
        )

        return state

    try:
        incident_id = state.get("incident_id")

        if not incident_id:
            raise ValueError(
                "Cannot close incident without its ID."
            )

        incident = incident_service.get_incident(incident_id)

        if incident is None:
            raise ValueError(
                f"Incident '{incident_id}' could not be retrieved."
            )

        incident_service.update_status(
            incident_id,
            IncidentStatus.RESOLVED,
        )

        state["status"] = "incident_resolved"
        state["error"] = None

        state["messages"] = _append_message(
            state,
            {
                "node": "close_incident",
                "status": "success",
                "incident_id": incident_id,
                "safety_certified": False,
                "note": (
                    "The incident was resolved according to simulated "
                    "verification results. This does not certify the "
                    "equipment safe."
                ),
            },
        )

    except Exception as exc:
        _error(state, "close_incident", exc)

    return state


# ---------------------------------------------------------------------------
# NODE 15: ESCALATE INCIDENT
# ---------------------------------------------------------------------------

def escalate_incident(state: FactoryAgentState) -> FactoryAgentState:
    """Escalate an incident when resolution has not been established."""

    state["resolved"] = False
    state["status"] = "escalated"

    state["escalation"] = {
        "incident_id": state.get("incident_id"),
        "machine_id": state.get("machine_id"),
        "reason": (
            "Post-maintenance verification did not establish resolution, "
            "or the workflow could not safely complete."
        ),
        "verification_result": _json_safe(
            state.get("verification_result", {})
        ),
        "registry_match_status": state.get(
            "registry_match_status",
            "not_checked",
        ),
        "identifier_conflicts": _json_safe(
            state.get("equipment_identifier_conflicts", [])
        ),
        "registry_identifier_conflicts": _json_safe(
            state.get("identifier_conflicts", [])
        ),
        "requires_human_review": True,
        "safety_certified": False,
    }

    state["messages"] = _append_message(
        state,
        {
            "node": "escalate_incident",
            "status": "escalated",
        },
    )

    return state


# ---------------------------------------------------------------------------
# NODE 16: HANDLE ERRORS
# ---------------------------------------------------------------------------

def handle_error(state: FactoryAgentState) -> FactoryAgentState:
    """Record an unexpected workflow error without claiming resolution."""

    state["status"] = "error"
    state["resolved"] = False

    state.setdefault(
        "error",
        "An unexpected workflow error occurred.",
    )

    state["messages"] = _append_message(
        state,
        {
            "node": "handle_error",
            "status": "error",
            "error": state["error"],
        },
    )

    return state