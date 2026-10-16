"""Unit tests for deterministic, advisory repair planning."""

from copy import deepcopy
from uuid import uuid4

from app.services.repair_planning_service import RepairPlanningService


def verified_state() -> dict:
    registry_id = str(uuid4())

    return {
        "maintenance_task_id": "MT-REPAIR-001",
        "incident_id": "INC-REPAIR-001",
        "physical_identity_confirmed": True,
        "physical_verification_required": False,
        "registry_requires_physical_verification": False,
        "physical_identity_verification_decision": "confirmed",
        "physical_identity_verified_registry_id": registry_id,
        "physical_identity_verification_audit_id": str(uuid4()),
        "registry_match_status": "verified_match",
        "registry_match": {
            "status": "verified_match",
            "candidate": {
                "id": registry_id,
                "manufacturer": "Acme Motors",
                "model_number": "MX-100",
                "equipment_type": "electric_motor",
            },
        },
        "equipment_identifier_conflicts": [],
        "identifier_conflicts": [],
    }


def compatible_part(**overrides: object) -> dict:
    part = {
        "part_id": "cooling-kit",
        "part_number": "CAT-COOL-100",
        "part_name": "Cooling inspection kit",
        "compatible_equipment_manufacturer": "Acme Motors",
        "compatible_model_numbers": ["MX-100"],
        "compatible_equipment_types": ["electric_motor"],
        "compatibility_basis": "Test catalogue exact match.",
        "quantity": 2,
        "unit_price": "12.50",
        "currency": "USD",
        "supplier_name": "Test catalogue supplier",
        "price_source": "Test catalogue fixture",
        "price_checked_at": "2026-01-01T00:00:00+00:00",
        "availability": "unknown",
    }
    part.update(overrides)
    return part


def test_compatible_known_price_is_itemised_with_decimal_totals():
    plan = RepairPlanningService([compatible_part()]).create_plan(
        verified_state()
    )

    assert plan["status"] == "parts_estimate_ready_for_review"
    assert plan["parts"][0]["compatibility_status"] == "confirmed_compatible"
    assert plan["parts"][0]["unit_price"] == "12.50"
    assert plan["parts"][0]["line_total"] == "25.00"
    assert plan["parts_subtotal"] == "25.00"
    assert plan["known_cost_subtotal"] == "25.00"
    assert plan["currency"] == "USD"
    assert plan["estimated_total"] is None
    assert plan["parts"][0]["price_source"] == "Test catalogue fixture"
    assert plan["parts"][0]["price_checked_at"] == "2026-01-01T00:00:00+00:00"


def test_no_compatible_part_does_not_invent_a_recommendation():
    plan = RepairPlanningService([
        compatible_part(compatible_model_numbers=["MX-999"])
    ]).create_plan(verified_state())

    assert plan["status"] == "requires_technical_assessment"
    assert plan["parts"] == []
    assert plan["parts_subtotal"] is None
    assert plan["excluded_incompatible_parts"][0]["compatibility_status"] == "incompatible"


def test_missing_price_is_not_treated_as_zero():
    plan = RepairPlanningService([
        compatible_part(
            unit_price=None,
            currency=None,
            supplier_name=None,
            price_source=None,
            price_checked_at=None,
        )
    ]).create_plan(verified_state())

    assert plan["status"] == "awaiting_supplier_quote"
    assert plan["parts"][0]["price_status"] == "unknown"
    assert plan["parts"][0]["unit_price"] is None
    assert plan["parts"][0]["line_total"] is None
    assert plan["parts_subtotal"] is None
    assert plan["known_cost_subtotal"] is None
    assert plan["price_completeness"] == "unknown"


def test_missing_model_never_claims_model_specific_compatibility():
    state = verified_state()
    state["registry_match"]["candidate"]["model_number"] = None

    plan = RepairPlanningService([compatible_part()]).create_plan(state)

    assert plan["status"] == "insufficient_equipment_information"
    assert plan["parts"][0]["compatibility_status"] == "insufficient_equipment_data"
    assert plan["parts_subtotal"] is None


def test_mixed_currencies_are_not_summed():
    plan = RepairPlanningService([
        compatible_part(),
        compatible_part(
            part_id="bearing-kit",
            part_number="CAT-BEAR-100",
            part_name="Bearing inspection kit",
            quantity=1,
            unit_price="8.00",
            currency="EUR",
        ),
    ]).create_plan(verified_state())

    assert plan["price_completeness"] == "incomplete"
    assert plan["currency"] is None
    assert plan["known_cost_subtotal"] is None
    assert plan["parts_subtotal"] is None
    assert plan["estimated_total"] is None


def test_unconfirmed_or_rejected_identity_blocks_asset_specific_planning():
    unconfirmed = verified_state()
    unconfirmed["physical_identity_confirmed"] = False
    unconfirmed["physical_identity_verification_decision"] = None

    unconfirmed_plan = RepairPlanningService([compatible_part()]).create_plan(
        unconfirmed
    )

    assert unconfirmed_plan["status"] == "blocked_identity_not_confirmed"
    assert unconfirmed_plan["equipment_registry_id"] is None
    assert unconfirmed_plan["parts"] == []

    rejected = deepcopy(verified_state())
    rejected["physical_identity_confirmed"] = False
    rejected["physical_identity_verification_decision"] = "rejected"

    rejected_plan = RepairPlanningService([compatible_part()]).create_plan(
        rejected
    )

    assert rejected_plan["status"] == "blocked_identity_rejected"
    assert rejected_plan["equipment_registry_id"] is None
    assert rejected_plan["parts"] == []
    assert rejected_plan["procurement"]["research_status"] == (
        "blocked_identity_rejected"
    )


def test_confirmation_decision_is_required_by_the_identity_gate():
    state = verified_state()
    state["physical_identity_verification_decision"] = None

    assert RepairPlanningService.has_valid_physical_identity(state) is False
