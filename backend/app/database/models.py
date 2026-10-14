from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all Factory Inspector database models."""


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    machine_id: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(255))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    model_number: Mapped[str | None] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(255))
    asset_tag: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    equipment_type: Mapped[str | None] = mapped_column(String(120))

    # Records the source and confidence of registry information.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="equipment",
    )


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    machine_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("equipment.machine_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="received",
        nullable=False,
    )
    sensor_readings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    image_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    findings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    agent_trace: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    equipment: Mapped["Equipment"] = relationship(
        back_populates="inspections",
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="inspection",
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    incident_number: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
    )
    machine_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("equipment.machine_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    inspection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("inspections.id", ondelete="SET NULL"),
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(
        String(40),
        default="medium",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="open",
        nullable=False,
    )
    visual_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    sensor_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    inspection: Mapped["Inspection | None"] = relationship(
        back_populates="incidents",
    )
    maintenance_tasks: Mapped[list["MaintenanceTask"]] = relationship(
        back_populates="incident",
    )
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        back_populates="incident",
    )


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    task_number: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        index=True,
        nullable=False,
    )
    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending_approval",
        nullable=False,
    )
    proposed_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    approval_user: Mapped[str | None] = mapped_column(String(255))
    approval_comment: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        back_populates="maintenance_tasks",
    )
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        back_populates="maintenance_task",
    )


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    maintenance_task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("maintenance_tasks.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # A positive result is not a certification that equipment is safe.
    safety_certified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        back_populates="verification_results",
    )
    maintenance_task: Mapped["MaintenanceTask"] = relationship(
        back_populates="verification_results",
    )


Index("ix_incidents_status_severity", Incident.status, Incident.severity)
Index("ix_inspections_created_at", Inspection.created_at)
Index("ix_maintenance_tasks_status", MaintenanceTask.status)
class EquipmentIdentityVerification(Base):
    """
    Audit record for a human review of an equipment identity candidate.

    This records a review decision. It does not certify equipment as safe,
    and it does not automatically update LangGraph workflow state.
    """

    __tablename__ = "equipment_identity_verifications"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # LangGraph thread ID is a UUID string, not an SQL workflow-row ID.
    thread_id: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
    )

    # Reference the SQL equipment record, when a candidate exists.
    equipment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("equipment.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    # Store the identifier used to look up the candidate.
    machine_id: Mapped[str | None] = mapped_column(
        String(120),
        index=True,
        nullable=True,
    )

    # Identity decisions are separate from maintenance approval.
    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Reviewer is free-text for this demo because authentication is not
    # currently configured. This field is NOT proof of reviewer identity.
    reviewer: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Evidence should document what the reviewer examined.
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Optional reviewer explanation.
    comment: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )