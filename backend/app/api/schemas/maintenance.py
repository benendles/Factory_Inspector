"""Pydantic schemas for Factory Inspector maintenance tasks."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceTaskCreate(BaseModel):
    """Fields accepted when creating a maintenance task."""

    incident_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    proposed_actions: list[dict[str, Any]] = Field(
        default_factory=list,
    )


class MaintenanceApprovalRequest(BaseModel):
    """Human decision on a proposed maintenance task."""

    decision: str = Field(pattern=r"^(approved|rejected)$")
    approval_user: str = Field(min_length=1, max_length=255)
    approval_comment: str | None = None


class MaintenanceTaskResponse(BaseModel):
    """Maintenance task returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_number: str
    incident_id: UUID
    title: str
    description: str
    status: str
    proposed_actions: list[dict[str, Any]]
    approval_user: str | None = None
    approval_comment: str | None = None
    approved_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime