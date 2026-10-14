"""API endpoints for factory inspections."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas.inspection import (
    InspectionCreate,
    InspectionResponse,
)
from app.database.repositories import (
    EquipmentRepository,
    InspectionRepository,
)
from app.database.session import get_db
from app.services.sensor_analysis import (
    SensorAnalysisService,
    SensorReadings,
)

router = APIRouter(prefix="/inspections", tags=["Inspections"])

DatabaseSession = Annotated[Session, Depends(get_db)]


def _analyze_sensor_readings(
    machine_id: str,
    sensor_readings: dict,
) -> dict:
    """
    Analyze sensor readings when all required measurements are present.

    Thresholds are illustrative simulation thresholds, not universal
    industrial safety limits.
    """

    required_fields = {
        "temperature_c",
        "vibration_mm_s",
        "pressure_bar",
        "moisture_percent",
    }

    # An inspection can contain images or partial sensor readings.
    # Do not pretend to have completed sensor analysis if measurements
    # required by the existing service are missing.
    if not required_fields.issubset(sensor_readings.keys()):
        return {
            "sensor_analysis": {
                "status": "not_performed",
                "reason": "Required sensor measurements are incomplete.",
                "required_fields": sorted(required_fields),
            }
        }

    try:
        readings = SensorReadings(
            machine_id=machine_id,
            temperature_c=sensor_readings["temperature_c"],
            vibration_mm_s=sensor_readings["vibration_mm_s"],
            pressure_bar=sensor_readings["pressure_bar"],
            moisture_percent=sensor_readings["moisture_percent"],
        )

        result = SensorAnalysisService().analyze(readings)

    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sensor readings: {exc}",
        ) from exc

    return {
        "sensor_analysis": {
            "status": result.status,
            "summary": result.summary,
            "anomalies": [
                {
                    "sensor": anomaly.sensor,
                    "value": anomaly.value,
                    "threshold": anomaly.threshold,
                    "unit": anomaly.unit,
                    "severity": anomaly.severity,
                    "description": anomaly.description,
                }
                for anomaly in result.anomalies
            ],
            "thresholds_are_simulated": True,
        }
    }


@router.post(
    "",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inspection(
    payload: InspectionCreate,
    db: DatabaseSession,
):
    """Create an inspection for registered equipment."""

    equipment_repository = EquipmentRepository(db)
    equipment = equipment_repository.get_by_machine_id(
        payload.machine_id
    )

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment is not registered.",
        )

    sensor_readings = payload.sensor_readings

    findings = _analyze_sensor_readings(
        machine_id=payload.machine_id,
        sensor_readings=sensor_readings,
    )

    if payload.image_evidence:
        findings["image_analysis"] = {
            "status": "not_performed",
            "reason": (
                "Image evidence was recorded, but visual analysis "
                "has not been executed by this endpoint."
            ),
        }

    inspection_repository = InspectionRepository(db)

    try:
        inspection = inspection_repository.create(
            machine_id=payload.machine_id,
            status="completed",
            sensor_readings=sensor_readings,
            image_evidence=payload.image_evidence,
            findings=findings,
            agent_trace=[
                {
                    "step": "equipment_validation",
                    "status": "completed",
                    "machine_id": payload.machine_id,
                },
                {
                    "step": "sensor_analysis",
                    "status": findings["sensor_analysis"]["status"],
                },
            ],
            error_message=None,
            completed_at=datetime.now(timezone.utc),
        )

        db.commit()
        db.refresh(inspection)

        return inspection

    except Exception:
        db.rollback()
        raise


@router.get(
    "",
    response_model=list[InspectionResponse],
)
def list_inspections(
    db: DatabaseSession,
    machine_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List inspections, optionally filtered by machine."""

    repository = InspectionRepository(db)

    return repository.list_all(
        machine_id=machine_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{inspection_id}",
    response_model=InspectionResponse,
)
def get_inspection(
    inspection_id: UUID,
    db: DatabaseSession,
):
    """Retrieve an inspection by its UUID."""

    repository = InspectionRepository(db)

    inspection = repository.get_by_id(inspection_id)

    if inspection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found.",
        )

    return inspection