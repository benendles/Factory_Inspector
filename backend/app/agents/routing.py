from app.agents.state import FactoryAgentState


# =========================================================
# ROUTE AFTER DATA ACQUISITION
# =========================================================

def route_after_acquisition(
    state: FactoryAgentState,
) -> str:
    """Continue only when data acquisition succeeds."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "analyze_sensors"


# =========================================================
# ROUTE AFTER SENSOR ANALYSIS
# =========================================================

def route_after_sensor_analysis(
    state: FactoryAgentState,
) -> str:
    """Inspect the image if sensor analysis succeeded."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "inspect_image"


# =========================================================
# ROUTE AFTER IMAGE INSPECTION
# =========================================================

def route_after_image_inspection(
    state: FactoryAgentState,
) -> str:
    """Triage evidence, or stop if image inspection failed."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "triage_incident"


# =========================================================
# ROUTE AFTER TRIAGE
# =========================================================

def route_after_triage(
    state: FactoryAgentState,
) -> str:
    """Separate normal operation from anomaly investigation."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    if state.get("anomalies_detected", False):
        return "create_incident"

    return "log_normal_operation"


# =========================================================
# ROUTE AFTER INCIDENT CREATION
# =========================================================

def route_after_incident_creation(
    state: FactoryAgentState,
) -> str:
    """Continue only if an incident was created or retrieved."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    if not state.get("incident_id"):
        return "error"

    return "investigate_incident"


# =========================================================
# ROUTE AFTER INVESTIGATION
# =========================================================

def route_after_investigation(
    state: FactoryAgentState,
) -> str:
    """Proceed to maintenance planning when investigation succeeds."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "generate_maintenance_task"


# =========================================================
# ROUTE AFTER MAINTENANCE TASK CREATION
# =========================================================

def route_after_task_creation(
    state: FactoryAgentState,
) -> str:
    """Pause for approval or stop on an error."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "human_approval"


# =========================================================
# ROUTE AFTER HUMAN APPROVAL
# =========================================================

def route_after_approval(
    state: FactoryAgentState,
) -> str:
    """Determine whether the task can proceed."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    decision = state.get("approval_status", "pending")

    if decision == "approved":
        return "start_maintenance"

    if decision == "rejected":
        return "end"

    return "await_approval"


# =========================================================
# ROUTE AFTER MAINTENANCE STARTS
# =========================================================

def route_after_maintenance_start(
    state: FactoryAgentState,
) -> str:
    """Continue only when maintenance has started successfully."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "complete_maintenance"


# =========================================================
# ROUTE AFTER MAINTENANCE COMPLETION
# =========================================================

def route_after_maintenance_completion(
    state: FactoryAgentState,
) -> str:
    """Continue to verification only after task completion."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    return "verify_maintenance"


# =========================================================
# ROUTE AFTER VERIFICATION
# =========================================================

def route_after_verification(
    state: FactoryAgentState,
) -> str:
    """Choose incident closure or escalation."""

    if state.get("status") == "error" or state.get("error"):
        return "error"

    outcome = state.get("verification_result", {}).get("outcome")

    if outcome == "verified":
        return "close_incident"

    return "escalate_incident"