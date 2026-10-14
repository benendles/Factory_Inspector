"""API endpoints for factory incidents."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
)
from app.database.repositories import (
    IncidentRepository,
    InspectionRepository,
)
from app.database.session import get_db


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


def _generate_incident_number() -> str:
    """Generate a unique, human-readable incident reference."""
    return f"INC-{uuid4().hex[:10].upper()}"


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    payload: IncidentCreate,
    db: DatabaseSession,
):
    """Create an incident associated with registered equipment."""

    from app.database.repositories import EquipmentRepository

    equipment = EquipmentRepository(db).get_by_machine_id(
        payload.machine_id
    )

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment is not registered.",
        )

    if payload.inspection_id is not None:
        inspection = InspectionRepository(db).get_by_id(
            payload.inspection_id
        )

        if inspection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection not found.",
            )

        if inspection.machine_id != payload.machine_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The inspection belongs to a different machine."
                ),
            )

    repository = IncidentRepository(db)

    try:
        incident = repository.create(
            incident_number=_generate_incident_number(),
            machine_id=payload.machine_id,
            inspection_id=payload.inspection_id,
            title=payload.title,
            description=payload.description,
            severity=payload.severity,
            status="open",
            visual_evidence=payload.visual_evidence,
            sensor_evidence=payload.sensor_evidence,
            requires_human_review=payload.requires_human_review,
        )

        db.commit()
        db.refresh(incident)

        return incident

    except Exception:
        db.rollback()
        raise


@router.get(
    "",
    response_model=list[IncidentResponse],
)
def list_incidents(
    db: DatabaseSession,
    machine_id: str | None = None,
    incident_status: str | None = Query(
        default=None,
        alias="status",
    ),
    severity: str | None = Query(
        default=None,
        pattern=r"^(low|medium|high|critical)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List incidents, optionally filtered by machine, status, or severity."""

    return IncidentRepository(db).list_all(
        machine_id=machine_id,
        status=incident_status,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
)
def get_incident(
    incident_id: UUID,
    db: DatabaseSession,
):
    """Retrieve one incident by its database UUID."""

    incident = IncidentRepository(db).get_by_id(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found.",
        )

    return incident


@router.patch(
    "/{incident_id}",
    response_model=IncidentResponse,
)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: DatabaseSession,
):
    """Update permitted incident fields."""

    repository = IncidentRepository(db)
    incident = repository.get_by_id(incident_id)

    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        return incident

    try:
        updated_incident = repository.update(
            incident_id,
            **changes,
        )

        db.commit()
        db.refresh(updated_incident)

        return updated_incident

    except Exception:
        db.rollback()
        raise