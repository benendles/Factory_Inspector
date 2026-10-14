from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.services.incident_service import Incident
from app.services.maintenance_service import MaintenanceTask, MaintenanceStatus


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"
    NOT_RESOLVED = "not_resolved"
    INCONCLUSIVE = "inconclusive"
    ESCALATION_REQUIRED = "escalation_required"


@dataclass
class VerificationResult:
    verification_id: str
    incident_id: str
    machine_id: str
    outcome: VerificationOutcome
    summary: str
    evidence: list[dict] = field(default_factory=list)
    requires_human_review: bool = True
    verified_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class VerificationService:
    """
    Evaluate whether post-maintenance evidence meets recovery criteria.

    This initial version verifies sensor conditions only.
    Visual verification and equipment-specific recovery criteria
    will be added later.
    """

    def verify(
        self,
        incident: Incident,
        maintenance_task: MaintenanceTask,
        post_maintenance_readings: dict | None,
    ) -> VerificationResult:
        if maintenance_task.incident_id != incident.incident_id:
            raise ValueError(
                "Maintenance task does not belong to this incident."
            )

        if maintenance_task.machine_id != incident.machine_id:
            raise ValueError(
                "Maintenance task machine does not match the incident."
            )

        if maintenance_task.status != MaintenanceStatus.COMPLETED:
            raise ValueError(
                "Verification requires a completed maintenance task."
            )

        evidence = []

        # Without new measurements, we cannot claim recovery.
        if not post_maintenance_readings:
            return VerificationResult(
                verification_id=f"VER-{uuid4().hex[:8].upper()}",
                incident_id=incident.incident_id,
                machine_id=incident.machine_id,
                outcome=VerificationOutcome.INCONCLUSIVE,
                summary=(
                    "No post-maintenance readings were provided. "
                    "Recovery cannot be verified."
                ),
            )

        if post_maintenance_readings.get("machine_id") != incident.machine_id:
            raise ValueError(
                "Post-maintenance readings belong to a different machine."
            )

        # Identify which sensors were abnormal in the original incident.
        original_sensor_names = {
            str(item.get("sensor", "")).lower()
            for item in incident.sensor_evidence
        }

        if not original_sensor_names:
            return VerificationResult(
                verification_id=f"VER-{uuid4().hex[:8].upper()}",
                incident_id=incident.incident_id,
                machine_id=incident.machine_id,
                outcome=VerificationOutcome.INCONCLUSIVE,
                summary=(
                    "The incident contains no sensor evidence. "
                    "This version cannot verify a visual-only incident."
                ),
            )

        # Re-run the deterministic sensor rules against the new readings.
        from app.services.sensor_analysis import (
            SensorAnalysisService,
            SensorReadings,
        )

        try:
            readings = SensorReadings(
                machine_id=post_maintenance_readings["machine_id"],
                temperature_c=post_maintenance_readings["temperature_c"],
                vibration_mm_s=post_maintenance_readings["vibration_mm_s"],
                pressure_bar=post_maintenance_readings["pressure_bar"],
                moisture_percent=post_maintenance_readings["moisture_percent"],
            )
        except KeyError as error:
            raise ValueError(
                f"Missing post-maintenance reading: {error.args[0]}"
            ) from error

        analysis = SensorAnalysisService().analyze(readings)

        # Only anomalies related to the original incident determine
        # whether that particular problem has been resolved.
        remaining_anomalies = [
            anomaly
            for anomaly in analysis.anomalies
            if anomaly.sensor in original_sensor_names
        ]

        for sensor in original_sensor_names:
            matching = [
                anomaly for anomaly in remaining_anomalies
                if anomaly.sensor == sensor
            ]

            evidence.append(
                {
                    "sensor": sensor,
                    "resolved": not matching,
                    "remaining_anomalies": [
                        {
                            "value": anomaly.value,
                            "threshold": anomaly.threshold,
                            "unit": anomaly.unit,
                            "severity": anomaly.severity,
                        }
                        for anomaly in matching
                    ],
                }
            )

        if any(
            anomaly.severity == "critical"
            for anomaly in remaining_anomalies
        ):
            outcome = VerificationOutcome.ESCALATION_REQUIRED
            summary = (
                "A critical anomaly remains after maintenance. "
                "Escalation and qualified human assessment are required."
            )

        elif remaining_anomalies:
            outcome = VerificationOutcome.NOT_RESOLVED
            summary = (
                "One or more original sensor anomalies remain. "
                "Further investigation is required."
            )

        else:
            outcome = VerificationOutcome.VERIFIED
            summary = (
                "The original sensor anomalies are no longer detected "
                "by the configured analysis rules. This does not, by "
                "itself, certify that the equipment is safe."
            )

        return VerificationResult(
            verification_id=f"VER-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            machine_id=incident.machine_id,
            outcome=outcome,
            summary=summary,
            evidence=evidence,
            requires_human_review=True,
        )