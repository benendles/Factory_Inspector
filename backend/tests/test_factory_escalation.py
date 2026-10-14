from langgraph.types import Command

from app.agents.graph import build_factory_graph


def test_approved_maintenance_with_persistent_anomalies():
    graph = build_factory_graph()

    config = {
        "configurable": {
            "thread_id": "escalation-test-001",
        }
    }

    initial_state = {
        "machine_id": "MACHINE-004",
        "sensor_readings": {
            "machine_id": "MACHINE-004",
            "temperature_c": 98.5,
            "vibration_mm_s": 12.4,
            "pressure_bar": 5.0,
            "moisture_percent": 40.0,
        },
        "post_maintenance_readings": {
            "machine_id": "MACHINE-004",
            "temperature_c": 95.0,
            "vibration_mm_s": 10.0,
            "pressure_bar": 5.0,
            "moisture_percent": 40.0,
        },
    }

    print("\n--- Starting Escalation Test ---")

    result = graph.invoke(initial_state, config=config)

    assert result.get("incident_id"), (
        "An incident should be created."
    )

    assert result.get("maintenance_task_id"), (
        "A maintenance task should be created."
    )

    assert graph.get_state(config).next, (
        "The workflow should pause for human approval."
    )

    print("Incident ID:", result.get("incident_id"))
    print("Maintenance task ID:", result.get("maintenance_task_id"))

    print("\n--- Approving Simulated Maintenance ---")

    result = graph.invoke(
        Command(
            resume={
                "approval_status": "approved",
                "approval_user": "test-reviewer",
                "approval_comment": (
                    "Approval for escalation-path testing."
                ),
            }
        ),
        config=config,
    )

    verification = result.get("verification_result", {})

    print("\n--- Escalation Results ---")
    print("Final status:", result.get("status"))
    print("Maintenance status:", result.get("maintenance_status"))
    print("Verification outcome:", verification.get("outcome"))
    print("Verification summary:", verification.get("summary"))
    print("Messages:", result.get("messages"))

    assert result.get("maintenance_status") == "completed", (
        "The simulated maintenance task should complete."
    )

    assert verification.get("outcome") == "escalation_required", (
        "Persistent critical anomalies should require escalation."
    )

    assert result.get("resolved") is False, (
        "The incident must not be marked resolved."
    )

    assert result.get("status") != "incident_resolved", (
        "The workflow must not close the incident as resolved."
    )

    print(
        "\nPASS: Persistent critical anomalies were escalated "
        "instead of being marked resolved."
    )


if __name__ == "__main__":
    test_approved_maintenance_with_persistent_anomalies()