"""Regression coverage for incident severity during active-incident reuse."""

from app.services.incident_service import IncidentService, IncidentSeverity


def test_reused_critical_sensor_incident_remains_critical_with_visual_evidence():
    service = IncidentService()
    visual_evidence = [{
        "anomaly_type": "surface_contamination",
        "description": "Dust is visible around the cooling fins.",
    }]
    sensor_evidence = [{
        "sensor": "temperature",
        "value": 95.0,
        "threshold": 90.0,
        "severity": "critical",
        "description": "Temperature exceeds the critical simulated threshold.",
    }]

    created = service.create_incident(
        machine_id="MACHINE-CRITICAL-001",
        visual_evidence=visual_evidence,
        sensor_evidence=sensor_evidence,
    )
    reused = service.create_incident(
        machine_id="MACHINE-CRITICAL-001",
        visual_evidence=visual_evidence,
        sensor_evidence=sensor_evidence,
    )

    assert reused.incident_id == created.incident_id
    assert reused.severity == IncidentSeverity.CRITICAL
