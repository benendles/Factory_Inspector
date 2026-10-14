"""Pydantic schemas for Factory Inspector inspections."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InspectionCreate(BaseModel):
    """Fields accepted when starting an inspection."""

    machine_id: str = Field(min_length=1, max_length=120)

    sensor_readings: dict[str, Any] = Field(
        default_factory=dict,
        description="Sensor measurements collected for the inspection.",
    )

    image_evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="References and metadata for inspection images.",
    )


class InspectionUpdate(BaseModel):
    """Fields that may be updated during an inspection."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(
        default=None,
        pattern=r"^(received|processing|completed|failed)$",
    )
    sensor_readings: dict[str, Any] | None = None
    image_evidence: list[dict[str, Any]] | None = None
    findings: dict[str, Any] | None = None
    agent_trace: list[dict[str, Any]] | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class InspectionResponse(BaseModel):
    """Inspection returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    machine_id: str
    status: str
    sensor_readings: dict[str, Any]
    image_evidence: list[dict[str, Any]]
    findings: dict[str, Any]
    agent_trace: list[dict[str, Any]]
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None