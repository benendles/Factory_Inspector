"""Manage Factory Inspector workflows and physical identity verification."""

from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.graph import build_factory_graph
from app.database.identity_verification_repository import (
    EquipmentIdentityVerificationRepository,
)
from app.database.session import SessionLocal
from app.simulator.scenarios import get_scenario


class FactoryWorkflowService:
    """Run and resume Factory Inspector simulation workflows."""

    def __init__(self) -> None:
        self._checkpointer = InMemorySaver()
        self._graph = build_factory_graph(
            checkpointer=self._checkpointer
        )

        self._lock = RLock()
        self._workflows: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # GENERAL HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

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

        # Prefer the current workflow state's canonical status.
        # Do not overwrite it with a stale cached task status.
        maintenance_status = state.get("maintenance_status")

        if maintenance_status:
            task_details["status"] = maintenance_status

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

        candidates.append(
            cached_workflow.get("proposed_actions")
        )

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

        Requires:
        - Explicit physical identity confirmation.
        - Physical verification flags cleared.
        - A unique verified registry match.
        - The verified registry ID to match the candidate ID.
        - A valid audit UUID.
        - Both conflict lists to exist and be empty.
        """

        pending_interrupts = pending_interrupts or []

        if state.get("physical_identity_confirmed") is not True:
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

    # ------------------------------------------------------------------
    # WORKFLOW STATUS HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_workflow_status(
        state: dict[str, Any],
        pending_interrupts: list[dict[str, Any]],
        snapshot_next: tuple[Any, ...] | list[Any] | None = None,
    ) -> str:
        """
        Resolve status without allowing stale cache values to win.

        A real pending interrupt takes precedence. Otherwise, the current
        graph state determines the workflow status.
        """

        if pending_interrupts:
            return "awaiting_approval"

        status = state.get("status")

        if isinstance(status, str) and status.strip():
            return status

        # Fallback for a state that has no explicit status.
        next_nodes = list(snapshot_next or [])

        if not next_nodes:
            return "completed"

        return "in_progress"

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

        # Add consistent identity information to genuine pending requests.
        if pending_interrupts:
            pending_interrupts = [
                {
                    **item,
                    "maintenance_task": self._first_nonempty_dict(
                        item.get("maintenance_task"),
                        task_details,
                    ),
                    "proposed_actions": (
                        item.get("proposed_actions")
                        or proposed_actions
                    ),
                    "physical_identity_confirmed": (
                        state.get("physical_identity_confirmed") is True
                    ),
                    "physical_verification_required": (
                        verification_required
                    ),
                }
                for item in pending_interrupts
            ]

        incident_details = self._first_nonempty_dict(
            state.get("incident"),
            state.get("incident_details"),
            cached_workflow.get("incident_details"),
        )

        registry_match = self._first_nonempty_dict(
            state.get("registry_match"),
            cached_workflow.get("registry_match"),
        )

        maintenance_status = (
            state.get("maintenance_status")
            or task_details.get("status")
            or cached_workflow.get("maintenance_status")
        )

        # Keep the nested task status consistent with the resolved
        # maintenance status whenever the current state supplies one.
        if maintenance_status:
            task_details["status"] = maintenance_status

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
            "investigation": (
                state.get("investigation")
                or cached_workflow.get("investigation")
                or {}
            ),
            "proposed_actions": proposed_actions,
            "sensor_readings": (
                state.get("sensor_readings")
                or cached_workflow.get("sensor_readings")
                or {}
            ),
            "sensor_analysis": (
                state.get("sensor_analysis")
                or cached_workflow.get("sensor_analysis")
                or {}
            ),
            "vision_analysis": (
                state.get("vision_analysis")
                or cached_workflow.get("vision_analysis")
                or {}
            ),
            "registry_match": registry_match,
            "registry_match_status": (
                state.get("registry_match_status")
                or cached_workflow.get(
                    "registry_match_status",
                    "not_checked",
                )
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
            "resolved": state.get("resolved"),
            "error": state.get("error"),
            "messages": (
                state.get("messages")
                if isinstance(state.get("messages"), list)
                else cached_workflow.get("messages", [])
            ),
            "storage": "in_memory_demo",
            "safety_certified": False,
        }

        # Synchronize the cache with the current graph state.
        self._workflows[thread_id] = {
            **cached_workflow,
            **response,
            "status": workflow_status,
            "workflow_status": workflow_status,
            "maintenance_status": maintenance_status,
            "maintenance_task_details": task_details,
        }

        return response

    # ------------------------------------------------------------------
    # START WORKFLOW
    # ------------------------------------------------------------------

    def start_workflow(
        self,
        scenario_id: str,
        machine_id: str,
    ) -> dict[str, Any]:
        """Start a new inspection workflow."""

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

        initial_state = {
            "machine_id": normalized_machine_id,
            "sensor_readings": {
                **scenario["sensor_readings"],
                "machine_id": normalized_machine_id,
            },
            "simulation_scenario_id": scenario_id,
            "thread_id": thread_id,
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
            cached = self._workflows.get(thread_id)

            if cached is None:
                raise KeyError("Workflow not found.")

            snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            state = dict(snapshot.values)

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

            pending = {
                "type": "maintenance_approval_required",
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
                "registry_match": state.get("registry_match") or {},
                "registry_match_status": state.get(
                    "registry_match_status",
                    "not_checked",
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
                "message": (
                    "Physical equipment identity must be verified before "
                    "asset-specific maintenance approval."
                ),
            }

            response = self._build_response(
                thread_id,
                {
                    "state": state,
                    "__interrupt__": [],
                },
                snapshot_next=snapshot.next,
            )

            response.update({
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending],
                "maintenance_task_details": task_details,
                "proposed_actions": proposed_actions,
                "physical_verification_required": verification_required,
            })

            self._workflows[thread_id].update({
                "status": "awaiting_approval",
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending],
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
        """
        Record a physical identity decision.

        The audit is persisted before graph identity flags are updated.
        This method does not resume the graph or approve maintenance.
        """

        if decision not in {"confirmed", "rejected"}:
            raise ValueError(
                "decision must be 'confirmed' or 'rejected'."
            )

        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer must not be empty.")

        with self._lock:
            workflow = self._workflows.get(thread_id)

            if workflow is None:
                raise KeyError("Workflow not found.")

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
                    "there is no registry candidate. Provide valid "
                    "equipment identifiers and run the workflow again."
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
                        f"'{key}' must exist as an empty list. "
                        f"Received type={type(conflicts).__name__}, "
                        f"value={conflicts!r}"
                    )

            try:
                candidate_uuid = UUID(str(candidate["id"]))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(
                    "The registry candidate has an invalid equipment UUID."
                ) from exc

            # Persist the audit decision before updating graph state.
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

            values: dict[str, Any] = {
                "physical_identity_confirmed": decision == "confirmed",
                "physical_verification_required": True,
                "registry_requires_physical_verification": True,
                "physical_identity_verified_registry_id": None,
                "physical_identity_verification_audit_id": audit_id,
                "physical_identity_verification_decision": decision,
            }

            if decision == "confirmed":
                values.update({
                    "physical_verification_required": False,
                    "registry_requires_physical_verification": False,
                    "physical_identity_verified_registry_id": str(
                        candidate_uuid
                    ),
                })

            self._graph.update_state(
                self._config(thread_id),
                values,
            )

            updated_snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            updated_state = dict(updated_snapshot.values)

            response = self._build_response(
                thread_id,
                {
                    "state": updated_state,
                    "__interrupt__": [],
                },
                snapshot_next=updated_snapshot.next,
            )

            # Preserve the approval request in the response. Updating the
            # checkpoint does not resume the actual approval interrupt.
            task_details = self._resolve_task_details(
                updated_state,
                cached_workflow=workflow,
            )

            proposed_actions = self._resolve_proposed_actions(
                updated_state,
                task_details,
                cached_workflow=workflow,
            )

            pending_approval = {
                "type": "maintenance_approval_required",
                "incident_id": (
                    updated_state.get("incident_id")
                    or task_details.get("incident_id")
                ),
                "maintenance_task_id": (
                    updated_state.get("maintenance_task_id")
                    or task_details.get("task_id")
                ),
                "maintenance_task": task_details,
                "proposed_actions": proposed_actions,
                "registry_match": updated_state.get(
                    "registry_match"
                ) or {},
                "registry_match_status": updated_state.get(
                    "registry_match_status",
                    "not_checked",
                ),
                "identifier_conflicts": updated_state.get(
                    "identifier_conflicts",
                    [],
                ),
                "equipment_identifier_conflicts": (
                    updated_state.get(
                        "equipment_identifier_conflicts",
                        [],
                    )
                ),
                "physical_identity_confirmed": (
                    decision == "confirmed"
                ),
                "physical_verification_required": (
                    decision != "confirmed"
                ),
                "message": (
                    "Physical identity verification has been recorded. "
                    "A separate human maintenance approval is required."
                ),
            }

            response.update({
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending_approval],
                "maintenance_task_details": task_details,
                "proposed_actions": proposed_actions,
                "physical_identity_confirmed": (
                    decision == "confirmed"
                ),
                "physical_verification_required": (
                    decision != "confirmed"
                ),
                "physical_identity_verified_registry_id": (
                    str(candidate_uuid)
                    if decision == "confirmed"
                    else None
                ),
                "physical_identity_verification_audit_id": audit_id,
                "physical_identity_verification_decision": decision,
                "safety_certified": False,
            })

            self._workflows[thread_id].update({
                "status": "awaiting_approval",
                "workflow_status": "awaiting_approval",
                "approval_required": True,
                "pending_approval": [pending_approval],
                "maintenance_task_details": task_details,
                "proposed_actions": proposed_actions,
                "physical_identity_confirmed": (
                    decision == "confirmed"
                ),
                "physical_verification_required": (
                    decision != "confirmed"
                ),
                "physical_identity_verification_audit_id": audit_id,
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
            workflow = self._workflows.get(thread_id)

            if workflow is None:
                raise KeyError("Workflow not found.")

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

            # This method is the only method that resumes approval.
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

            # Read the latest checkpoint after the graph resumes.
            # This ensures the response reflects the final graph state.
            updated_snapshot = self._graph.get_state(
                self._config(thread_id)
            )

            final_state = dict(updated_snapshot.values)

            # Prefer the checkpoint state because it is authoritative
            # after graph execution and may include nodes run after the
            # approval interrupt.
            response = self._build_response(
                thread_id,
                {
                    "state": final_state,
                    "__interrupt__": self._extract_interrupts(result),
                },
                snapshot_next=updated_snapshot.next,
            )

            return response


factory_workflow_service = FactoryWorkflowService()