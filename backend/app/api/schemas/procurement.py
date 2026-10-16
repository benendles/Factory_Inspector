"""Public shapes for evidence-backed procurement research.

The schemas deliberately describe *research findings*, not orders, quotes, or
maintenance authorization.  They are kept separate from the workflow request
models because supplier data is untrusted until a technician reviews it.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiagnosisCause(BaseModel):
    cause: str
    evidence: list[str] = Field(default_factory=list)
    confirmation_required: bool = True
    source: str | None = None


class RecommendedAction(BaseModel):
    action: str
    action_type: str = "inspection"
    priority: str = "medium"
    requires_qualified_technician: bool = True
    source: str | None = None


class AMDEnrichment(BaseModel):
    status: str
    response_format: str
    hypotheses_proposed: int = Field(default=0, ge=0)
    hypotheses_accepted: int = Field(default=0, ge=0)
    actions_proposed: int = Field(default=0, ge=0)
    actions_accepted: int = Field(default=0, ge=0)


class RepairDiagnosis(BaseModel):
    diagnosis_status: str
    provider: str
    confirmed_findings: list[str] = Field(default_factory=list)
    possible_causes: list[DiagnosisCause] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    replacement_justified: bool = False
    requires_technician_review: bool = True
    amd_enrichment: AMDEnrichment | None = None
    limitations: list[str] = Field(default_factory=list)


class PartsResearchRequirements(BaseModel):
    equipment_manufacturer: str | None = None
    equipment_model: str | None = None
    equipment_type: str | None = None
    candidate_part_category: str
    known_part_number: str | None = None
    research_reason: str
    replacement_justified: bool = False
    queries: list[str] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)


class SupplierOffer(BaseModel):
    """A traceable supplier-search observation.

    ``verified_listing`` only means that the application retrieved a listing
    with direct supporting evidence.  It never represents a supplier quote,
    available stock, verified compatibility, or an approved purchase.
    """

    supplier_name: str | None = None
    product_url: str
    product_name: str
    part_number: str | None = None
    original_price: float | None = Field(default=None, ge=0)
    original_currency: str | None = None
    price_usd: float | None = Field(default=None, ge=0)
    price_status: Literal[
        "verified_listing",
        "unverified_listing",
        "quote_required",
        "unknown",
    ] = "unknown"
    price_observation: Literal[
        "product_price",
        "shipping_only",
        "quote_required",
        "not_found",
    ] = "not_found"
    price_note: str | None = None
    compatibility_status: Literal[
        "verified_compatible",
        "possibly_compatible",
        "incompatible",
        "unknown",
    ] = "unknown"
    compatibility_basis: str = "No compatibility assessment is available."
    availability: str = "unknown"
    price_checked_at: datetime | None = None
    evidence_excerpt: str | None = None
    evidence_used: dict[str, Any] = Field(default_factory=dict)
    requires_technician_review: bool = True


class ProcurementProposal(BaseModel):
    research_status: str
    diagnosis: RepairDiagnosis | None = None
    research_requirements: PartsResearchRequirements | None = None
    supplier_offers: list[SupplierOffer] = Field(default_factory=list)
    verified_compatible_parts: list[SupplierOffer] = Field(default_factory=list)
    possibly_compatible_parts: list[SupplierOffer] = Field(default_factory=list)
    excluded_incompatible_parts: list[SupplierOffer] = Field(default_factory=list)
    known_parts_subtotal_usd: str | None = None
    estimated_total_usd: str | None = None
    cost_status: str
    requires_supplier_quote: bool = True
    requires_technician_review: bool = True
    requires_human_approval: bool = False
    limitations: list[str] = Field(default_factory=list)
