from app.services.incident_service import (
    IncidentService,
    IncidentSeverity,
    IncidentStatus,
)


def main():
    service = IncidentService()

    # Test 1: Create an incident from sensor evidence.
    sensor_evidence = [
        {
            "sensor": "temperature",
            "value": 98.5,
            "threshold": 90.0,
            "unit": "°C",
            "severity": "critical",
            "description": "Temperature exceeded the critical threshold.",
        }
    ]

    incident = service.create_incident(
        machine_id="MACHINE-001",
        sensor_evidence=sensor_evidence,
    )

    print("\nTEST 1: CREATE INCIDENT")
    print(incident)

    assert incident.machine_id == "MACHINE-001"
    assert incident.severity == IncidentSeverity.CRITICAL
    assert incident.status == IncidentStatus.OPEN
    assert incident.requires_human_review is True

    # Test 2: Retrieve the incident.
    retrieved = service.get_incident(incident.incident_id)

    assert retrieved is incident

    print("\nTEST 2: RETRIEVE INCIDENT")
    print(f"Retrieved: {retrieved.incident_id}")

    # Test 3: Duplicate evidence should reuse the active incident.
    duplicate = service.create_incident(
        machine_id="MACHINE-001",
        sensor_evidence=sensor_evidence,
    )

    assert duplicate.incident_id == incident.incident_id

    print("\nTEST 3: DUPLICATE DETECTION")
    print(f"Reused incident: {duplicate.incident_id}")

    # Test 4: Update the incident status.
    updated = service.update_status(
        incident.incident_id,
        IncidentStatus.INVESTIGATING,
    )

    assert updated.status == IncidentStatus.INVESTIGATING

    print("\nTEST 4: UPDATE STATUS")
    print(f"Status: {updated.status.value}")

    # Test 5: Reject an incident with no evidence.
    try:
        service.create_incident(
            machine_id="MACHINE-002",
        )

    except ValueError as error:
        print("\nTEST 5: EMPTY EVIDENCE REJECTED")
        print(error)

    else:
        raise AssertionError("Incident without evidence was accepted.")

    print("\nAll incident service tests passed!")


if __name__ == "__main__":
    main()