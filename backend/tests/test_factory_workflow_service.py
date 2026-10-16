"""Regression tests for FactoryWorkflowService response consistency."""

from threading import RLock
from types import SimpleNamespace

import pytest

from app.services.factory_workflow_service import FactoryWorkflowService


def test_rejected_identity_blocks_maintenance_task_in_response_and_cache():
    """A rejected identity must not leave maintenance awaiting approval."""

    thread_id = "identity-rejected-workflow"
    service = object.__new__(FactoryWorkflowService)
    service._workflows = {
        thread_id: {
            "maintenance_status": "pending_approval",
            "maintenance_task_details": {
                "task_id": "maintenance-task",
                "status": "pending_approval",
                "requires_human_approval": True,
            },
            "pending_approval": [{"type": "maintenance_approval_required"}],
        }
    }

    response = service._build_response(
        thread_id,
        {
            "state": {
                "status": "awaiting_approval",
                "maintenance_status": "pending_approval",
                "physical_identity_confirmed": False,
                "physical_identity_verification_decision": "rejected",
            },
            "__interrupt__": [],
        },
    )

    assert response["workflow_status"] == "identity_rejected"
    assert response["approval_required"] is False
    assert response["pending_approval"] == []
    assert response["maintenance_status"] == "blocked_identity_rejected"
    assert response["maintenance_task_details"]["status"] == (
        "blocked_identity_rejected"
    )
    assert response["maintenance_task_details"]["requires_human_approval"] is False

    cached = service._workflows[thread_id]
    assert cached["maintenance_status"] == "blocked_identity_rejected"
    assert cached["maintenance_task_details"]["status"] == (
        "blocked_identity_rejected"
    )
    assert cached["maintenance_task_details"]["requires_human_approval"] is False
    assert cached["approval_required"] is False
    assert cached["pending_approval"] == []


def test_rejected_identity_cannot_be_approved_before_graph_execution():
    """The approval guard prevents a rejected workflow from resuming."""

    service = object.__new__(FactoryWorkflowService)
    service._lock = RLock()
    service._workflows = {
        "identity-rejected-workflow": {
            "workflow_status": "identity_rejected",
            "physical_identity_verification_decision": "rejected",
        }
    }

    with pytest.raises(
        ValueError,
        match="Maintenance approval is blocked because physical identity was rejected",
    ):
        service.decide_approval(
            thread_id="identity-rejected-workflow",
            decision="approved",
            approval_user="test-operator",
        )


def test_legacy_workflow_without_image_evidence_reports_unavailable_state():
    """Older checkpoints must not expose paths or imply image evidence."""

    service = object.__new__(FactoryWorkflowService)
    service._workflows = {}

    response = service._build_response(
        "no-image-workflow",
        {
            "state": {
                "machine_id": "MACHINE-001",
                "image_path": "/private/temporary/inspection.png",
                "nameplate_ocr_result": {
                    "image_path": "/private/temporary/inspection.png",
                    "status": "unavailable",
                    "fields": {},
                },
                "physical_identity_confirmed": False,
                "physical_verification_required": True,
            },
            "__interrupt__": [],
        },
    )

    assert response["image_evidence"]["status"] == "unavailable"
    assert response["image_inspection_result"]["status"] == "unavailable"
    assert response["nameplate_ocr_result"]["status"] == "unavailable"
    assert response["evidence_reconciliation"]["status"] == (
        "evidence_unavailable"
    )
    assert "image_path" not in response["nameplate_ocr_result"]
    assert "/private/temporary" not in str(response)


def test_response_exposes_simulated_before_after_readings_and_resolved_incident():
    """Terminal responses must not hide follow-up evidence or stale status."""

    service = object.__new__(FactoryWorkflowService)
    service._workflows = {}

    response = service._build_response(
        "resolved-workflow",
        {
            "state": {
                "machine_id": "MACHINE-DEMO-001",
                "status": "incident_resolved",
                "sensor_readings": {
                    "machine_id": "MACHINE-DEMO-001",
                    "temperature_c": 95.0,
                },
                "post_maintenance_readings": {
                    "machine_id": "MACHINE-DEMO-001",
                    "temperature_c": 55.0,
                    "simulated": True,
                },
                "incident": {
                    "incident_id": "INC-DEMO-001",
                    "status": "resolved",
                },
                "investigation": {
                    "incident_details": {
                        "incident_id": "INC-DEMO-001",
                        "status": "open",
                    },
                },
                "physical_identity_confirmed": False,
                "physical_verification_required": True,
            },
            "__interrupt__": [],
        },
    )

    assert response["sensor_readings"]["temperature_c"] == 95.0
    assert response["pre_maintenance_readings"]["temperature_c"] == 95.0
    assert response["post_maintenance_readings"] == {
        "machine_id": "MACHINE-DEMO-001",
        "temperature_c": 55.0,
        "simulated": True,
    }
    assert response["incident_details"]["status"] == "resolved"
    assert response["investigation"]["incident_details"]["status"] == (
        "resolved"
    )


def test_get_workflow_rebuilds_its_response_cache_from_a_checkpoint():
    """A backend reload must not make a paused workflow disappear."""

    paused_state = {
        "machine_id": "MACHINE-DEMO-001",
        "simulation_scenario_id": "overheating",
        "status": "awaiting_approval",
        "incident_id": "INC-DEMO-001",
        "incident": {
            "incident_id": "INC-DEMO-001",
            "machine_id": "MACHINE-DEMO-001",
            "status": "open",
        },
        "maintenance_task_id": "MT-DEMO-001",
        "maintenance_status": "pending_approval",
        "maintenance_task": {
            "task_id": "MT-DEMO-001",
            "incident_id": "INC-DEMO-001",
            "status": "pending_approval",
            "requires_human_approval": True,
        },
        "physical_identity_confirmed": False,
        "physical_verification_required": True,
        "registry_match": {"status": "verified_match"},
        "registry_match_status": "verified_match",
    }

    class DurableGraph:
        def get_state(self, _config):
            return SimpleNamespace(
                values=paused_state,
                next=("human_approval",),
            )

    service = object.__new__(FactoryWorkflowService)
    service._graph = DurableGraph()
    service._lock = RLock()
    service._workflows = {}
    service._storage = "postgres"

    response = service.get_workflow("durable-thread")

    assert response["thread_id"] == "durable-thread"
    assert response["storage"] == "postgres"
    assert response["workflow_status"] == "awaiting_approval"
    assert response["maintenance_task_id"] == "MT-DEMO-001"
    assert response["pending_approval"][0]["maintenance_task_id"] == (
        "MT-DEMO-001"
    )
