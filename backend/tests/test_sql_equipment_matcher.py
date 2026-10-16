"""Focused unit tests for SQL registry candidate matching."""

from app.services.sql_equipment_matcher import (
    REGISTRY_MATCHED,
    REGISTRY_POSSIBLE,
    SQLEquipmentMatcher,
)


def matcher_with(*records):
    """Use dictionary records to test matching without a database."""
    matcher = SQLEquipmentMatcher(db=object())
    matcher._load_all_equipment = lambda: list(records)
    return matcher


def registry_record(**overrides):
    return {
        "id": "registry-motor-1",
        "machine_id": "machine_001",
        "manufacturer": "Example Manufacturer",
        "model_number": "MOTOR-001",
        "serial_number": "SERIAL-001",
        "asset_tag": "ASSET-001",
        "equipment_type": "electric_motor",
        **overrides,
    }


def test_strong_candidate_reports_all_comparable_identifier_conflicts():
    matcher = matcher_with(registry_record())

    result = matcher.match(
        machine_id="machine_001",
        manufacturer="Siemens",
        model_number="1LE1001-1AB23-4AA4",
        serial_number="Q8W123456",
    )

    assert result["status"] == REGISTRY_POSSIBLE
    assert result["candidate"] is None
    assert result["matched_identifiers"] == ["machine_id"]
    assert result["identifier_conflicts"] == [
        "Observed manufacturer conflicts with the candidate.",
        "Observed model_number conflicts with the candidate.",
        "Observed serial_number conflicts with the candidate.",
    ]
    assert result["physical_identity_confirmed"] is False
    assert result["physical_verification_required"] is True


def test_matching_comparable_identifiers_do_not_create_conflicts():
    matcher = matcher_with(registry_record())

    result = matcher.match(
        machine_id="machine_001",
        manufacturer="example manufacturer",
        model_number="motor 001",
        serial_number="serial 001",
        asset_tag="asset-001",
    )

    assert result["status"] == REGISTRY_MATCHED
    assert result["candidate"]["id"] == "registry-motor-1"
    assert result["identifier_conflicts"] == []
    assert result["physical_identity_confirmed"] is False
    assert result["physical_verification_required"] is True


def test_missing_registry_or_observed_identifiers_do_not_create_conflicts():
    matcher = matcher_with(
        registry_record(
            manufacturer=None,
            model_number=None,
            serial_number=None,
            asset_tag=None,
        )
    )

    result = matcher.match(
        machine_id="machine_001",
        manufacturer="Siemens",
        model_number="1LE1001-1AB23-4AA4",
        serial_number="Q8W123456",
    )

    assert result["status"] == REGISTRY_MATCHED
    assert result["identifier_conflicts"] == []


def test_weak_only_observations_remain_possible_and_do_not_select_candidate():
    matcher = matcher_with(registry_record())

    result = matcher.match(
        manufacturer="Example Manufacturer",
        model_number="MOTOR-001",
    )

    assert result["status"] == REGISTRY_POSSIBLE
    assert result["candidate"] is None
    assert [record["id"] for record in result["candidates"]] == [
        "registry-motor-1"
    ]
    assert result["identifier_conflicts"] == []


def test_multiple_weak_candidates_remain_ambiguous_without_a_selection():
    matcher = matcher_with(
        registry_record(),
        registry_record(
            id="registry-motor-2",
            machine_id="machine_002",
            serial_number="SERIAL-002",
            asset_tag="ASSET-002",
        ),
    )

    result = matcher.match(
        manufacturer="Example Manufacturer",
        model_number="MOTOR-001",
    )

    assert result["status"] == REGISTRY_POSSIBLE
    assert result["candidate"] is None
    assert {record["id"] for record in result["candidates"]} == {
        "registry-motor-1",
        "registry-motor-2",
    }
