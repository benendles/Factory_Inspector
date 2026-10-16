"""Persist workflow artifacts without granting them execution authority."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.database.repositories import (
    IncidentRepository,
    MaintenanceTaskRepository,
    VerificationResultRepository,
)
from app.database.session import SessionLocal


def _enabled() -> bool:
    return os.getenv(
        "WORKFLOW_ARTIFACT_PERSISTENCE", "true"
    ).strip().casefold() not in {"0", "false", "no", "off"}


class WorkflowArtifactStore:
    """Small transaction boundary for workflow-created SQL records.

    The LangGraph state remains the orchestration source of truth. These rows
    provide durable task and verification history for the registry/API and
    are never used to bypass either human approval gate.
    """

    def persist_incident(self, incident: dict[str, Any]) -> str | None:
        if not _enabled():
            return None

        incident_number = str(incident["incident_id"])
        with SessionLocal() as db:
            repository = IncidentRepository(db)
            row = repository.get_by_number(incident_number)
            data = {
                "machine_id": str(incident["machine_id"]),
                "title": str(incident["title"]),
                "description": str(incident.get("description") or ""),
                "severity": str(incident["severity"]),
                "status": str(incident["status"]),
                "visual_evidence": list(incident.get("visual_evidence") or []),
                "sensor_evidence": list(incident.get("sensor_evidence") or []),
                "requires_human_review": bool(
                    incident.get("requires_human_review", True)
                ),
            }
            if row is None:
                row = repository.create(
                    incident_number=incident_number,
                    **data,
                )
            else:
                row = repository.update(row.id, **data)
            db.commit()
            return str(row.id)

    def persist_task(
        self,
        task: dict[str, Any],
        *,
        incident_database_id: str | None,
        approval_user: str | None = None,
        approval_comment: str | None = None,
    ) -> str | None:
        if not _enabled():
            return None
        if not incident_database_id:
            raise ValueError("Maintenance task persistence requires a database incident ID.")

        status = str(task.get("status") or "pending_approval")
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            repository = MaintenanceTaskRepository(db)
            row = repository.get_by_number(str(task["task_id"]))
            data: dict[str, Any] = {
                "title": str(task.get("title") or "Maintenance investigation"),
                "description": str(task.get("problem") or ""),
                "status": status,
                "proposed_actions": list(task.get("proposed_actions") or task.get("recommended_actions") or []),
            }
            if status == "approved":
                data["approved_at"] = now
            elif status == "in_progress":
                data["started_at"] = now
            elif status == "completed":
                data["completed_at"] = now

            if approval_user:
                data["approval_user"] = approval_user
                data["approval_comment"] = approval_comment or ""

            if row is None:
                row = repository.create(
                    task_number=str(task["task_id"]),
                    incident_id=UUID(incident_database_id),
                    **data,
                )
            else:
                row = repository.update(row.id, **data)
            db.commit()
            return str(row.id)

    def load_task_payload(
        self,
        maintenance_task_database_id: str | None,
        *,
        incident_id: str | None,
        machine_id: str | None,
    ) -> dict[str, Any]:
        """Return a checkpoint-compatible task payload from the SQL row.

        This fallback is used only for checkpoints made before the nested
        ``maintenance_task`` field was part of the graph schema. It restores
        display/resume data; it does not alter task status or approval state.
        """

        if not _enabled() or not maintenance_task_database_id:
            return {}

        try:
            task_uuid = UUID(maintenance_task_database_id)
        except (TypeError, ValueError):
            return {}

        with SessionLocal() as db:
            row = MaintenanceTaskRepository(db).get_by_id(task_uuid)
            if row is None:
                return {}

            recommendations = []
            for action in row.proposed_actions or []:
                if not isinstance(action, dict):
                    continue
                description = action.get("reason") or action.get("description")
                recommendations.append({
                    "action": action.get("action"),
                    "reason": description or action.get("action"),
                    "priority": action.get("priority", "medium"),
                    "requires_qualified_technician": action.get(
                        "requires_qualified_technician", True
                    ),
                })

            return {
                "task_id": row.task_number,
                "incident_id": incident_id or "",
                "machine_id": machine_id or "",
                "title": row.title,
                "problem": row.description,
                "severity": "unknown",
                "status": row.status,
                "recommended_actions": recommendations,
                "proposed_actions": list(row.proposed_actions or []),
                "requires_human_approval": row.status == "pending_approval",
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }

    def persist_verification(
        self,
        verification: dict[str, Any],
        *,
        incident_database_id: str | None,
        maintenance_task_database_id: str | None,
    ) -> str | None:
        if not _enabled():
            return None
        if not incident_database_id or not maintenance_task_database_id:
            raise ValueError(
                "Verification persistence requires database incident and task IDs."
            )

        with SessionLocal() as db:
            repository = VerificationResultRepository(db)
            existing = repository.list_all(
                maintenance_task_id=UUID(maintenance_task_database_id),
                limit=1,
            )
            data = {
                "outcome": str(verification.get("outcome") or "inconclusive"),
                "resolved": bool(verification.get("resolved")),
                "summary": str(verification.get("summary") or ""),
                "evidence": {
                    "items": list(verification.get("evidence") or []),
                    "workflow_verification_id": verification.get("verification_id"),
                    "evidence_simulated": verification.get("evidence_simulated") is True,
                },
                "safety_certified": False,
            }
            if existing:
                row = existing[0]
                for field, value in data.items():
                    setattr(row, field, value)
                db.flush()
            else:
                row = repository.create(
                    incident_id=UUID(incident_database_id),
                    maintenance_task_id=UUID(maintenance_task_database_id),
                    **data,
                )
            db.commit()
            return str(row.id)

    def resolve_incident(
        self,
        incident_database_id: str | None,
        summary: str,
    ) -> None:
        if not _enabled():
            return
        if not incident_database_id:
            raise ValueError("Incident resolution requires a database incident ID.")
        with SessionLocal() as db:
            row = IncidentRepository(db).update(
                UUID(incident_database_id),
                status="resolved",
                resolution_summary=summary,
                closed_at=datetime.now(timezone.utc),
            )
            if row is None:
                raise ValueError("Persisted incident was not found.")
            db.commit()
