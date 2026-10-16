"""Evidence-first repair and procurement research orchestration."""

from __future__ import annotations

from typing import Any

from app.services.part_compatibility_service import PartCompatibilityService
from app.services.parts_research_service import PartsResearchService
from app.services.pricing_service import PricingService
from app.services.repair_diagnosis_service import RepairDiagnosisService
from app.services.supplier_search_service import SupplierSearchService


class ProcurementService:
    """Build a technician-review proposal without purchasing or approval."""

    def __init__(
        self,
        *,
        diagnosis_service: RepairDiagnosisService | None = None,
        parts_research_service: PartsResearchService | None = None,
        supplier_search_service: SupplierSearchService | None = None,
        compatibility_service: PartCompatibilityService | None = None,
        pricing_service: PricingService | None = None,
    ) -> None:
        self._diagnosis_service = diagnosis_service or RepairDiagnosisService()
        self._parts_research_service = (
            parts_research_service or PartsResearchService()
        )
        self._supplier_search_service = (
            supplier_search_service or SupplierSearchService()
        )
        self._compatibility_service = (
            compatibility_service or PartCompatibilityService()
        )
        self._pricing_service = pricing_service or PricingService()

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _identity_verified(state: dict[str, Any]) -> bool:
        registry_match = ProcurementService._as_dict(state.get("registry_match"))
        candidate = ProcurementService._as_dict(registry_match.get("candidate"))
        equipment_conflicts = state.get("equipment_identifier_conflicts")
        identifier_conflicts = state.get("identifier_conflicts")
        return (
            state.get("physical_identity_confirmed") is True
            and state.get("physical_verification_required") is False
            and state.get("registry_requires_physical_verification") is False
            and state.get("physical_identity_verification_decision") == "confirmed"
            and state.get("registry_match_status") == "verified_match"
            and registry_match.get("status") == "verified_match"
            and bool(candidate.get("id"))
            and bool(state.get("physical_identity_verification_audit_id"))
            and isinstance(equipment_conflicts, list)
            and not equipment_conflicts
            and isinstance(identifier_conflicts, list)
            and not identifier_conflicts
        )

    @staticmethod
    def blocked_proposal(status: str, limitation: str) -> dict[str, Any]:
        return {
            "research_status": status,
            "diagnosis": None,
            "research_requirements": None,
            "supplier_offers": [],
            "verified_compatible_parts": [],
            "possibly_compatible_parts": [],
            "excluded_incompatible_parts": [],
            "known_parts_subtotal_usd": None,
            "estimated_total_usd": None,
            "cost_status": "not_available",
            "requires_supplier_quote": False,
            "requires_technician_review": True,
            "requires_human_approval": False,
            "limitations": [limitation],
        }

    def create_proposal(self, state: dict[str, Any]) -> dict[str, Any]:
        """Research after identity confirmation; never mutate workflow state."""

        if not self._identity_verified(state):
            return self.blocked_proposal(
                "blocked_identity_not_confirmed",
                "Asset-specific procurement research requires an audited, conflict-free physical identity confirmation.",
            )

        equipment = self._as_dict(
            self._as_dict(state.get("registry_match")).get("candidate")
        )
        diagnosis = self._diagnosis_service.diagnose(state)
        requirements = self._parts_research_service.build_requirements(
            equipment,
            diagnosis,
        )
        search = self._supplier_search_service.search_parts(
            requirements.get("queries", [])
        )
        offers: list[dict[str, Any]] = []
        for source in search.get("results", []):
            if not isinstance(source, dict):
                continue
            compatibility = self._compatibility_service.assess(equipment, source)
            offers.append(
                self._pricing_service.offer_from_source(source, compatibility)
            )

        totals = self._pricing_service.summarize_usd(offers)
        classified = {
            "verified_compatible_parts": [
                offer for offer in offers
                if offer["compatibility_status"] == "verified_compatible"
            ],
            "possibly_compatible_parts": [
                offer for offer in offers
                if offer["compatibility_status"] == "possibly_compatible"
            ],
            "excluded_incompatible_parts": [
                offer for offer in offers
                if offer["compatibility_status"] == "incompatible"
            ],
        }

        status = search.get("status", "search_unavailable")
        limitations = [
            *diagnosis.get("limitations", []),
            *requirements.get("limitations", []),
            *search.get("limitations", []),
            *totals["limitations"],
            "Procurement research does not authorize maintenance, purchasing, or replacement.",
        ]
        return {
            "research_status": status,
            "diagnosis": diagnosis,
            "research_requirements": requirements,
            "supplier_offers": offers,
            **classified,
            "known_parts_subtotal_usd": totals["known_parts_subtotal_usd"],
            "estimated_total_usd": totals["estimated_total_usd"],
            "cost_status": totals["cost_status"],
            "requires_supplier_quote": True,
            "requires_technician_review": True,
            "requires_human_approval": True,
            "limitations": limitations,
        }
