"""Workflow integration tests for advisory repair plans."""

from threading import RLock
from types import SimpleNamespace
from uuid import uuid4

from app.services.factory_workflow_service import FactoryWorkflowService
from app.services.repair_planning_service import RepairPlanningService
import app.services.factory_workflow_service as workflow_module


class FakeGraph:
    """Minimal paused LangGraph stand-in; it has no resume operation."""

    def __init__(self, state: dict):
        self.state = dict(state)
        self.next = ("human_approval",)
        self.update_calls: list[dict] = []

    def get_state(self, _config):
        return SimpleNamespace(values=dict(self.state), next=self.next)

    def update_state(self, _config, values):
        self.update_calls.append(dict(values))
        self.state.update(values)


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def commit(self):
        return None

    def refresh(self, _value):
        return None


class FakeIdentityRepository:
    audit_id = uuid4()

    def __init__(self, _db):
        pass

    def create(self, **_kwargs):
        return SimpleNamespace(id=self.audit_id)


def repair_catalogue() -> list[dict]:
    return [{
        "part_id": "cooling-kit",
        "part_number": "CAT-COOL-100",
        "part_name": "Cooling inspection kit",
        "compatible_equipment_manufacturer": "Demo Motors",
        "compatible_model_numbers": ["DM-100"],
        "compatible_equipment_types": ["electric_motor"],
        "compatibility_basis": "Explicit test-catalogue match.",
        "quantity": 1,
        "unit_price": "15.50",
        "currency": "USD",
        "supplier_name": "Test catalogue supplier",
        "price_source": "Test catalogue fixture",
        "price_checked_at": "2026-01-01T00:00:00+00:00",
        "availability": "unknown",
    }]


def paused_state() -> dict:
    registry_id = str(uuid4())

    return {
        "machine_id": "MACHINE-DEMO-001",
        "status": "awaiting_approval",
        "incident_id": "INC-DEMO-001",
        "maintenance_task_id": "MT-DEMO-001",
        "maintenance_status": "pending_approval",
        "maintenance_task": {
            "task_id": "MT-DEMO-001",
            "incident_id": "INC-DEMO-001",
            "status": "pending_approval",
            "requires_human_approval": True,
        },
        "action_plan": [],
        "image_evidence": {
            "status": "available",
            "source": "test",
        },
        "image_inspection_result": {
            "status": "completed",
            "equipment": {
                "equipment_type": "electric_motor",
            },
            "observations": [],
        },
        "nameplate_ocr_result": {
            "status": "text_extracted",
            "provider": "test_ocr",
            "fields": {
                "model_number": "DM-100",
                "serial_number": "SN-DEMO-001",
            },
            "confidence": 90.0,
        },
        "evidence_reconciliation": {
            "status": "reconciled",
            "contradictions": [],
            "missing_fields": [],
            "physical_identity_confirmed": False,
        },
        "physical_identity_confirmed": False,
        "physical_verification_required": True,
        "registry_requires_physical_verification": True,
        "physical_identity_verified_registry_id": None,
        "physical_identity_verification_audit_id": None,
        "physical_identity_verification_decision": None,
        "registry_match_status": "verified_match",
        "registry_match": {
            "status": "verified_match",
            "candidate": {
                "id": registry_id,
                "manufacturer": "Demo Motors",
                "model_number": "DM-100",
                "equipment_type": "electric_motor",
            },
        },
        "equipment_identifier_conflicts": [],
        "identifier_conflicts": [],
        "repair_plan": None,
    }


def make_service(state: dict) -> tuple[FactoryWorkflowService, FakeGraph]:
    service = object.__new__(FactoryWorkflowService)
    service._lock = RLock()
    service._graph = FakeGraph(state)
    service._repair_planning_service = RepairPlanningService(repair_catalogue())
    service._workflows = {
        "workflow-001": {
            "thread_id": "workflow-001",
            "status": "awaiting_approval",
            "workflow_status": "awaiting_approval",
            "maintenance_status": "pending_approval",
            "maintenance_task_details": dict(state["maintenance_task"]),
            "pending_approval": [],
            "repair_plan": None,
        }
    }
    return service, service._graph


def install_audit_fakes(monkeypatch):
    monkeypatch.setattr(workflow_module, "SessionLocal", FakeSession)
    monkeypatch.setattr(
        workflow_module,
        "EquipmentIdentityVerificationRepository",
        FakeIdentityRepository,
    )


def test_confirmation_creates_plan_without_resuming_the_paused_workflow(
    monkeypatch,
):
    install_audit_fakes(monkeypatch)
    service, graph = make_service(paused_state())

    response = service.verify_physical_identity(
        thread_id="workflow-001",
        decision="confirmed",
        reviewer="test-reviewer",
    )

    plan = response["repair_plan"]

    assert response["workflow_status"] == "awaiting_approval"
    assert response["approval_required"] is True
    assert response["physical_identity_confirmed"] is True
    assert response["maintenance_status"] == "pending_approval"
    assert plan["maintenance_task_id"] == "MT-DEMO-001"
    assert plan["equipment_identity_confirmed"] is True
    assert plan["parts"][0]["compatibility_status"] == "confirmed_compatible"
    assert response["maintenance_task_details"]["repair_plan"] == plan
    assert response["pending_approval"][0]["repair_plan"] == plan
    assert response["registry_match"]["physical_identity_confirmed"] is True
    assert response["registry_match"]["physical_verification_required"] is False
    assert response["registry_match"][
        "physical_identity_verification_decision"
    ] == "confirmed"
    assert response["pending_approval"][0]["registry_match"] == (
        response["registry_match"]
    )
    assert response["pending_approval"][0][
        "physical_identity_verification_audit_id"
    ] == response["physical_identity_verification_audit_id"]
    assert response["investigation"]["registry_match"] == (
        response["registry_match"]
    )
    assert plan["identity_verification_audit_id"] == response[
        "physical_identity_verification_audit_id"
    ]
    assert plan["inspection_evidence"]["image_inspection"]["status"] == (
        "completed"
    )
    assert plan["inspection_evidence"]["nameplate_ocr"]["provider"] == (
        "test_ocr"
    )
    assert response["evidence_reconciliation"][
        "physical_identity_confirmed"
    ] is True
    assert response["pending_approval"][0][
        "evidence_reconciliation"
    ] == response["evidence_reconciliation"]
    assert "confirmed" in response["pending_approval"][0]["message"]
    assert graph.state["repair_plan"] == plan
    assert graph.state["registry_match"][
        "physical_identity_confirmed"
    ] is True
    assert len(graph.update_calls) == 2

    update_count = len(graph.update_calls)
    retrieved = service.get_workflow("workflow-001")

    assert retrieved["repair_plan"] == plan
    assert retrieved["maintenance_task_details"]["repair_plan"] == plan
    assert retrieved["pending_approval"][0]["repair_plan"] == plan
    assert retrieved["registry_match"]["physical_identity_confirmed"] is True
    assert retrieved["registry_match"]["physical_verification_required"] is False
    assert retrieved["pending_approval"][0]["registry_match"] == (
        retrieved["registry_match"]
    )
    assert retrieved["pending_approval"][0][
        "physical_identity_verification_audit_id"
    ] == retrieved["physical_identity_verification_audit_id"]
    assert retrieved["investigation"]["registry_match"] == (
        retrieved["registry_match"]
    )
    assert retrieved["repair_plan"]["identity_verification_audit_id"] == (
        retrieved["physical_identity_verification_audit_id"]
    )
    assert retrieved["image_inspection_result"]["status"] == "completed"
    assert retrieved["nameplate_ocr_result"]["provider"] == "test_ocr"
    assert retrieved["evidence_reconciliation"][
        "physical_identity_confirmed"
    ] is True
    assert retrieved["pending_approval"][0][
        "evidence_reconciliation"
    ] == retrieved["evidence_reconciliation"]
    assert "confirmed" in retrieved["pending_approval"][0]["message"]
    assert retrieved["safety_certified"] is False
    assert len(graph.update_calls) == update_count


def test_rejection_clears_asset_specific_plan_and_keeps_approval_blocked(
    monkeypatch,
):
    install_audit_fakes(monkeypatch)
    state = paused_state()
    state["repair_plan"] = {
        "plan_id": "RP-STALE",
        "equipment_registry_id": state["registry_match"]["candidate"]["id"],
        "parts": [{"part_number": "STALE-PART"}],
    }
    service, graph = make_service(state)

    response = service.verify_physical_identity(
        thread_id="workflow-001",
        decision="rejected",
        reviewer="test-reviewer",
    )

    assert response["workflow_status"] == "identity_rejected"
    assert response["approval_required"] is False
    assert response["pending_approval"] == []
    assert response["repair_plan"]["status"] == "blocked_identity_rejected"
    assert response["repair_plan"]["equipment_registry_id"] is None
    assert response["repair_plan"]["parts"] == []
    assert response["registry_match"]["physical_identity_confirmed"] is False
    assert response["registry_match"]["physical_verification_required"] is True
    assert response["registry_match"][
        "physical_identity_verification_decision"
    ] == "rejected"
    assert response["investigation"][
        "physical_identity_verification_decision"
    ] == "rejected"
    assert graph.state["repair_plan"]["status"] == "blocked_identity_rejected"
    assert graph.state["registry_match"][
        "physical_identity_verification_decision"
    ] == "rejected"

    retrieved = service.get_workflow("workflow-001")

    assert retrieved["workflow_status"] == "identity_rejected"
    assert retrieved["pending_approval"] == []
    assert retrieved["repair_plan"]["equipment_registry_id"] is None
    assert retrieved["repair_plan"]["parts"] == []
    assert retrieved["registry_match"][
        "physical_identity_verification_decision"
    ] == "rejected"
    assert retrieved["investigation"][
        "physical_identity_verification_decision"
    ] == "rejected"
    assert retrieved["safety_certified"] is False


def test_planning_failure_keeps_confirmed_identity_and_pauses_approval(
    monkeypatch,
):
    class FailingPlanner:
        def create_plan(self, _state):
            raise RuntimeError("catalogue unavailable")

    install_audit_fakes(monkeypatch)
    service, graph = make_service(paused_state())
    service._repair_planning_service = FailingPlanner()

    response = service.verify_physical_identity(
        thread_id="workflow-001",
        decision="confirmed",
        reviewer="test-reviewer",
    )

    assert response["physical_identity_confirmed"] is True
    assert response["approval_required"] is True
    assert response["repair_plan"]["status"] == "repair_planning_error"
    assert graph.state["repair_plan"]["status"] == "repair_planning_error"


def test_retrieving_a_planned_workflow_does_not_repeat_procurement_research(
    monkeypatch,
):
    class CountingProcurement:
        def __init__(self):
            self.calls = 0

        def create_proposal(self, _state):
            self.calls += 1
            return {
                "research_status": "research_disabled",
                "supplier_offers": [],
                "requires_technician_review": True,
                "requires_human_approval": True,
            }

    install_audit_fakes(monkeypatch)
    service, _graph = make_service(paused_state())
    procurement = CountingProcurement()
    service._repair_planning_service = RepairPlanningService(
        repair_catalogue(),
        procurement_service=procurement,
    )

    confirmed = service.verify_physical_identity(
        thread_id="workflow-001",
        decision="confirmed",
        reviewer="test-reviewer",
    )
    first_get = service.get_workflow("workflow-001")
    second_get = service.get_workflow("workflow-001")

    assert confirmed["repair_plan"]["procurement"]["research_status"] == (
        "research_disabled"
    )
    assert first_get["repair_plan"] == confirmed["repair_plan"]
    assert second_get["repair_plan"] == confirmed["repair_plan"]
    assert procurement.calls == 1
