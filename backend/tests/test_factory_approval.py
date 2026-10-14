from langgraph.types import Command

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
        "post_maintenance_readings": {
            "machine_id": "MACHINE-003",
            "temperature_c": 45.0,
            "vibration_mm_s": 2.0,
            "pressure_bar": 5.0,
            "moisture_percent": 40.0,
        },
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

    print(
        "\nPASS: Approved maintenance completed and "
        "the incident passed verification."
    )


if __name__ == "__main__":
    test_approved_maintenance_and_verification()