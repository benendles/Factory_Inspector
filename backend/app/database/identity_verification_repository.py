from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EquipmentIdentityVerification


class EquipmentIdentityVerificationRepository:
    """
    SQL operations for equipment identity-verification audit records.

    Transaction commits and rollbacks are deliberately managed by the
    calling service or API route.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        thread_id: str,
        decision: str,
        reviewer: str,
        equipment_id: UUID | None = None,
        machine_id: str | None = None,
        evidence: dict | None = None,
        comment: str = "",
    ) -> EquipmentIdentityVerification:
        record = EquipmentIdentityVerification(
            thread_id=thread_id,
            equipment_id=equipment_id,
            machine_id=machine_id,
            decision=decision,
            reviewer=reviewer,
            evidence=evidence or {},
            comment=comment,
        )

        self.db.add(record)

        # Populate generated values where possible, but do not commit.
        self.db.flush()

        return record

    def get_by_id(
        self,
        verification_id: UUID,
    ) -> EquipmentIdentityVerification | None:
        statement = select(EquipmentIdentityVerification).where(
            EquipmentIdentityVerification.id == verification_id
        )

        return self.db.scalar(statement)

    def list_for_thread(
        self,
        thread_id: str,
        limit: int = 100,
    ) -> list[EquipmentIdentityVerification]:
        safe_limit = max(1, min(limit, 500))

        statement = (
            select(EquipmentIdentityVerification)
            .where(
                EquipmentIdentityVerification.thread_id == thread_id
            )
            .order_by(
                EquipmentIdentityVerification.created_at.desc()
            )
            .limit(safe_limit)
        )

        return list(self.db.scalars(statement).all())