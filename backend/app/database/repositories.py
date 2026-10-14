"""Database repositories for Factory Inspector.

These repositories handle PostgreSQL persistence through SQLAlchemy.
They do not commit automatically: transaction boundaries remain with
the caller so related database changes can be committed together.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Equipment,
    Incident,
    Inspection,
    MaintenanceTask,
    VerificationResult,
)


class EquipmentRepository:
    """Database operations for registered equipment."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, **data: Any) -> Equipment:
        equipment = Equipment(**data)
        self.db.add(equipment)
        self.db.flush()
        return equipment

    def get_by_id(self, equipment_id: UUID) -> Equipment | None:
        return self.db.get(Equipment, equipment_id)

    def get_by_machine_id(self, machine_id: str) -> Equipment | None:
        statement = select(Equipment).where(
            Equipment.machine_id == machine_id
        )
        return self.db.scalar(statement)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Equipment]:
        statement = (
            select(Equipment)
            .order_by(Equipment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(statement).all())

    def update(
        self,
        machine_id: str,
        **changes: Any,
    ) -> Equipment | None:
        equipment = self.get_by_machine_id(machine_id)

        if equipment is None:
            return None

        for field, value in changes.items():
            if field != "id" and hasattr(equipment, field):
                setattr(equipment, field, value)

        self.db.flush()
        return equipment

    def delete(self, machine_id: str) -> bool:
        equipment = self.get_by_machine_id(machine_id)

        if equipment is None:
            return False

        self.db.delete(equipment)
        self.db.flush()
        return True


class InspectionRepository:
    """Database operations for inspection runs."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, **data: Any) -> Inspection:
        inspection = Inspection(**data)
        self.db.add(inspection)
        self.db.flush()
        return inspection

    def get_by_id(self, inspection_id: UUID) -> Inspection | None:
        return self.db.get(Inspection, inspection_id)

    def list_all(
        self,
        machine_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Inspection]:
        statement = select(Inspection)

        if machine_id is not None:
            statement = statement.where(
                Inspection.machine_id == machine_id
            )

        statement = (
            statement
            .order_by(Inspection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(self.db.scalars(statement).all())

    def update(
        self,
        inspection_id: UUID,
        **changes: Any,
    ) -> Inspection | None:
        inspection = self.get_by_id(inspection_id)

        if inspection is None:
            return None

        for field, value in changes.items():
            if field not in {"id", "created_at"} and hasattr(
                inspection, field
            ):
                setattr(inspection, field, value)

        self.db.flush()
        return inspection


class IncidentRepository:
    """Database operations for incidents."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, **data: Any) -> Incident:
        incident = Incident(**data)
        self.db.add(incident)
        self.db.flush()
        return incident

    def get_by_id(self, incident_id: UUID) -> Incident | None:
        return self.db.get(Incident, incident_id)

    def get_by_number(self, incident_number: str) -> Incident | None:
        statement = select(Incident).where(
            Incident.incident_number == incident_number
        )
        return self.db.scalar(statement)

    def list_all(
        self,
        machine_id: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Incident]:
        statement = select(Incident)

        if machine_id is not None:
            statement = statement.where(
                Incident.machine_id == machine_id
            )

        if status is not None:
            statement = statement.where(Incident.status == status)

        if severity is not None:
            statement = statement.where(Incident.severity == severity)

        statement = (
            statement
            .order_by(Incident.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(self.db.scalars(statement).all())

    def update(
        self,
        incident_id: UUID,
        **changes: Any,
    ) -> Incident | None:
        incident = self.get_by_id(incident_id)

        if incident is None:
            return None

        for field, value in changes.items():
            if field not in {"id", "incident_number", "created_at"} and hasattr(
                incident, field
            ):
                setattr(incident, field, value)

        self.db.flush()
        return incident


class MaintenanceTaskRepository:
    """Database operations for maintenance tasks."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, **data: Any) -> MaintenanceTask:
        task = MaintenanceTask(**data)
        self.db.add(task)
        self.db.flush()
        return task

    def get_by_id(self, task_id: UUID) -> MaintenanceTask | None:
        return self.db.get(MaintenanceTask, task_id)

    def get_by_number(self, task_number: str) -> MaintenanceTask | None:
        statement = select(MaintenanceTask).where(
            MaintenanceTask.task_number == task_number
        )
        return self.db.scalar(statement)

    def list_all(
        self,
        incident_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MaintenanceTask]:
        statement = select(MaintenanceTask)

        if incident_id is not None:
            statement = statement.where(
                MaintenanceTask.incident_id == incident_id
            )

        if status is not None:
            statement = statement.where(
                MaintenanceTask.status == status
            )

        statement = (
            statement
            .order_by(MaintenanceTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(self.db.scalars(statement).all())

    def update(
        self,
        task_id: UUID,
        **changes: Any,
    ) -> MaintenanceTask | None:
        task = self.get_by_id(task_id)

        if task is None:
            return None

        protected_fields = {"id", "task_number", "incident_id", "created_at"}

        for field, value in changes.items():
            if field not in protected_fields and hasattr(task, field):
                setattr(task, field, value)

        self.db.flush()
        return task


class VerificationResultRepository:
    """Database operations for post-maintenance verification results."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, **data: Any) -> VerificationResult:
        # Verification results are historical evidence. Never allow callers
        # to claim that the result certifies the equipment as safe.
        data["safety_certified"] = False

        result = VerificationResult(**data)
        self.db.add(result)
        self.db.flush()
        return result

    def get_by_id(self, result_id: UUID) -> VerificationResult | None:
        return self.db.get(VerificationResult, result_id)

    def list_all(
        self,
        incident_id: UUID | None = None,
        maintenance_task_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VerificationResult]:
        statement = select(VerificationResult)

        if incident_id is not None:
            statement = statement.where(
                VerificationResult.incident_id == incident_id
            )

        if maintenance_task_id is not None:
            statement = statement.where(
                VerificationResult.maintenance_task_id
                == maintenance_task_id
            )

        statement = (
            statement
            .order_by(VerificationResult.verified_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return list(self.db.scalars(statement).all())