from langgraph.types import Command

from app.agents.graph import build_factory_graph


def test_anomaly_requires_human_approval():
    graph = build_factory_graph()

    config = {
        "configurable": {
            "thread_id": "anomaly-test-001"
        }
    }

    initial_state = {
        "machine_id": "MACHINE-002",
        "sensor_readings": {
            "machine_id": "MACHINE-002",
            "temperature_c": 98.5,
            "vibration_mm_s": 12.4,
            "pressure_bar": 5.0,
            "moisture_percent": 40.0,
        },
    }

    print("\n--- Starting Factory Inspector ---")

    result = graph.invoke(initial_state, config=config)

    print("\n--- Workflow Paused for Review ---")
    print("Status:", result.get("status"))
    print("Incident ID:", result.get("incident_id"))
    print("Maintenance task ID:", result.get("maintenance_task_id"))
    print("Approval status:", result.get("approval_status"))
    print("Messages:", result.get("messages"))

    snapshot = graph.get_state(config)

    print("\n--- Pending Graph Tasks ---")
    print(snapshot.next)

    assert result.get("incident_id"), "An incident should be created."
    assert result.get("maintenance_task_id"), (
        "A maintenance task should be created."
    )
    assert snapshot.next, "The graph should pause for human approval."

    print("\nPASS: Anomaly detected and approval checkpoint reached.")

    print("\n--- Rejecting the Proposed Maintenance ---")

    result = graph.invoke(
        Command(
            resume={
                "approval_status": "rejected",
                "approval_user": "test-reviewer",
                "approval_comment": "Automated test: verify rejection flow.",
            }
        ),
        config=config,
    )

    print("Final status:", result.get("status"))
    print("Approval status:", result.get("approval_status"))
    print("Maintenance status:", result.get("maintenance_status"))
    print("Messages:", result.get("messages"))

    assert result.get("approval_status") == "rejected"
    assert result.get("maintenance_status") == "rejected"

    print("\nPASS: Rejected maintenance did not proceed.")


if __name__ == "__main__":
    test_anomaly_requires_human_approval()