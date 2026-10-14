"""API endpoints for human approval of maintenance tasks."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas.maintenance import (
    MaintenanceApprovalRequest,
    MaintenanceTaskResponse,
)
from app.database.repositories import MaintenanceTaskRepository
from app.database.session import get_db


router = APIRouter(
    prefix="/approvals",
    tags=["Maintenance Approvals"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/{task_id}",
    response_model=MaintenanceTaskResponse,
    status_code=status.HTTP_200_OK,
)
def decide_maintenance_approval(
    task_id: UUID,
    payload: MaintenanceApprovalRequest,
    db: DatabaseSession,
):
    """
    Approve or reject a pending maintenance task.

    This endpoint records a human decision. Approval does not
    itself execute physical maintenance or operate equipment.
    """

    repository = MaintenanceTaskRepository(db)

    # 1. Retrieve the task from the database.
    task = repository.get_by_id(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance task not found.",
        )

    # 2. Only pending tasks can receive an approval decision.
    if task.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This task is no longer awaiting approval. "
                f"Current status: {task.status}."
            ),
        )

    # 3. Record the decision and the human approver.
    decision = payload.decision

    changes = {
        "status": decision,
        "approval_user": payload.approval_user,
        "approval_comment": payload.approval_comment,
    }

    if decision == "approved":
        changes["approved_at"] = datetime.now(timezone.utc)

    try:
        updated_task = repository.update(
            task_id,
            **changes,
        )

        if updated_task is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance task not found.",
            )

        # 4. Persist the decision.
        db.commit()
        db.refresh(updated_task)

        return updated_task

    except HTTPException:
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the maintenance approval decision.",
        ) from exc