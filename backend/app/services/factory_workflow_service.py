"""Manage Factory Inspector workflows and physical identity verification."""

import os
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg import Connection
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from app.agents.graph import build_factory_graph
from app.database.identity_verification_repository import (
    EquipmentIdentityVerificationRepository,
)
from app.database.session import DATABASE_URL, SessionLocal
from app.services.repair_planning_service import RepairPlanningService
from app.services.workflow_artifact_store import WorkflowArtifactStore
from app.simulator.scenarios import get_scenario


class FactoryWorkflowService:
    """Run and resume Factory Inspector simulation workflows."""

    def __init__(self, checkpointer: Any | None = None) -> None:
        self._checkpoint_connection: Connection | None = None
        self._checkpointer, self._storage = (
            (checkpointer, "in_memory_test")
            if checkpointer is not None
            else self._create_checkpointer()
        )
        self._graph = build_factory_graph(
            checkpointer=self._checkpointer
        )

        self._repair_planning_service = RepairPlanningService()
        self._artifact_store = WorkflowArtifactStore()
        self._lock = RLock()
        self._workflows: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _postgres_connection_string() -> str:
        """Convert SQLAlchemy's PostgreSQL URL to psycopg's URL format."""

        database_url = make_url(DATABASE_URL)
        if database_url.drivername != "postgresql":
            database_url = database_url.set(drivername="postgresql")
        return database_url.render_as_string(hide_password=False)

    def _create_checkpointer(self) -> tuple[Any, str]:
        backend = os.getenv(
            "FACTORY_WORKFLOW_CHECKPOINTER", "postgres"
        ).strip().casefold()

        if backend == "memory":
            return InMemorySaver(), "in_memory_demo"

        if backend != "postgres":
            raise RuntimeError(
                "FACTORY_WORKFLOW_CHECKPOINTER must be 'postgres' or 'memory'."
            )

        try:
            self._checkpoint_connection = Connection.connect(
                self._postgres_connection_string(),
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
            )
            checkpointer = PostgresSaver(self._checkpoint_connection)
            checkpointer.setup()
            return checkpointer, "postgres"
        except Exception as exc:
            if self._checkpoint_connection is not None:
                self._checkpoint_connection.close()
                self._checkpoint_connection = None
            raise RuntimeError(
                "Could not initialize the PostgreSQL workflow checkpointer."
            ) from exc

    def close(self) -> None:
        """Release the dedicated synchronous checkpoint connection."""

        if self._checkpoint_connection is not None:
            self._checkpoint_connection.close()
            self._checkpoint_connection = None

    # ------------------------------------------------------------------
    # GENERAL HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _load_cached_workflow(self, thread_id: str) -> dict[str, Any]:
        """Rebuild the transient response cache from a durable checkpoint."""

        cached = self._workflows.get(thread_id)
        if cached is not None:
            return cached

        snapshot = self._graph.get_state(self._config(thread_id))
        state = dict(snapshot.values)
        if not state:
            raise KeyError("Workflow not found.")

        # Graphs created before ``maintenance_task`` became a declared state
        # field retained the task ID but not its nested details. Recover it
        # from the workflow-owned SQL record and write it back into the
        # checkpoint without resuming the approval interrupt.
        if not self._as_dict(state.get("maintenance_task")):
            task_payload = self._artifact_store.load_task_payload(
                state.get("maintenance_task_database_id"),
                incident_id=state.get("incident_id"),
                machine_id=state.get("machine_id"),
            )
            if task_payload:
                self._graph.update_state(
                    self._config(thread_id),
                    {"maintenance_task": task_payload},
                )
                snapshot = self._graph.get_state(self._config(thread_id))
                state = dict(snapshot.values)

        self._build_response(
            thread_id,
            {"state": state, "__interrupt__": []},
            snapshot_next=snapshot.next,
        )
        return self._workflows[thread_id]

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        if value is None:
            return {}

        if hasattr(value, "model_dump"):
            try:
                result = value.model_dump()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass

        if hasattr(value, "to_dict"):
            try:
                result = value.to_dict()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass

        return {}

    @staticmethod
    def _extract_interrupts(
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract interrupt payloads returned by LangGraph."""

        output: list[dict[str, Any]] = []

        for item in result.get("__interrupt__", []):
            value = getattr(item, "value", None)

            if isinstance(value, dict):
                output.append(value)

        return output

    @staticmethod
    def _first_nonempty_dict(*values: Any) -> dict[str, Any]:
        for value in values:
            normalized = FactoryWorkflowService._as_dict(value)

            if normalized:
                return normalized.copy()

        return {}

    @staticmethod
    def _first_nonempty_list(*values: Any) -> list[Any]:
        for value in values:
            if isinstance(value, list) and value:
                return value

        return []

    # ------------------------------------------------------------------
    # MAINTENANCE RESPONSE HELPERS
    # ------------------------------------------------------------------

    def _resolve_task_details(
        self,
        state: dict[str, Any],
        pending_interrupts: list[dict[str, Any]] | None = None,
        cached_workflow: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve task details, preferring the current graph state."""

        pending_interrupts = pending_interrupts or []
        cached_workflow = cached_workflow or {}

        cached_interrupts = cached_workflow.get(
            "pending_approval", []
        )

        if not isinstance(cached_interrupts, list):
            cached_interrupts = []

        candidates: list[Any] = [
            state.get("maintenance_task"),
        ]

        candidates.extend(
            item.get("maintenance_task")
            for item in pending_interrupts
            if isinstance(item, dict)
        )

        candidates.extend(
            item.get("maintenance_task")
            for item in cached_interrupts
            if isinstance(item, dict)
        )

        candidates.extend([
            cached_workflow.get("maintenance_task_details"),
            cached_workflow.get("maintenance_task"),
        ])

        task_details = self._first_nonempty_dict(*candidates)

        maintenance_status = state.get("maintenance_status")

        if maintenance_status:
            task_details["status"] = maintenance_status

        # This field describes whether the task is still waiting for the
        # separate human maintenance decision. Completed, rejected, and
        # in-progress simulated work must not keep presenting as awaiting it.
        if task_details.get("status") not in {None, "pending_approval"}:
            task_details["requires_human_approval"] = False

        return task_details

    def _resolve_proposed_actions(
        self,
        state: dict[str, Any],
        task_details: dict[str, Any],
        pending_interrupts: list[dict[str, Any]] | None = None,
        cached_workflow: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve proposed actions from current or cached task data."""

        pending_interrupts = pending_interrupts or []
        cached_workflow = cached_workflow or {}

        cached_interrupts = cached_workflow.get(
            "pending_approval", []
        )

        if not isinstance(cached_interrupts, list):
            cached_interrupts = []

        candidates: list[Any] = [
            state.get("action_plan"),
            task_details.get("proposed_actions"),
            task_details.get("recommended_actions"),
        ]

        candidates.extend(
            item.get("proposed_actions")
            for item in pending_interrupts
            if isinstance(item, dict)
        )

        candidates.extend(
            item.get("proposed_actions")
            for item in cached_interrupts
            if isinstance(item, dict)
        )

        candidates.append(cached_workflow.get("proposed_actions"))

        return self._first_nonempty_list(*candidates)

    # ------------------------------------------------------------------
    # PHYSICAL IDENTITY VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _physical_verification_required(
        state: dict[str, Any],
        pending_interrupts: list[dict[str, Any]] | None = None,
    ) -> bool:
        """
        Fail closed unless physical identity has been confirmed.

        Requires explicit confirmation, a verified registry candidate,
        a matching audit UUID, cleared verification flags, and empty
        identifier-conflict lists.
        """

        pending_interrupts = pending_interrupts or []

        if state.get("physical_identity_confirmed") is not True:
            return True

        if state.get("physical_identity_verification_decision") != "confirmed":
            return True

        if state.get("physical_verification_required") is not False:
            return True

        if (
            state.get("registry_requires_physical_verification")
            is not False
        ):
            return True

        registry_match = FactoryWorkflowService._as_dict(
            state.get("registry_match")
        )

        candidate = FactoryWorkflowService._as_dict(
            registry_match.get("candidate")
        )

        candidate_id = candidate.get("id")

        verified_registry_id = state.get(
            "physical_identity_verified_registry_id"
        )

        audit_id = state.get(
            "physical_identity_verification_audit_id"
        )

        if not candidate_id or not verified_registry_id or not audit_id:
            return True

        if str(candidate_id) != str(verified_registry_id):
            return True

        try:
            UUID(str(audit_id))
        except (TypeError, ValueError, AttributeError):
            return True

        if state.get("registry_match_status") != "verified_match":
            return True

        if registry_match.get("status") != "verified_match":
            return True

        for key in (
            "equipment_identifier_conflicts",
            "identifier_conflicts",
        ):
            conflicts = state.get(key)

            if not isinstance(conflicts, list) or conflicts:
                return True

        for item in pending_interrupts:
            if item.get("physical_identity_confirmed") is not True:
                return True

            if item.get("physical_verification_required") is not False:
                return True

        return False

    @staticmethod
    def _repair_plan_matches_state(
        repair_plan: dict[str, Any],
        state: dict[str, Any],
    ) -> bool:
        """Reuse a plan only when it belongs to this audited workflow state."""

        if not repair_plan:
            return False

        candidate = FactoryWorkflowService._as_dict(
            FactoryWorkflowService._as_dict(
                state.get("registry_match")
            ).get("candidate")
        )

        return (
            repair_plan.get("maintenance_task_id")
            == state.get("maintenance_task_id")
            and str(repair_plan.get("equipment_registry_id"))
            == str(candidate.get("id"))
            and str(repair_plan.get("identity_verification_audit_id"))
            == str(state.get("physical_identity_verification_audit_id"))
            and repair_plan.get("equipment_identity_confirmed") is True
        )

    @staticmethod
    def _maintenance_approval_message(
        verification_required: bool,
    ) -> str:
        """Describe the remaining gate without contradicting identity state."""

        if verification_required:
            return (
                "Physical equipment identity must be verified before "
                "asset-specific maintenance approval."
            )

        return (
            "Physical identity was confirmed. A separate human "
            "maintenance approval is required."
        )

    def _synchronize_registry_match(
        self,
        state: dict[str, Any],
        cached_workflow: dict[str, Any],
        verification_required: bool,
    ) -> dict[str, Any]:
        """Project the audited identity decision into registry-match data."""

        registry_match = self._first_nonempty_dict(
            state.get("registry_match"),
            cached_workflow.get("registry_match"),
        )

        registry_match.update({
            "physical_identity_confirmed": (
                state.get("physical_identity_confirmed") is True
            ),
            "physical_verification_required": verification_required,
            "requires_human_physical_verification": verification_required,
            "physical_identity_verified_registry_id": state.get(
                "physical_identity_verified_registry_id"
            ),
            "physical_identity_verification_audit_id": state.get(
                "physical_identity_verification_audit_id"
            ),
            "physical_identity_verification_decision": state.get(
                "physical_identity_verification_decision"
            ),
        })

        return registry_match

    @staticmethod
    def _public_evidence_data(value: Any) -> dict[str, Any]:
        """Return stored evidence data without an internal file path."""

        data = FactoryWorkflowService._as_dict(value).copy()
        data.pop("image_path", None)
        # Evidence nodes expose a safe error type and limitation instead of a
        # provider exception; discard legacy/raw errors from old checkpoints.
        data.pop("error", None)
        return data

    def _synchronize_evidence_reconciliation(
        self,
        state: dict[str, Any],
        cached_workflow: dict[str, Any],
        verification_required: bool,
    ) -> dict[str, Any]:
        """Project audited identity state into evidence reconciliation."""

        reconciliation = self._public_evidence_data(
            state.get("evidence_reconciliation")
            or cached_workflow.get("evidence_reconciliation")
        )

        reconciliation.setdefault("status", "evidence_unavailable")
        reconciliation.setdefault("image_inspection_status", "unavailable")
        reconciliation.setdefault("nameplate_ocr_status", "unavailable")
        reconciliation.setdefault("agreements", [])
        reconciliation.setdefault("missing_fields", [])
        reconciliation.setdefault("contradictions", [])
        reconciliation.setdefault("limitations", [
            "No image evidence was supplied to this workflow."
        ])

        reconciliation.update({
            "physical_identity_confirmed": (
                state.get("physical_identity_confirmed") is True
            ),
            "physical_verification_required": verification_required,
            "physical_identity_verified_registry_id": state.get(
                "physical_identity_verified_registry_id"
            ),
            "physical_identity_verification_audit_id": state.get(
                "physical_identity_verification_audit_id"
            ),
            "physical_identity_verification_decision": state.get(
                "physical_identity_verification_decision"
            ),
            "requires_human_review": True,
        })

        return reconciliation

    def _build_pending_approval(
        self,
        *,
        state: dict[str, Any],
        task_details: dict[str, Any],
        proposed_actions: list[dict[str, Any]],
        repair_plan: dict[str, Any] | None,
        registry_match: dict[str, Any],
        image_evidence: dict[str, Any],
        image_inspection_result: dict[str, Any],
        nameplate_ocr_result: dict[str, Any],
        evidence_reconciliation: dict[str, Any],
        verification_required: bool,
        base: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a canonical paused-maintenance approval payload."""

        pending = dict(base or {})
        pending.update({
            "type": pending.get("type", "maintenance_approval_required"),
            "incident_id": (
                state.get("incident_id")
                or task_details.get("incident_id")
            ),
            "maintenance_task_id": (
                state.get("maintenance_task_id")
                or task_details.get("task_id")
            ),
            "maintenance_task": task_details,
            "proposed_actions": proposed_actions,
            "repair_plan": repair_plan,
            "registry_match": registry_match,
            "image_evidence": image_evidence,
            "image_inspection_result": image_inspection_result,
            "nameplate_ocr_result": nameplate_ocr_result,
            "evidence_reconciliation": evidence_reconciliation,
            "evolus_maintenance_assessment": self._as_dict(
                state.get("evolus_maintenance_assessment")
            ) or self._as_dict(
                self._as_dict(state.get("investigation")).get(
                    "evolus_maintenance_assessment"
                )
            ),
            "evolus_evidence_context": self._as_dict(
                state.get("evolus_evidence_context")
            ) or self._as_dict(
                self._as_dict(state.get("investigation")).get(
                    "evolus_evidence_context"
                )
            ),
            "registry_match_status": (
                state.get("registry_match_status")
                or registry_match.get("status")
                or "not_checked"
            ),
            "identifier_conflicts": state.get(
                "identifier_conflicts",
                [],
            ),
            "equipment_identifier_conflicts": state.get(
                "equipment_identifier_conflicts",
                [],
            ),
            "physical_identity_confirmed": (
                state.get("physical_identity_confirmed") is True
            ),
            "physical_verification_required": verification_required,
            "physical_identity_verified_registry_id": state.get(
                "physical_identity_verified_registry_id"
            ),
            "physical_identity_verification_audit_id": state.get(
                "physical_identity_verification_audit_id"
            ),
            "physical_identity_verification_decision": state.get(
                "physical_identity_verification_decision"
            ),
            "message": self._maintenance_approval_message(
                verification_required
            ),
        })

        return pending

    # ------------------------------------------------------------------
    # WORKFLOW STATUS HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_workflow_status(
        state: dict[str, Any],
        pending_interrupts: list[dict[str, Any]],
        snapshot_next: tuple[Any, ...] | list[Any] | None = None,
    ) -> str:
        """Resolve status from the current graph state."""

        # A rejected physical identity always takes precedence over
        # ordinary maintenance approval status.
        if (
            state.get("physical_identity_verification_decision")
            == "rejected"
        ):
            return "identity_rejected"

        if pending_interrupts:
            return "awaiting_approval"

        status = state.get("status")

        if isinstance(status, str) and status.strip():
            return status

        next_nodes = list(snapshot_next or [])

        if not next_nodes:
            return "completed"

        return "in_progress"

    # ------------------------------------------------------------------
    # INVESTIGATION RESPONSE SYNCHRONIZATION
    # ------------------------------------------------------------------

    def _synchronize_investigation(
        self,
        state: dict[str, Any],
        cached_workflow: dict[str, Any],
        registry_match: dict[str, Any],
        verification_required: bool,
    ) -> dict[str, Any]:
        """
        Synchronize nested identity information with current graph state.

        The current graph state's identity fields are authoritative.
        Cached investigation data is only a fallback for other fields.
        """

        investigation = self._first_nonempty_dict(
            state.get("investigation"),
            cached_workflow.get("investigation"),
        )

        physical_identity_confirmed = (
            state.get("physical_identity_confirmed") is True
        )

        verified_registry_id = state.get(
            "physical_identity_verified_registry_id"
        )

        verification_audit_id = state.get(
            "physical_identity_verification_audit_id"
        )

        verification_decision = state.get(
            "physical_identity_verification_decision"
        )

        image_evidence = self._public_evidence_data(
            state.get("image_evidence")
            or cached_workflow.get("image_evidence")
        )
        if not image_evidence:
            image_evidence = {
                "status": "unavailable",
                "source": "not_provided",
            }
        image_inspection_result = self._public_evidence_data(
            state.get("image_inspection_result")
            or state.get("vision_analysis")
            or cached_workflow.get("image_inspection_result")
            or cached_workflow.get("vision_analysis")
        )
        if not image_inspection_result:
            image_inspection_result = {
                "status": "unavailable",
                "evidence_available": False,
                "requires_human_review": True,
                "limitations": [
                    "No image evidence was supplied to this workflow."
                ],
            }
        nameplate_ocr_result = self._public_evidence_data(
            state.get("nameplate_ocr_result")
            or cached_workflow.get("nameplate_ocr_result")
        )
        if not nameplate_ocr_result:
            nameplate_ocr_result = {
                "status": "unavailable",
                "provider": None,
                "raw_text": "",
                "fields": {},
                "confidence": None,
                "requires_human_review": True,
                "notes": [
                    "No image evidence was supplied for nameplate OCR."
                ],
            }
        evidence_reconciliation = self._synchronize_evidence_reconciliation(
            state,
            cached_workflow,
            verification_required,
        )

        registry_match.update({
            "physical_identity_confirmed": physical_identity_confirmed,
            "physical_verification_required": verification_required,
            "requires_human_physical_verification": verification_required,
            "physical_identity_verified_registry_id": verified_registry_id,
            "physical_identity_verification_audit_id": (
                verification_audit_id
            ),
            "physical_identity_verification_decision": (
                verification_decision
            ),
        })

        equipment_identification = self._first_nonempty_dict(
            investigation.get("equipment_identification")
        )

        equipment_identification.update({
            "physical_identity_confirmed": physical_identity_confirmed,
            "physical_verification_required": verification_required,
            "physical_identity_verified_registry_id": verified_registry_id,
            "physical_identity_verification_audit_id": (
                verification_audit_id
            ),
            "physical_identity_verification_decision": (
                verification_decision
            ),
        })

        equipment_identification["identifier_conflicts"] = (
            state.get("equipment_identifier_conflicts")
            if isinstance(
                state.get("equipment_identifier_conflicts"),
                list,
            )
            else equipment_identification.get("identifier_conflicts", [])
        )

        investigation["equipment_identification"] = (
            equipment_identification
        )

        investigation["registry_match"] = registry_match
        investigation["image_evidence"] = image_evidence
        investigation["image_inspection_result"] = image_inspection_result
        investigation["nameplate_ocr_result"] = nameplate_ocr_result
        investigation["evidence_reconciliation"] = evidence_reconciliation
        evolus_assessment = self._as_dict(
            state.get("evolus_maintenance_assessment")
            or cached_workflow.get("evolus_maintenance_assessment")
            or investigation.get("evolus_maintenance_assessment")
        )
        if evolus_assessment:
            # The dashboard may display this advisory output, but neither it
            # nor a cached response can change approval or safety policy.
            evolus_assessment["requires_human_approval"] = True
            evolus_assessment["safety_certified"] = False
        investigation["evolus_maintenance_assessment"] = evolus_assessment
        investigation["evolus_evidence_context"] = self._as_dict(
            state.get("evolus_evidence_context")
            or cached_workflow.get("evolus_evidence_context")
            or investigation.get("evolus_evidence_context")
        )

        current_incident = self._as_dict(state.get("incident"))
        if current_incident:
            investigation["incident_details"] = current_incident

        investigation["registry_match_status"] = (
            state.get("registry_match_status")
            or registry_match.get("status")
            or investigation.get("registry_match_status")
        )

        investigation["physical_identity_confirmed"] = (
            physical_identity_confirmed
        )

        investigation["physical_verification_required"] = (
            verification_required
        )

        investigation["physical_identity_verified_registry_id"] = (
            verified_registry_id
        )

        investigation["physical_identity_verification_audit_id"] = (
            verification_audit_id
        )

        investigation["physical_identity_verification_decision"] = (
            verification_decision
        )

        return investigation

    # ------------------------------------------------------------------
    # BUILD WORKFLOW RESPONSE
    # ------------------------------------------------------------------

    def _build_response(
        self,
        thread_id: str,
        result: dict[str, Any],
        snapshot_next: tuple[Any, ...] | list[Any] | None = None,
    ) -> dict[str, Any]:
        """Build a consistent response from the current graph state."""

        state = result.get("state", result)

        if not isinstance(state, dict):
            state = {}

        pending_interrupts = self._extract_interrupts(result)
        cached_workflow = self._workflows.get(thread_id, {})

        workflow_status = self._resolve_workflow_status(
            state,
            pending_interrupts,
            snapshot_next,
        )

        task_details = self._resolve_task_details(
            state,
            pending_interrupts,
            cached_workflow,
        )

        proposed_actions = self._resolve_proposed_actions(
            state,
            task_details,
            pending_interrupts,
            cached_workflow,
        )

        verification_required = self._physical_verification_required(
            state,
            pending_interrupts,
        )

        # A rejected identity must never expose a pending approval.
        identity_rejected = (
            state.get("physical_identity_verification_decision")
            == "rejected"
        )

        if identity_rejected:
            pending_interrupts = []
            workflow_status = "identity_rejected"

        repair_plan = self._first_nonempty_dict(
            state.get("repair_plan"),
            cached_workflow.get("repair_plan"),
        )

        # Never expose a plan tied to an asset after that asset's physical
        # identity has been rejected.
        if identity_rejected:
            if repair_plan.get("status") != "blocked_identity_rejected":
                repair_plan = RepairPlanningService.blocked_plan(
                    maintenance_task_id=state.get("maintenance_task_id"),
                    incident_id=state.get("incident_id"),
                    status="blocked_identity_rejected",
                    limitation=(
                        "Asset-specific repair planning is blocked because "
                        "physical identity was rejected."
                    ),
                )
        elif not repair_plan:
            repair_plan = None

        incident_details = self._first_nonempty_dict(
            state.get("incident"),
            state.get("incident_details"),
            cached_workflow.get("incident_details"),
        )

        registry_match = self._synchronize_registry_match(
            state=state,
            cached_workflow=cached_workflow,
            verification_required=verification_required,
        )
        image_evidence = self._public_evidence_data(
            state.get("image_evidence")
            or cached_workflow.get("image_evidence")
        )
        if not image_evidence:
            image_evidence = {
                "status": "unavailable",
                "source": "not_provided",
            }
        image_inspection_result = self._public_evidence_data(
            state.get("image_inspection_result")
            or state.get("vision_analysis")
            or cached_workflow.get("image_inspection_result")
            or cached_workflow.get("vision_analysis")
        )
        if not image_inspection_result:
            image_inspection_result = {
                "status": "unavailable",
                "evidence_available": False,
                "requires_human_review": True,
                "limitations": [
                    "No image evidence was supplied to this workflow."
                ],
            }
        nameplate_ocr_result = self._public_evidence_data(
            state.get("nameplate_ocr_result")
            or cached_workflow.get("nameplate_ocr_result")
        )
        if not nameplate_ocr_result:
            nameplate_ocr_result = {
                "status": "unavailable",
                "provider": None,
                "raw_text": "",
                "fields": {},
                "confidence": None,
                "requires_human_review": True,
                "notes": [
                    "No image evidence was supplied for nameplate OCR."
                ],
            }
        evidence_reconciliation = self._synchronize_evidence_reconciliation(
            state,
            cached_workflow,
            verification_required,
        )
        evolus_maintenance_assessment = self._as_dict(
            state.get("evolus_maintenance_assessment")
            or cached_workflow.get("evolus_maintenance_assessment")
            or self._as_dict(state.get("investigation")).get(
                "evolus_maintenance_assessment"
            )
        )
        if evolus_maintenance_assessment:
            evolus_maintenance_assessment["requires_human_approval"] = True
            evolus_maintenance_assessment["safety_certified"] = False
        evolus_evidence_context = self._as_dict(
            state.get("evolus_evidence_context")
            or cached_workflow.get("evolus_evidence_context")
            or self._as_dict(state.get("investigation")).get(
                "evolus_evidence_context"
            )
        )

        investigation = self._synchronize_investigation(
            state=state,
            cached_workflow=cached_workflow,
            registry_match=registry_match,
            verification_required=verification_required,
        )

        if pending_interrupts:
            pending_interrupts = [
                self._build_pending_approval(
                    state=state,
                    task_details=self._first_nonempty_dict(
                        item.get("maintenance_task"),
                        task_details,
                    ),
                    proposed_actions=(
                        item.get("proposed_actions") or proposed_actions
                    ),
                    repair_plan=repair_plan,
                    registry_match=registry_match,
                    image_evidence=image_evidence,
                    image_inspection_result=image_inspection_result,
                    nameplate_ocr_result=nameplate_ocr_result,
                    evidence_reconciliation=evidence_reconciliation,
                    verification_required=verification_required,
                    base=item,
                )
                for item in pending_interrupts
            ]

        maintenance_status = (
            state.get("maintenance_status")
            or task_details.get("status")
            or cached_workflow.get("maintenance_status")
        )
        pre_maintenance_readings = self._as_dict(
            state.get("sensor_readings")
            or cached_workflow.get("pre_maintenance_readings")
            or cached_workflow.get("sensor_readings")
        )
        post_maintenance_readings = self._as_dict(
            state.get("post_maintenance_readings")
            or cached_workflow.get("post_maintenance_readings")
        )

        # A rejected physical identity blocks the maintenance task.
        # Do not leave the task displaying pending_approval.
        if identity_rejected:
            task_details.pop("repair_plan", None)
            maintenance_status = "blocked_identity_rejected"
            task_details["status"] = maintenance_status
            task_details["requires_human_approval"] = False
        else:
            if maintenance_status:
                task_details["status"] = maintenance_status

            if repair_plan:
                task_details["repair_plan"] = repair_plan

        response = {
            "thread_id": thread_id,
            "machine_id": (
                state.get("machine_id")
                or cached_workflow.get("machine_id")
            ),
            "scenario_id": (
                state.get("simulation_scenario_id")
                or cached_workflow.get("scenario_id")
            ),
            "workflow_status": workflow_status,
            "approval_required": bool(pending_interrupts),
            "pending_approval": pending_interrupts,
            "incident_id": (
                state.get("incident_id")
                or incident_details.get("incident_id")
            ),
            "incident_details": incident_details,
            "maintenance_task_id": (
                state.get("maintenance_task_id")
                or task_details.get("task_id")
                or cached_workflow.get("maintenance_task_id")
            ),
            "maintenance_status": maintenance_status,
            "maintenance_task_details": task_details,
            "repair_plan": repair_plan,
            "investigation": investigation,
            "proposed_actions": proposed_actions,
            # Keep the established field and add explicit before/after names
            # so simulated verification evidence is clear to API consumers.
            "sensor_readings": pre_maintenance_readings,
            "pre_maintenance_readings": pre_maintenance_readings,
            "post_maintenance_readings": post_maintenance_readings,
            "sensor_analysis": (
                state.get("sensor_analysis")
                or cached_workflow.get("sensor_analysis")
                or {}
            ),
            "vision_analysis": (
                image_inspection_result
            ),
            "image_evidence": image_evidence,
            "image_inspection_result": image_inspection_result,
            "nameplate_ocr_result": nameplate_ocr_result,
            "evidence_reconciliation": evidence_reconciliation,
            "evolus_maintenance_assessment": evolus_maintenance_assessment,
            "evolus_evidence_context": evolus_evidence_context,
            "registry_match": registry_match,
            "registry_match_status": (
                state.get("registry_match_status")
                or cached_workflow.get("registry_match_status", "not_checked")
            ),
            "identifier_conflicts": (
                state.get("identifier_conflicts")
                if isinstance(state.get("identifier_conflicts"), list)
                else cached_workflow.get("identifier_conflicts", [])
            ),
            "equipment_identifier_conflicts": (
                state.get("equipment_identifier_conflicts")
                if isinstance(
                    state.get("equipment_identifier_conflicts"),
                    list,
                )
                else cached_workflow.get(
                    "equipment_identifier_conflicts",
                    [],
                )
            ),
            "physical_identity_confirmed": (
                state.get("physical_identity_confirmed") is True
            ),
            "physical_verification_required": verification_required,
            "physical_identity_verified_registry_id": state.get(
                "physical_identity_verified_registry_id"
            ),
            "physical_identity_verification_audit_id": state.get(
                "physical_identity_verification_audit_id"
            ),
            "physical_identity_verification_decision": state.get(
                "physical_identity_verification_decision"
            ),
            "verification_result": state.get("verification_result"),
            "resolved": (
                False if identity_rejected else state.get("resolved")
            ),
            "error": (
                "Physical identity was rejected. Asset-specific "
                "maintenance approval and execution are blocked."
                if identity_rejected
                else state.get("error")
            ),
            "messages": (
                state.get("messages")
                if isinstance(state.get("messages"), list)
                else cached_workflow.get("messages", [])
            ),
            # Older focused tests construct this service without __init__.
            # Keep their response shape stable while exposing the active
            # durable backend in normal application instances.
            "storage": getattr(self, "_storage", "in_memory_legacy"),
            "safety_certified": False,
        }

        if identity_rejected:
            response["approval_required"] = False
            response["pending_approval"] = []

        # Synchronize the cache with the current graph state.
        self._workflows[thread_id] = {
            **cached_workflow,
            **response,
            "status": workflow_status,
            "workflow_status": workflow_status,
            "maintenance_status": maintenance_status,
            "maintenance_task_details": task_details,
            "repair_plan": repair_plan,
            "investigation": investigation,
            "registry_match": registry_match,
            "approval_required": (
                False if identity_rejected else bool(pending_interrupts)
            ),
            "pending_approval": (
                [] if identity_rejected else pending_interrupts
            ),
        }

        return response

    # ------------------------------------------------------------------
    # START WORKFLOW
    # ------------------------------------------------------------------

    def start_workflow(
        self,
        scenario_id: str,
        machine_id: str,
        image_path: str | None = None,
        image_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a new inspection workflow with optional validated evidence."""

        if not machine_id or not machine_id.strip():
            raise ValueError("machine_id must not be empty.")

        scenario = get_scenario(scenario_id)

        if not isinstance(scenario, dict):
            raise ValueError(
                f"Scenario '{scenario_id}' has an invalid definition."
            )

        if not isinstance(scenario.get("sensor_readings"), dict):
            raise ValueError(
                f"Scenario '{scenario_id}' has no valid sensor_readings."
            )

        thread_id = str(uuid4())
        normalized_machine_id = machine_id.strip()
        public_image_evidence = self._as_dict(image_evidence).copy()

        if image_path:
            public_image_evidence.setdefault("status", "available")
            public_image_evidence.setdefault("source", "uploaded_image")
        else:
            public_image_evidence = {
                "status": "unavailable",
                "source": "not_provided",
            }

        initial_state = {
            "machine_id": normalized_machine_id,
            "sensor_readings": {
                **scenario["sensor_readings"],
                "machine_id": normalized_machine_id,
            },
            "simulation_scenario_id": scenario_id,
            "thread_id": thread_id,
            # This controlled, temporary path is internal-only. Response
            # builders expose ``image_evidence`` instead.
            "image_path": image_path,
            "image_evidence": public_image_evidence,
            "image_inspection_result": {},
            "nameplate_ocr_result": {},
            "evidence_reconciliation": {},
            "status": "inspection_started",
            "approval_status": "pending",
            "requires_human_approval": True,
            "physical_identity_confirmed": False,
            "physical_verification_required": True,
            "registry_requires_physical_verification": True,
            "physical_identity_verified_registry_id": None,
            "physical_identity_verification_audit_id": None,
            "physical_identity_verification_decision": None,
            "equipment_identifier_conflicts": [],
            "identifier_conflicts": [],
            "repair_plan": None,
            "post_maintenance_readings": {},
            "messages": [],
        }

        with self._lock:
            self._workflows[thread_id] = {
                "thread_id": thread_id,
                "machine_id": normalized_machine_id,
                "scenario_id": scenario_id,
                "status": "inspection_started",
                "workflow_status": "inspection_started",
                "maintenance_task_details": {},
                "pending_approval": [],
                "repair_plan": None,
            }

            result = self._graph.invoke(
                initial_state,
                config=self._config(thread_id),
            )

            snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            return self._build_response(
                thread_id,
                result,
                snapshot_next=snapshot.next,
            )

    # ------------------------------------------------------------------
    # GET WORKFLOW
    # ------------------------------------------------------------------

    def get_workflow(self, thread_id: str) -> dict[str, Any]:
        """Retrieve a workflow using its latest graph checkpoint."""

        with self._lock:
            cached = self._load_cached_workflow(thread_id)

            snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            state = dict(snapshot.values)

            # A rejection must remain rejected when the workflow is fetched
            # again, even though LangGraph is still paused at human approval.
            if (
                state.get("physical_identity_verification_decision")
                == "rejected"
                or cached.get("physical_identity_verification_decision")
                == "rejected"
                or cached.get("workflow_status") == "identity_rejected"
            ):
                state["physical_identity_confirmed"] = False
                state["physical_verification_required"] = True
                state["registry_requires_physical_verification"] = True
                state["physical_identity_verified_registry_id"] = None
                state["physical_identity_verification_decision"] = "rejected"

                if not state.get("physical_identity_verification_audit_id"):
                    state["physical_identity_verification_audit_id"] = (
                        cached.get(
                            "physical_identity_verification_audit_id"
                        )
                    )

                response = self._build_response(
                    thread_id,
                    {
                        "state": state,
                        "__interrupt__": [],
                    },
                    snapshot_next=snapshot.next,
                )

                response.update({
                    "workflow_status": "identity_rejected",
                    "approval_required": False,
                    "pending_approval": [],
                    "physical_identity_confirmed": False,
                    "physical_verification_required": True,
                    "physical_identity_verified_registry_id": None,
                    "physical_identity_verification_decision": "rejected",
                    "resolved": False,
                    "error": (
                        "Physical identity was rejected. Asset-specific "
                        "maintenance approval and execution are blocked."
                    ),
                    "safety_certified": False,
                })

                self._workflows[thread_id].update({
                    "status": "identity_rejected",
                    "workflow_status": "identity_rejected",
                    "approval_required": False,
                    "pending_approval": [],
                    "physical_identity_confirmed": False,
                    "physical_verification_required": True,
                    "physical_identity_verified_registry_id": None,
                    "physical_identity_verification_decision": "rejected",
                    "resolved": False,
                    "safety_certified": False,
                    "repair_plan": response.get("repair_plan"),
                })

                return response

            if "human_approval" not in snapshot.next:
                return self._build_response(
                    thread_id,
                    {
                        "state": state,
                        "__interrupt__": [],
                    },
                    snapshot_next=snapshot.next,
                )

            interrupts = cached.get("pending_approval", [])

            if not isinstance(interrupts, list):
                interrupts = []

            task_details = self._resolve_task_details(
                state,
                interrupts,
                cached,
            )

            proposed_actions = self._resolve_proposed_actions(
                state,
                task_details,
                interrupts,
                cached,
            )

            verification_required = self._physical_verification_required(
                state,
                interrupts,
            )

            response = self._build_response(
                thread_id,
                {
                    "state": state,
                    "__interrupt__": [],
                },
                snapshot_next=snapshot.next,
            )

            task_details = self._as_dict(
                response.get("maintenance_task_details")
            )
            proposed_actions = response.get("proposed_actions") or []
            verification_required = response.get(
                "physical_verification_required",
                verification_required,
            )

            if response.get("repair_plan"):
                task_details["repair_plan"] = response["repair_plan"]

            pending = self._build_pending_approval(
                state=state,
                task_details=task_details,
                proposed_actions=proposed_actions,
                repair_plan=response.get("repair_plan"),
                registry_match=self._as_dict(
                    response.get("registry_match")
                ),
                image_evidence=self._as_dict(
                    response.get("image_evidence")
                ),
                image_inspection_result=self._as_dict(
                    response.get("image_inspection_result")
                ),
                nameplate_ocr_result=self._as_dict(
                    response.get("nameplate_ocr_result")
                ),
                evidence_reconciliation=self._as_dict(
                    response.get("evidence_reconciliation")
                ),
                verification_required=verification_required,
            )

            response.update({
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending],
                "maintenance_task_details": task_details,
                "repair_plan": response.get("repair_plan"),
                "proposed_actions": proposed_actions,
                "physical_verification_required": verification_required,
            })

            self._workflows[thread_id].update({
                "status": "awaiting_approval",
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending],
                "repair_plan": response.get("repair_plan"),
            })

            return response

    # ------------------------------------------------------------------
    # PHYSICAL IDENTITY VERIFICATION
    # ------------------------------------------------------------------

    def verify_physical_identity(
        self,
        thread_id: str,
        decision: str,
        reviewer: str,
        comment: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an identity decision without resuming the graph."""

        if decision not in {"confirmed", "rejected"}:
            raise ValueError(
                "decision must be 'confirmed' or 'rejected'."
            )

        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer must not be empty.")

        with self._lock:
            workflow = self._load_cached_workflow(thread_id)

            # Do not allow an already-rejected identity to be overwritten
            # with a confirmation on the same workflow.
            if (
                workflow.get("physical_identity_verification_decision")
                == "rejected"
                or workflow.get("workflow_status") == "identity_rejected"
            ):
                raise ValueError(
                    "Physical identity was already rejected for this "
                    "workflow. Start a new workflow after the identity "
                    "issue has been independently resolved."
                )

            snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            if "human_approval" not in snapshot.next:
                raise ValueError(
                    "Identity verification is only allowed while "
                    "the workflow is paused for human approval."
                )

            state = dict(snapshot.values)

            registry_match = self._as_dict(
                state.get("registry_match")
            )

            candidate = self._as_dict(
                registry_match.get("candidate")
            )

            if not candidate or not candidate.get("id"):
                raise ValueError(
                    "Identity verification cannot be recorded because "
                    "there is no registry candidate."
                )

            if (
                state.get("registry_match_status") != "verified_match"
                or registry_match.get("status") != "verified_match"
            ):
                raise ValueError(
                    "Identity verification requires a unique verified "
                    "registry match."
                )

            for key in (
                "equipment_identifier_conflicts",
                "identifier_conflicts",
            ):
                conflicts = state.get(key)

                if not isinstance(conflicts, list) or conflicts:
                    raise ValueError(
                        "Identity verification is blocked: "
                        f"'{key}' must exist as an empty list."
                    )

            try:
                candidate_uuid = UUID(str(candidate["id"]))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(
                    "The registry candidate has an invalid equipment UUID."
                ) from exc

            # Persist the decision before updating workflow state.
            with SessionLocal() as db:
                repository = EquipmentIdentityVerificationRepository(db)

                audit = repository.create(
                    thread_id=thread_id,
                    equipment_id=candidate_uuid,
                    machine_id=str(state.get("machine_id") or ""),
                    decision=decision,
                    reviewer=reviewer.strip(),
                    evidence={
                        **(evidence or {}),
                        "registry_candidate_id": str(candidate_uuid),
                        "registry_match_status": state.get(
                            "registry_match_status"
                        ),
                    },
                    comment=(comment or "").strip() or None,
                )

                db.commit()
                db.refresh(audit)
                audit_id = str(audit.id)

            identity_confirmed = decision == "confirmed"

            values: dict[str, Any] = {
                "physical_identity_confirmed": identity_confirmed,
                "physical_verification_required": not identity_confirmed,
                "registry_requires_physical_verification": (
                    not identity_confirmed
                ),
                "physical_identity_verified_registry_id": (
                    str(candidate_uuid) if identity_confirmed else None
                ),
                "physical_identity_verification_audit_id": audit_id,
                "physical_identity_verification_decision": decision,
            }

            if not identity_confirmed:
                # Store only a blocked, non-asset-specific representation.
                # This clears any stale plan that could identify parts for a
                # physical asset whose identity was rejected.
                values["repair_plan"] = RepairPlanningService.blocked_plan(
                    maintenance_task_id=state.get("maintenance_task_id"),
                    incident_id=state.get("incident_id"),
                    status="blocked_identity_rejected",
                    limitation=(
                        "Asset-specific repair planning is blocked because "
                        "physical identity was rejected."
                    ),
                )

            # The graph stores the original registry-match object from the
            # identification node. Persist the audited decision into that
            # nested state too, so later GET responses cannot replay its
            # pre-verification flags.
            state_after_identity_decision = {**state, **values}
            verification_required = self._physical_verification_required(
                state_after_identity_decision
            )
            synchronized_registry_match = self._synchronize_registry_match(
                state=state_after_identity_decision,
                cached_workflow=workflow,
                verification_required=verification_required,
            )
            state_after_identity_decision["registry_match"] = (
                synchronized_registry_match
            )
            values["registry_match"] = synchronized_registry_match
            synchronized_evidence_reconciliation = (
                self._synchronize_evidence_reconciliation(
                    state_after_identity_decision,
                    workflow,
                    verification_required,
                )
            )
            state_after_identity_decision["evidence_reconciliation"] = (
                synchronized_evidence_reconciliation
            )
            values["evidence_reconciliation"] = (
                synchronized_evidence_reconciliation
            )
            values["investigation"] = self._synchronize_investigation(
                state=state_after_identity_decision,
                cached_workflow=workflow,
                registry_match=synchronized_registry_match,
                verification_required=verification_required,
            )

            # Updating the checkpoint does not resume the approval interrupt.
            self._graph.update_state(
                self._config(thread_id),
                values,
            )

            updated_snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            updated_state = dict(updated_snapshot.values)

            # ----------------------------------------------------------
            # REJECTED IDENTITY: BLOCK APPROVAL AND EXECUTION
            # ----------------------------------------------------------

            if decision == "rejected":
                response = self._build_response(
                    thread_id,
                    {
                        "state": updated_state,
                        "__interrupt__": [],
                    },
                    snapshot_next=updated_snapshot.next,
                )

                task_details = self._resolve_task_details(
                    updated_state,
                    cached_workflow=workflow,
                )

                proposed_actions = self._resolve_proposed_actions(
                    updated_state,
                    task_details,
                    cached_workflow=workflow,
                )

                task_details["status"] = "blocked_identity_rejected"
                task_details["requires_human_approval"] = False

                response["maintenance_status"] = "blocked_identity_rejected"
                response["maintenance_task_details"] = task_details

                response.update({
                    "workflow_status": "identity_rejected",
                    "approval_required": False,
                    "pending_approval": [],
                    "maintenance_task_details": task_details,
                    "proposed_actions": proposed_actions,
                    "physical_identity_confirmed": False,
                    "physical_verification_required": True,
                    "physical_identity_verified_registry_id": None,
                    "physical_identity_verification_audit_id": audit_id,
                    "physical_identity_verification_decision": "rejected",
                    "resolved": False,
                    "error": (
                        "Physical identity was rejected. Asset-specific "
                        "maintenance approval and execution are blocked."
                    ),
                    "safety_certified": False,
                })

                self._workflows[thread_id].update({
                    "status": "identity_rejected",
                    "workflow_status": "identity_rejected",
                    "approval_required": False,
                    "pending_approval": [],
                    "physical_identity_confirmed": False,
                    "physical_verification_required": True,
                    "physical_identity_verified_registry_id": None,
                    "physical_identity_verification_audit_id": audit_id,
                    "physical_identity_verification_decision": "rejected",
                    "resolved": False,
                    "safety_certified": False,
                    "repair_plan": response.get("repair_plan"),
                })

                return response

            # ----------------------------------------------------------
            # CONFIRMED IDENTITY: PREPARE PLAN, THEN REQUIRE APPROVAL
            # ----------------------------------------------------------

            existing_plan = self._as_dict(
                updated_state.get("repair_plan")
            )

            if self._repair_plan_matches_state(existing_plan, updated_state):
                repair_plan = existing_plan
            elif self._physical_verification_required(updated_state):
                repair_plan = RepairPlanningService.planning_error_plan(
                    updated_state,
                    ValueError(
                        "The full physical identity gate was not satisfied."
                    ),
                )
            else:
                try:
                    repair_plan = self._repair_planning_service.create_plan(
                        updated_state
                    )
                except Exception as exc:
                    # The audit is already committed. Planning failure must
                    # leave identity confirmed and approval paused.
                    repair_plan = RepairPlanningService.planning_error_plan(
                        updated_state,
                        exc,
                    )

            self._graph.update_state(
                self._config(thread_id),
                {"repair_plan": repair_plan},
            )

            planned_snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            planned_state = dict(planned_snapshot.values)

            response = self._build_response(
                thread_id,
                {
                    "state": planned_state,
                    "__interrupt__": [],
                },
                snapshot_next=planned_snapshot.next,
            )

            task_details = self._as_dict(
                response.get("maintenance_task_details")
            )
            proposed_actions = response.get("proposed_actions") or []
            verification_required = response.get(
                "physical_verification_required",
                self._physical_verification_required(planned_state),
            )

            task_details["repair_plan"] = repair_plan

            pending_approval = self._build_pending_approval(
                state=planned_state,
                task_details=task_details,
                proposed_actions=proposed_actions,
                repair_plan=repair_plan,
                registry_match=self._as_dict(
                    response.get("registry_match")
                ),
                image_evidence=self._as_dict(
                    response.get("image_evidence")
                ),
                image_inspection_result=self._as_dict(
                    response.get("image_inspection_result")
                ),
                nameplate_ocr_result=self._as_dict(
                    response.get("nameplate_ocr_result")
                ),
                evidence_reconciliation=self._as_dict(
                    response.get("evidence_reconciliation")
                ),
                verification_required=verification_required,
            )

            response.update({
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending_approval],
                "maintenance_task_details": task_details,
                "repair_plan": repair_plan,
                "proposed_actions": proposed_actions,
                "physical_identity_confirmed": True,
                "physical_verification_required": False,
                "physical_identity_verified_registry_id": str(candidate_uuid),
                "physical_identity_verification_audit_id": audit_id,
                "physical_identity_verification_decision": "confirmed",
                "safety_certified": False,
            })

            self._workflows[thread_id].update({
                "status": "awaiting_approval",
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending_approval],
                "maintenance_task_details": task_details,
                "repair_plan": repair_plan,
                "proposed_actions": proposed_actions,
                "physical_identity_confirmed": True,
                "physical_verification_required": False,
                "physical_identity_verified_registry_id": str(candidate_uuid),
                "physical_identity_verification_audit_id": audit_id,
                "physical_identity_verification_decision": "confirmed",
            })

            return response

    # ------------------------------------------------------------------
    # HUMAN MAINTENANCE APPROVAL
    # ------------------------------------------------------------------

    def decide_approval(
        self,
        thread_id: str,
        decision: str,
        approval_user: str,
        approval_comment: str | None = None,
    ) -> dict[str, Any]:
        """Record a human decision and resume the approval interrupt."""

        if decision not in {"approved", "rejected"}:
            raise ValueError(
                "decision must be 'approved' or 'rejected'."
            )

        if not approval_user or not approval_user.strip():
            raise ValueError("approval_user must not be empty.")

        with self._lock:
            workflow = self._load_cached_workflow(thread_id)

            # A rejected physical identity can never be approved.
            if (
                workflow.get("physical_identity_verification_decision")
                == "rejected"
                or workflow.get("workflow_status") == "identity_rejected"
            ):
                raise ValueError(
                    "Maintenance approval is blocked because physical "
                    "identity was rejected. Start a new workflow after "
                    "resolving the identity issue."
                )

            if workflow.get("status") != "awaiting_approval":
                raise ValueError(
                    "This workflow is not awaiting approval."
                )

            snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            if "human_approval" not in snapshot.next:
                raise ValueError(
                    "The workflow is not paused at the approval step."
                )

            state = dict(snapshot.values)

            # Fail closed: only a valid, audited physical identity
            # confirmation permits maintenance approval.
            if (
                decision == "approved"
                and self._physical_verification_required(state)
            ):
                raise ValueError(
                    "Approval blocked: confirm physical identity using "
                    "the identity verification endpoint first. A unique "
                    "verified registry match, matching audit record, and "
                    "zero identifier conflicts are required."
                )

            result = self._graph.invoke(
                Command(
                    resume={
                        "approval_status": decision,
                        "approval_user": approval_user.strip(),
                        "approval_comment": (
                            approval_comment or ""
                        ).strip(),
                    }
                ),
                config=self._config(thread_id),
            )

            updated_snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            final_state = dict(updated_snapshot.values)

            return self._build_response(
                thread_id,
                {
                    "state": final_state,
                    "__interrupt__": self._extract_interrupts(result),
                },
                snapshot_next=updated_snapshot.next,
            )


factory_workflow_service = FactoryWorkflowService()
