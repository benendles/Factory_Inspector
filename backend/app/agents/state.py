from typing import Any, Literal
from typing_extensions import TypedDict


class FactoryAgentState(TypedDict, total=False):
    """
    Shared state passed between nodes in the Factory Inspector LangGraph.

    Nodes read the fields they need and return dictionaries containing
    only the fields they update.
    """

    # 1. Initial factory inspection input

    machine_id: str
    sensor_readings: dict[str, Any]
    image_path: str | None
    timestamp: str

    # 2. Simulation workflow metadata

    simulation_scenario_id: str
    thread_id: str

    # 3. Sensor and vision analysis

    sensor_analysis: dict[str, Any]
    vision_analysis: dict[str, Any]

    # Public metadata about submitted inspection evidence. ``image_path`` is
    # an internal, short-lived processing path and must not be returned.
    image_evidence: dict[str, Any]
    image_inspection_result: dict[str, Any]
    nameplate_ocr_result: dict[str, Any]
    evidence_reconciliation: dict[str, Any]

    # Nodes store detected anomaly records in this field.
    anomalies_detected: list[dict[str, Any]] | bool
    severity: str

    # 4. Equipment identification and registry lookup

    equipment_identification: dict[str, Any]
    registry_match: dict[str, Any]

    registry_match_status: Literal[
        "verified_match",
        "possible_match",
        "no_match",
        "not_checked",
        "error",
    ]

    registry_asset_id: str | None
    registry_requires_physical_verification: bool

    # Identifier conflicts reported during equipment identification.
    # Both fields must be declared so LangGraph can persist them.
    equipment_identifier_conflicts: list[dict[str, Any]]
    identifier_conflicts: list[dict[str, Any]]

    # Physical identity verification

    physical_identity_confirmed: bool
    physical_verification_required: bool
    physical_identity_verified_registry_id: str | None
    physical_identity_verification_audit_id: str | None

    physical_identity_verification_decision: Literal[
        "confirmed",
        "rejected",
    ] | None

    # 5. Incident management

    incident_id: str
    incident: dict[str, Any]
    incident_created: bool
    # IDs of durable records created for this workflow. They are separate
    # from the human-readable incident/task identifiers above.
    incident_database_id: str | None

    # Advisory output from the external Evolus Digital Maintenance Foreman.
    # This is never an approval, work order state, or safety certification.
    evolus_maintenance_assessment: dict[str, Any]
    # Evidence supplied to Evolus for auditability and dashboard display.
    # This contains observations/candidates, never a physical identity claim.
    evolus_evidence_context: dict[str, Any]

    # 6. Investigation and maintenance planning

    investigation: dict[str, Any]
    action_plan: list[dict[str, Any]]

    maintenance_task_id: str
    maintenance_task_database_id: str | None
    maintenance_task: dict[str, Any]
    maintenance_task_description: str
    maintenance_status: str
    repair_plan: dict[str, Any]

    # 7. Human approval

    requires_human_approval: bool

    approval_status: Literal[
        "pending",
        "approved",
        "rejected",
    ]

    approval_user: str
    approval_comment: str

    # 8. Maintenance verification

    post_maintenance_readings: dict[str, Any]
    verification_result: dict[str, Any]
    verification_result_database_id: str | None
    resolved: bool

    # 9. Workflow control

    status: str
    error: str | None
    messages: list[str]
