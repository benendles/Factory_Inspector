from app.services.part_compatibility_service import PartCompatibilityService


EQUIPMENT = {
    "manufacturer": "Acme Motors",
    "model_number": "MX-100",
    "equipment_type": "electric_motor",
}


def test_search_snippet_with_exact_model_is_only_possibly_compatible():
    assessment = PartCompatibilityService.assess(EQUIPMENT, {
        "title": "Acme cooling fan for MX-100",
        "url": "https://supplier.example/cooling-fan",
        "content": "Listed for Acme Motors MX-100.",
    })

    assert assessment["compatibility_status"] == "possibly_compatible"
    assert assessment["requires_human_verification"] is True


def test_exact_authoritative_fitment_evidence_can_be_verified():
    assessment = PartCompatibilityService.assess(EQUIPMENT, {
        "title": "MX-100 cooling fan",
        "url": "https://manufacturer.example/fan",
        "content": "Acme Motors MX-100 cooling fan.",
        "source_authoritative": True,
        "authoritative_evidence": "Manufacturer fitment table explicitly lists MX-100.",
    })

    assert assessment["compatibility_status"] == "verified_compatible"


def test_missing_or_conflicting_identifier_evidence_is_not_promoted():
    unknown = PartCompatibilityService.assess(EQUIPMENT, {
        "title": "Acme motor fan family",
        "url": "https://supplier.example/fan",
        "content": "For select motors.",
    })
    incompatible = PartCompatibilityService.assess(EQUIPMENT, {
        "title": "MX-100 fan",
        "url": "https://supplier.example/fan",
        "content": "Not compatible with MX-100.",
    })

    assert unknown["compatibility_status"] == "unknown"
    assert incompatible["compatibility_status"] == "incompatible"


def test_explicit_different_model_is_incompatible_not_an_ambiguous_match():
    assessment = PartCompatibilityService.assess(EQUIPMENT, {
        "title": "Acme cooling fan for MX-200",
        "url": "https://supplier.example/mx-200-fan",
        "content": "In stock for the Acme Motors MX-200 model.",
    })

    assert assessment["compatibility_status"] == "incompatible"
    assert "different model" in assessment["compatibility_basis"].casefold()
    assert assessment["evidence_used"]["source_model_candidates"] == ["MX-200"]
