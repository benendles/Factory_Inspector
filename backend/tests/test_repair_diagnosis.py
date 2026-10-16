from app.services.repair_diagnosis_service import RepairDiagnosisService


def test_preliminary_diagnosis_separates_simulated_evidence_from_hypotheses():
    result = RepairDiagnosisService(model_enabled=False).diagnose({
        "sensor_analysis": {
            "anomalies": [{
                "sensor": "temperature",
                "value": 95.0,
                "threshold": 90.0,
            }],
        },
        "image_inspection_result": {
            "observations": ["Dust visible around cooling fins."],
        },
    })

    assert result["diagnosis_status"] == "preliminary"
    assert result["replacement_justified"] is False
    assert result["requires_technician_review"] is True
    assert "Simulated temperature reading 95.0 exceeds configured threshold 90.0." in result["confirmed_findings"]
    assert result["possible_causes"][0]["confirmation_required"] is True
    assert result["recommended_actions"][0]["action_type"] == "inspection"
    assert result["provider"] == "evidence_grounded_rules"
    assert result["amd_enrichment"]["status"] == "disabled"


def test_amd_hypothesis_label_requires_an_accepted_structured_addition():
    class FakeModel:
        def chat(self, _prompt):
            return """{
                "possible_causes": [{"cause": "Fan failure"}],
                "recommended_actions": [{"action": "Replace the motor"}]
            }"""

    result = RepairDiagnosisService(
        model_client=FakeModel(),
        model_enabled=True,
    ).diagnose({})

    assert result["replacement_justified"] is False
    assert result["possible_causes"][0]["confirmation_required"] is True
    assert result["recommended_actions"] == []
    assert result["provider"] == "evidence_grounded_rules_with_amd_hypotheses"
    assert result["amd_enrichment"] == {
        "status": "completed",
        "response_format": "valid",
        "hypotheses_proposed": 1,
        "hypotheses_accepted": 1,
        "actions_proposed": 1,
        "actions_accepted": 0,
    }


def test_successful_amd_review_without_valid_additions_has_reviewed_label():
    class FakeModel:
        def chat(self, _prompt):
            return '{"possible_causes": [], "recommended_actions": []}'

    result = RepairDiagnosisService(
        model_client=FakeModel(),
        model_enabled=True,
    ).diagnose({})

    assert result["provider"] == "evidence_grounded_rules_with_amd_reviewed"
    assert result["amd_enrichment"] == {
        "status": "completed",
        "response_format": "valid",
        "hypotheses_proposed": 0,
        "hypotheses_accepted": 0,
        "actions_proposed": 0,
        "actions_accepted": 0,
    }


def test_failed_amd_request_retains_rules_only_provider():
    class FailingModel:
        def chat(self, _prompt):
            raise RuntimeError("provider unavailable")

    result = RepairDiagnosisService(
        model_client=FailingModel(),
        model_enabled=True,
    ).diagnose({})

    assert result["provider"] == "evidence_grounded_rules"
    assert result["amd_enrichment"]["status"] == "unavailable"
