"""Safety-focused LangGraph integration tests for the Evolus advisory node."""

from app.agents import nodes


def test_evolus_assessment_is_advisory_and_cannot_change_safety_or_approval(
    monkeypatch,
):
    class FakeClient:
        @classmethod
        def from_environment(cls):
            return cls()

        async def analyze_incident(self, _incident):
            return {
                "status": "completed",
                "assessment": {
                    "incident_id": "FI-DEMO-001",
                    "equipment_id": "HACKATHON-SIEMENS-001",
                    "human_approval_required": False,
                    "safety_certified": True,
                    "recommended_actions": ["Inspect cooling system"],
                },
                "requires_human_approval": False,
                "safety_certified": True,
            }

    monkeypatch.setattr(nodes, "EvolusClient", FakeClient)
    state = {
        "machine_id": "HACKATHON-SIEMENS-001",
        "incident_id": "FI-DEMO-001",
        "incident": {"severity": "critical"},
        "sensor_analysis": {"anomalies": [{"sensor": "temperature", "value": 95}]},
        "image_inspection_result": {"observations": []},
        "evidence_reconciliation": {},
        "approval_status": "pending",
        "requires_human_approval": True,
        "safety_certified": False,
        "messages": [],
    }

    result = nodes.consult_evolus_maintenance_foreman(state)

    assert result["evolus_maintenance_assessment"]["status"] == "completed"
    assert result["evolus_maintenance_assessment"]["requires_human_approval"] is True
    assert result["evolus_maintenance_assessment"]["safety_certified"] is False
    assert result["approval_status"] == "pending"
    assert result["requires_human_approval"] is True
    assert result["safety_certified"] is False


def test_evolus_configuration_failure_is_recorded_without_blocking_human_review(
    monkeypatch,
):
    class MissingClient:
        @classmethod
        def from_environment(cls):
            raise nodes.EvolusConfigurationError("EVOLUS_API_KEY is missing")

    monkeypatch.setattr(nodes, "EvolusClient", MissingClient)
    state = {
        "machine_id": "HACKATHON-SIEMENS-001",
        "incident_id": "FI-DEMO-001",
        "incident": {"severity": "critical"},
        "sensor_analysis": {},
        "image_inspection_result": {},
        "evidence_reconciliation": {},
        "messages": [],
    }

    result = nodes.consult_evolus_maintenance_foreman(state)

    assert result["evolus_maintenance_assessment"]["status"] == "not_configured"
    assert result["evolus_maintenance_assessment"]["requires_human_approval"] is True
    assert result["evolus_maintenance_assessment"]["safety_certified"] is False
