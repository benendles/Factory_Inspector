"""Pydantic schemas for registered equipment."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EquipmentCreate(BaseModel):
    """Request schema for registering equipment."""

    machine_id: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=255)
    manufacturer: str | None = Field(default=None, max_length=255)
    model_number: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    asset_tag: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    equipment_type: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias="metadata",
        validation_alias="metadata",
    )


class EquipmentUpdate(BaseModel):
    """Request schema for updating equipment."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    manufacturer: str | None = Field(default=None, max_length=255)
    model_number: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    asset_tag: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    equipment_type: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        serialization_alias="metadata",
        validation_alias="metadata",
    )


class EquipmentResponse(BaseModel):
    """Equipment returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    machine_id: str
    name: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    asset_tag: str | None = None
    location: str | None = None
    equipment_type: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime