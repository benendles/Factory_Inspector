"""Equipment registration and retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.equipment import (
    EquipmentCreate,
    EquipmentResponse,
    EquipmentUpdate,
)
from app.database.repositories import EquipmentRepository
from app.database.session import get_db

router = APIRouter(prefix="/equipment", tags=["Equipment"])

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_equipment(
    payload: EquipmentCreate,
    db: DatabaseSession,
):
    """Register a machine in the equipment registry."""

    repository = EquipmentRepository(db)

    existing = repository.get_by_machine_id(payload.machine_id)

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A machine with this machine_id is already registered.",
        )

    equipment_data = payload.model_dump(
        by_alias=False,
        exclude_unset=True,
    )

    try:
        equipment = repository.create(**equipment_data)
        db.commit()
        db.refresh(equipment)
        return equipment

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Equipment could not be registered because of a conflict.",
        )


@router.get("", response_model=list[EquipmentResponse])
def list_equipment(
    db: DatabaseSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return registered equipment."""

    repository = EquipmentRepository(db)
    return repository.list_all(limit=limit, offset=offset)


@router.get(
    "/{machine_id}",
    response_model=EquipmentResponse,
)
def get_equipment(
    machine_id: str,
    db: DatabaseSession,
):
    """Retrieve equipment by its machine identifier."""

    repository = EquipmentRepository(db)
    equipment = repository.get_by_machine_id(machine_id)

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found.",
        )

    return equipment


@router.patch(
    "/{machine_id}",
    response_model=EquipmentResponse,
)
def update_equipment(
    machine_id: str,
    payload: EquipmentUpdate,
    db: DatabaseSession,
):
    """Update registered equipment details."""

    repository = EquipmentRepository(db)

    changes = payload.model_dump(
        by_alias=False,
        exclude_unset=True,
    )

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update.",
        )

    equipment = repository.get_by_machine_id(machine_id)

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found.",
        )

    try:
        updated = repository.update(machine_id, **changes)
        db.commit()
        db.refresh(updated)
        return updated

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Equipment could not be updated because of a conflict.",
        )