from app.services.incident_service import (
    IncidentService,
    IncidentSeverity,
)
from app.services.maintenance_service import (
    MaintenanceService,
    MaintenanceStatus,
)


def main():
    incident_service = IncidentService()
    maintenance_service = MaintenanceService()

    # Create a critical incident from sensor evidence.
    incident = incident_service.create_incident(
        machine_id="MACHINE-001",
        sensor_evidence=[
            {
                "sensor": "temperature",
                "value": 98.5,
                "threshold": 90.0,
                "unit": "°C",
                "severity": "critical",
                "description": (
                    "Temperature exceeded the critical threshold."
                ),
            }
        ],
    )

    assert incident.severity == IncidentSeverity.CRITICAL

    # Test 1: Create a maintenance task.
    task = maintenance_service.create_task(incident)

    print("\nTEST 1: CREATE MAINTENANCE TASK")
    print(f"Task ID: {task.task_id}")
    print(f"Incident ID: {task.incident_id}")
    print(f"Machine ID: {task.machine_id}")
    print(f"Status: {task.status.value}")

    assert task.incident_id == incident.incident_id
    assert task.machine_id == incident.machine_id
    assert task.status == MaintenanceStatus.PENDING_APPROVAL
    assert task.requires_human_approval is True
    assert len(task.recommended_actions) > 0

    # Test 2: Prevent duplicate tasks.
    duplicate = maintenance_service.create_task(incident)

    print("\nTEST 2: DUPLICATE TASK PREVENTION")
    print(f"Original task: {task.task_id}")
    print(f"Returned task: {duplicate.task_id}")

    assert duplicate.task_id == task.task_id

    # Test 3: Retrieve the task.
    retrieved = maintenance_service.get_task(task.task_id)

    assert retrieved is task

    print("\nTEST 3: RETRIEVE TASK")
    print(f"Retrieved: {retrieved.task_id}")

    # Test 4: Reject starting work before approval.
    try:
        maintenance_service.update_status(
            task.task_id,
            MaintenanceStatus.IN_PROGRESS,
        )

    except ValueError as error:
        print("\nTEST 4: UNAPPROVED WORK REJECTED")
        print(error)

    else:
        raise AssertionError(
            "Maintenance started without approval."
        )

    # Test 5: Approve the task and then start work.
    maintenance_service.update_status(
        task.task_id,
        MaintenanceStatus.APPROVED,
    )

    maintenance_service.update_status(
        task.task_id,
        MaintenanceStatus.IN_PROGRESS,
    )

    assert task.status == MaintenanceStatus.IN_PROGRESS

    print("\nTEST 5: APPROVED WORK STARTED")
    print(f"Status: {task.status.value}")

    print("\nAll maintenance service tests passed!")


if __name__ == "__main__":
    main()