from langgraph.types import Command
from uuid import uuid4

from app.agents.graph import build_factory_graph


def test_approved_maintenance_and_verification():
    graph = build_factory_graph()

    config = {
        "configurable": {
            "thread_id": "approval-test-001",
        }
    }

    initial_state = {
        "machine_id": "MACHINE-003",
        "sensor_readings": {
            "machine_id": "MACHINE-003",
            "temperature_c": 98.5,
            "vibration_mm_s": 12.4,
            "pressure_bar": 5.0,
            "moisture_percent": 40.0,
        },
        "simulation_scenario_id": "overheating",
    }

    print("\n--- Starting Approval Workflow ---")

    result = graph.invoke(initial_state, config=config)

    print("Status:", result.get("status"))
    print("Incident ID:", result.get("incident_id"))
    print("Maintenance task ID:", result.get("maintenance_task_id"))

    snapshot = graph.get_state(config)

    assert result.get("incident_id"), (
        "An incident should be created."
    )

    assert result.get("maintenance_task_id"), (
        "A maintenance task should be created."
    )

    assert snapshot.next, (
        "The graph should pause for human approval."
    )

    assert result.get("approval_status") == "pending", (
        "Approval should initially be pending."
    )

    # Simulate the checkpoint state that the trusted identity-verification
    # endpoint writes after it has persisted an audit record. Direct graph
    # tests must not bypass the maintenance identity gate.
    registry_id = str(uuid4())
    graph.update_state(
        config,
        {
            "physical_identity_confirmed": True,
            "physical_verification_required": False,
            "registry_requires_physical_verification": False,
            "physical_identity_verified_registry_id": registry_id,
            "physical_identity_verification_audit_id": str(uuid4()),
            "physical_identity_verification_decision": "confirmed",
            "registry_match_status": "verified_match",
            "registry_match": {
                "status": "verified_match",
                "candidate": {"id": registry_id},
            },
            "equipment_identifier_conflicts": [],
            "identifier_conflicts": [],
        },
    )

    print("\n--- Approving Maintenance ---")

    result = graph.invoke(
        Command(
            resume={
                "approval_status": "approved",
                "approval_user": "test-reviewer",
                "approval_comment": (
                    "Automated integration test approval."
                ),
            }
        ),
        config=config,
    )

    print("\n--- Workflow Completed ---")
    print("Final status:", result.get("status"))
    print("Approval status:", result.get("approval_status"))
    print("Maintenance status:", result.get("maintenance_status"))
    print("Verification:", result.get("verification_result"))
    print("Messages:", result.get("messages"))

    assert result.get("approval_status") == "approved", (
        "The maintenance task should be approved."
    )

    assert result.get("maintenance_status") == "completed", (
        "The simulated maintenance should complete."
    )

    verification = result.get("verification_result", {})

    assert verification.get("outcome") == "verified", (
        "Fresh normal readings should pass the configured verification rules."
    )

    assert result.get("resolved") is True, (
        "The incident should resolve after successful verification."
    )

    assert result["post_maintenance_readings"]["temperature_c"] == 55.0
    assert result["post_maintenance_readings"]["simulated"] is True
    assert result["incident"]["status"] == "resolved"
    assert result["investigation"]["incident_details"]["status"] == (
        "resolved"
    )

    print(
        "\nPASS: Approved maintenance completed and "
        "the incident passed verification."
    )


if __name__ == "__main__":
    test_approved_maintenance_and_verification()
