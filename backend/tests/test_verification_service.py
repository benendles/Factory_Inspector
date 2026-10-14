from app.services.incident_service import IncidentService
from app.services.maintenance_service import (
    MaintenanceService,
    MaintenanceStatus,
)
from app.services.verification_service import (
    VerificationService,
    VerificationOutcome,
)


def main():
    incident_service = IncidentService()
    maintenance_service = MaintenanceService()
    verification_service = VerificationService()

    # --------------------------------------------------
    # Create an incident caused by excessive temperature.
    # --------------------------------------------------
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

    task = maintenance_service.create_task(incident)

    # --------------------------------------------------
    # Simulate approval, work, and completion.
    # Each transition happens exactly once.
    # --------------------------------------------------
    maintenance_service.update_status(
        task.task_id,
        MaintenanceStatus.APPROVED,
    )

    maintenance_service.update_status(
        task.task_id,
        MaintenanceStatus.IN_PROGRESS,
    )

    maintenance_service.update_status(
        task.task_id,
        MaintenanceStatus.COMPLETED,
    )

    # --------------------------------------------------
    # TEST 1: Anomaly resolved.
    # Expected outcome: VERIFIED
    # --------------------------------------------------
    recovered_readings = {
        "machine_id": "MACHINE-001",
        "temperature_c": 55.0,
        "vibration_mm_s": 2.0,
        "pressure_bar": 5.0,
        "moisture_percent": 50.0,
    }

    result = verification_service.verify(
        incident,
        task,
        recovered_readings,
    )

    print("\nTEST 1: RECOVERY")
    print(f"Outcome: {result.outcome.value}")
    print(f"Summary: {result.summary}")

    assert result.outcome == VerificationOutcome.VERIFIED

    # --------------------------------------------------
    # TEST 2: Original anomaly remains.
    # Expected outcome: ESCALATION_REQUIRED
    # --------------------------------------------------
    abnormal_readings = {
        "machine_id": "MACHINE-001",
        "temperature_c": 95.0,
        "vibration_mm_s": 2.0,
        "pressure_bar": 5.0,
        "moisture_percent": 50.0,
    }

    result = verification_service.verify(
        incident,
        task,
        abnormal_readings,
    )

    print("\nTEST 2: ANOMALY REMAINS")
    print(f"Outcome: {result.outcome.value}")
    print(f"Summary: {result.summary}")

    assert result.outcome == VerificationOutcome.ESCALATION_REQUIRED

    # --------------------------------------------------
    # TEST 3: No post-maintenance evidence.
    # Expected outcome: INCONCLUSIVE
    # --------------------------------------------------
    result = verification_service.verify(
        incident,
        task,
        None,
    )

    print("\nTEST 3: MISSING EVIDENCE")
    print(f"Outcome: {result.outcome.value}")

    assert result.outcome == VerificationOutcome.INCONCLUSIVE

    # --------------------------------------------------
    # TEST 4: Readings belong to the wrong machine.
    # Expected: ValueError
    # --------------------------------------------------
    try:
        verification_service.verify(
            incident,
            task,
            {
                **recovered_readings,
                "machine_id": "MACHINE-999",
            },
        )

    except ValueError as error:
        print("\nTEST 4: WRONG MACHINE REJECTED")
        print(error)

    else:
        raise AssertionError(
            "Readings from the wrong machine were accepted."
        )

    # --------------------------------------------------
    # TEST 5: Verification before maintenance completion.
    # Expected: ValueError
    # --------------------------------------------------
    second_incident = incident_service.create_incident(
        machine_id="MACHINE-002",
        sensor_evidence=[
            {
                "sensor": "vibration",
                "value": 9.0,
                "threshold": 7.1,
                "unit": "mm/s",
                "severity": "critical",
                "description": (
                    "Vibration exceeded the critical threshold."
                ),
            }
        ],
    )

    incomplete_task = maintenance_service.create_task(
        second_incident
    )

    try:
        verification_service.verify(
            second_incident,
            incomplete_task,
            {
                "machine_id": "MACHINE-002",
                "temperature_c": 50.0,
                "vibration_mm_s": 2.0,
                "pressure_bar": 5.0,
                "moisture_percent": 50.0,
            },
        )

    except ValueError as error:
        print("\nTEST 5: INCOMPLETE MAINTENANCE REJECTED")
        print(error)

    else:
        raise AssertionError(
            "Verification was allowed before maintenance completion."
        )

    print("\nAll verification service tests passed!")


if __name__ == "__main__":
    main()