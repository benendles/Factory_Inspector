"""Pydantic schemas for Factory Inspector incidents."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IncidentBase(BaseModel):
    """Fields shared by incident creation and responses."""

    machine_id: str = Field(
        min_length=1,
        max_length=120,
        description="Unique identifier of the registered machine.",
    )
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    severity: str = Field(
        default="medium",
        pattern=r"^(low|medium|high|critical)$",
    )
    visual_evidence: dict[str, Any] = Field(default_factory=dict)
    sensor_evidence: dict[str, Any] = Field(default_factory=dict)
    requires_human_review: bool = True


class IncidentCreate(IncidentBase):
    """Fields accepted when creating an incident."""

    inspection_id: UUID | None = None


class IncidentUpdate(BaseModel):
    """Fields that may be updated on an existing incident."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    severity: str | None = Field(
        default=None,
        pattern=r"^(low|medium|high|critical)$",
    )
    status: str | None = Field(
        default=None,
        pattern=r"^(open|investigating|awaiting_approval|"
                r"maintenance_in_progress|resolved|closed|escalated)$",
    )
    resolution_summary: str | None = None


class IncidentResponse(IncidentBase):
    """Incident returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_number: str
    inspection_id: UUID | None = None
    status: str
    resolution_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None