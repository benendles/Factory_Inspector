"""Advisory repair planning for verified workflow assets.

The local catalogue remains demonstration data only.  Optional procurement
research is appended as separately labelled, untrusted supplier discovery; it
never becomes a quote, purchase, compatibility proof, or equipment-control
command.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.services.procurement_service import ProcurementService


DEMONSTRATION_CATALOGUE: tuple[dict[str, Any], ...] = (
    {
        "part_id": "demo-motor-cooling-kit",
        "part_number": "DEMO-MOTOR-COOLING-KIT-001",
        "part_name": "Demonstration motor cooling inspection kit",
        "manufacturer": "Factory Inspector demonstration catalogue",
        "compatible_equipment_manufacturer": "Demo Motors",
        "compatible_model_numbers": ["DM-100"],
        "compatible_equipment_types": ["electric_motor"],
        "description": (
            "Demonstration-only entry for exercising repair-planning "
            "responses. It is not a real replacement-part recommendation."
        ),
        "quantity": 1,
        "unit_price": None,
        "currency": None,
        "supplier_name": None,
        "price_source": None,
        "price_checked_at": None,
        "availability": "unknown",
        "compatibility_basis": (
            "Demonstration fixture with an explicit exact manufacturer, "
            "model, and equipment-type match."
        ),
        "catalogue_kind": "demonstration",
    },
)


class RepairPlanningService:
    """Build transparent, asset-specific plans after identity confirmation."""

    def __init__(
        self,
        catalogue: list[dict[str, Any]] | None = None,
        procurement_service: ProcurementService | None = None,
    ) -> None:
        source = catalogue if catalogue is not None else DEMONSTRATION_CATALOGUE
        self._catalogue = [dict(item) for item in source if isinstance(item, dict)]
        self._procurement_service = procurement_service or ProcurementService()

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _normalise(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip().casefold()
        return " ".join(text.split()) or None

    @staticmethod
    def _money(value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None

    @staticmethod
    def _valid_audit_id(value: Any) -> bool:
        try:
            UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return False

        return True

    @classmethod
    def _inspection_evidence_context(
        cls,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Expose reviewed inspection context without treating it as proof."""

        image_result = cls._as_dict(
            state.get("image_inspection_result")
            or state.get("vision_analysis")
        )
        ocr_result = cls._as_dict(state.get("nameplate_ocr_result"))
        reconciliation = cls._as_dict(
            state.get("evidence_reconciliation")
        )

        return {
            "image_inspection": {
                "status": image_result.get("status", "unavailable"),
                "equipment": cls._as_dict(image_result.get("equipment")),
                "observation_count": len(
                    image_result.get("observations", [])
                ) if isinstance(image_result.get("observations"), list) else 0,
            },
            "nameplate_ocr": {
                "status": ocr_result.get("status", "unavailable"),
                "provider": ocr_result.get("provider"),
                "fields": cls._as_dict(ocr_result.get("fields")),
                "confidence": ocr_result.get("confidence"),
            },
            "evidence_reconciliation": {
                "status": reconciliation.get("status", "unavailable"),
                "contradictions": reconciliation.get("contradictions", []),
                "missing_fields": reconciliation.get("missing_fields", []),
            },
            "limitations": [
                "Inspection evidence is contextual and does not determine "
                "part compatibility or authorize maintenance."
            ],
        }

    @classmethod
    def has_valid_physical_identity(cls, state: dict[str, Any]) -> bool:
        """Return true only for the complete audited identity gate."""

        if state.get("physical_identity_confirmed") is not True:
            return False

        if state.get("physical_verification_required") is not False:
            return False

        if state.get("registry_requires_physical_verification") is not False:
            return False

        if state.get("physical_identity_verification_decision") != "confirmed":
            return False

        if state.get("registry_match_status") != "verified_match":
            return False

        registry_match = cls._as_dict(state.get("registry_match"))

        if registry_match.get("status") != "verified_match":
            return False

        candidate = cls._as_dict(registry_match.get("candidate"))
        candidate_id = candidate.get("id")
        verified_id = state.get("physical_identity_verified_registry_id")

        if not candidate_id or not verified_id:
            return False

        if str(candidate_id) != str(verified_id):
            return False

        if not cls._valid_audit_id(
            state.get("physical_identity_verification_audit_id")
        ):
            return False

        for key in (
            "equipment_identifier_conflicts",
            "identifier_conflicts",
        ):
            conflicts = state.get(key)

            if not isinstance(conflicts, list) or conflicts:
                return False

        return True

    @classmethod
    def blocked_plan(
        cls,
        *,
        maintenance_task_id: str | None,
        incident_id: str | None,
        status: str,
        limitation: str,
    ) -> dict[str, Any]:
        """Return a non-asset-specific plan for a blocked workflow."""

        return {
            "plan_id": None,
            "maintenance_task_id": maintenance_task_id,
            "incident_id": incident_id,
            "equipment_registry_id": None,
            "identity_verification_audit_id": None,
            "equipment_identity_confirmed": False,
            "status": status,
            "currency": None,
            "parts": [],
            "excluded_incompatible_parts": [],
            "parts_subtotal": None,
            "known_cost_subtotal": None,
            "labour_estimate": None,
            "transport_estimate": None,
            "tax_estimate": None,
            "estimated_total": None,
            "price_completeness": "not_available",
            "requires_supplier_quote": False,
            "requires_technician_review": True,
            "requires_human_approval": False,
            "procurement": ProcurementService.blocked_proposal(
                status,
                limitation,
            ),
            "created_at": None,
            "limitations": [limitation],
        }

    @classmethod
    def planning_error_plan(
        cls,
        state: dict[str, Any],
        error: Exception,
    ) -> dict[str, Any]:
        """Represent a planning failure without changing identity or approval."""

        candidate = cls._as_dict(
            cls._as_dict(state.get("registry_match")).get("candidate")
        )

        return {
            "plan_id": f"RP-{uuid4().hex.upper()}",
            "maintenance_task_id": state.get("maintenance_task_id"),
            "incident_id": state.get("incident_id"),
            "equipment_registry_id": candidate.get("id"),
            "identity_verification_audit_id": state.get(
                "physical_identity_verification_audit_id"
            ),
            "equipment_identity_confirmed": True,
            "status": "repair_planning_error",
            "currency": None,
            "parts": [],
            "excluded_incompatible_parts": [],
            "parts_subtotal": None,
            "known_cost_subtotal": None,
            "labour_estimate": None,
            "transport_estimate": None,
            "tax_estimate": None,
            "estimated_total": None,
            "price_completeness": "not_available",
            "requires_supplier_quote": True,
            "requires_technician_review": True,
            "requires_human_approval": True,
            "procurement": ProcurementService.blocked_proposal(
                "research_unavailable",
                "Procurement research was not attempted because repair planning failed.",
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inspection_evidence": cls._inspection_evidence_context(
                state
            ),
            "limitations": [
                "Repair planning could not be completed after identity "
                f"confirmation: {type(error).__name__}."
            ],
        }

    @classmethod
    def _price_data(
        cls,
        part: dict[str, Any],
        quantity: int,
    ) -> tuple[dict[str, Any], Decimal | None]:
        """Validate a catalogue price without treating missing data as zero."""

        unit_price = part.get("unit_price")
        currency = part.get("currency")
        source = part.get("price_source")
        checked_at = part.get("price_checked_at")

        price_data: dict[str, Any] = {
            "unit_price": None,
            "line_total": None,
            "currency": str(currency).upper() if currency else None,
            "price_status": "unknown",
            "price_source": source,
            "price_checked_at": checked_at,
            "supplier_name": part.get("supplier_name"),
            "availability": part.get("availability") or "unknown",
        }

        if unit_price is None:
            return price_data, None

        if isinstance(unit_price, bool):
            price_data["price_status"] = "invalid"
            return price_data, None

        try:
            amount = Decimal(str(unit_price))
        except (InvalidOperation, ValueError):
            price_data["price_status"] = "invalid"
            return price_data, None

        if not amount.is_finite() or amount < 0:
            price_data["price_status"] = "invalid"
            return price_data, None

        if not price_data["currency"] or not source or not checked_at:
            price_data["price_status"] = "unknown"
            return price_data, None

        if part.get("catalogue_kind") == "demonstration":
            price_data["price_status"] = "demonstration_only"
            price_data["unit_price"] = cls._money(amount)
            price_data["line_total"] = cls._money(amount * quantity)
            return price_data, None

        price_data["price_status"] = "known"
        price_data["unit_price"] = cls._money(amount)
        price_data["line_total"] = cls._money(amount * quantity)
        return price_data, amount * quantity

    @classmethod
    def _compatibility(
        cls,
        part: dict[str, Any],
        candidate: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Evaluate only explicit catalogue compatibility claims."""

        manufacturer = cls._normalise(candidate.get("manufacturer"))
        model = cls._normalise(candidate.get("model_number"))
        equipment_type = cls._normalise(candidate.get("equipment_type"))

        compatible_manufacturer = cls._normalise(
            part.get("compatible_equipment_manufacturer")
        )
        compatible_models = {
            cls._normalise(value)
            for value in part.get("compatible_model_numbers", [])
            if cls._normalise(value)
        }
        compatible_types = {
            cls._normalise(value)
            for value in part.get("compatible_equipment_types", [])
            if cls._normalise(value)
        }

        evidence = {
            "registry_manufacturer": candidate.get("manufacturer"),
            "registry_model_number": candidate.get("model_number"),
            "registry_equipment_type": candidate.get("equipment_type"),
        }

        if not compatible_manufacturer or not compatible_models or not compatible_types:
            return (
                "requires_verification",
                "Catalogue entry has no complete explicit compatibility rule.",
                evidence,
            )

        if not manufacturer or not model or not equipment_type:
            return (
                "insufficient_equipment_data",
                "Verified registry candidate lacks manufacturer, model, or equipment type required for an exact match.",
                evidence,
            )

        if manufacturer != compatible_manufacturer:
            return (
                "incompatible",
                "Catalogue manufacturer rule does not match the verified equipment manufacturer.",
                evidence,
            )

        if model not in compatible_models:
            return (
                "incompatible",
                "Catalogue model rule does not match the verified equipment model.",
                evidence,
            )

        if equipment_type not in compatible_types:
            return (
                "incompatible",
                "Catalogue equipment-type rule does not match the verified equipment type.",
                evidence,
            )

        return (
            "confirmed_compatible",
            str(part.get("compatibility_basis") or (
                "Explicit catalogue manufacturer, model, and equipment-type "
                "rules match the verified registry candidate."
            )),
            evidence,
        )

    def create_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """Create an advisory plan from a fully verified workflow state."""

        task_id = state.get("maintenance_task_id")
        incident_id = state.get("incident_id")

        if state.get("physical_identity_verification_decision") == "rejected":
            return self.blocked_plan(
                maintenance_task_id=task_id,
                incident_id=incident_id,
                status="blocked_identity_rejected",
                limitation=(
                    "Asset-specific repair planning is blocked because "
                    "physical identity was rejected."
                ),
            )

        if not self.has_valid_physical_identity(state):
            return self.blocked_plan(
                maintenance_task_id=task_id,
                incident_id=incident_id,
                status="blocked_identity_not_confirmed",
                limitation=(
                    "Asset-specific repair planning requires a complete "
                    "audited physical identity confirmation."
                ),
            )

        candidate = self._as_dict(
            self._as_dict(state.get("registry_match")).get("candidate")
        )
        audit_id = state.get("physical_identity_verification_audit_id")
        plan: dict[str, Any] = {
            "plan_id": f"RP-{uuid4().hex.upper()}",
            "maintenance_task_id": task_id,
            "incident_id": incident_id,
            "equipment_registry_id": candidate.get("id"),
            "identity_verification_audit_id": audit_id,
            "equipment_identity_confirmed": True,
            "status": "requires_technical_assessment",
            "currency": None,
            "parts": [],
            "excluded_incompatible_parts": [],
            "parts_subtotal": None,
            "known_cost_subtotal": None,
            "labour_estimate": None,
            "transport_estimate": None,
            "tax_estimate": None,
            "estimated_total": None,
            "price_completeness": "unknown",
            "requires_supplier_quote": True,
            "requires_technician_review": True,
            "requires_human_approval": True,
            "procurement": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inspection_evidence": self._inspection_evidence_context(
                state
            ),
            "limitations": [
                "Catalogue entries are advisory and do not authorize repair.",
                "Labour, transport, and tax are unknown because no configured source was provided.",
            ],
        }

        known_lines: list[tuple[dict[str, Any], Decimal]] = []
        confirmed_lines: list[dict[str, Any]] = []
        has_missing_price = False
        has_uncertain_part = False

        for part in self._catalogue:
            part_id = part.get("part_id")
            part_number = part.get("part_number")
            part_name = part.get("part_name")

            if not part_id or not part_number or not part_name:
                plan["limitations"].append(
                    "A malformed catalogue entry was ignored."
                )
                continue

            quantity = part.get("quantity", 1)

            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                plan["limitations"].append(
                    f"Catalogue part '{part_id}' has an invalid quantity and was ignored."
                )
                continue

            compatibility_status, compatibility_basis, evidence = self._compatibility(
                part,
                candidate,
            )

            price_data, known_line_total = self._price_data(part, quantity)
            line = {
                "part_id": str(part_id),
                "part_number": str(part_number),
                "part_name": str(part_name),
                "description": part.get("description"),
                "quantity": quantity,
                "compatibility_status": compatibility_status,
                "compatibility_basis": compatibility_basis,
                "evidence_used": evidence,
                "requires_human_verification": (
                    compatibility_status != "confirmed_compatible"
                ),
                "catalogue_kind": part.get("catalogue_kind") or "local",
                **price_data,
            }

            if compatibility_status == "incompatible":
                plan["excluded_incompatible_parts"].append(line)
                continue

            plan["parts"].append(line)

            if compatibility_status == "confirmed_compatible":
                confirmed_lines.append(line)

                if known_line_total is None:
                    has_missing_price = True
                else:
                    known_lines.append((line, known_line_total))
            else:
                has_uncertain_part = True

        currencies = {
            line["currency"]
            for line, _ in known_lines
            if line.get("currency")
        }

        if len(currencies) > 1:
            plan["price_completeness"] = "incomplete"
            plan["limitations"].append(
                "Known catalogue prices use multiple currencies and were not summed."
            )
        elif known_lines:
            currency = next(iter(currencies))
            known_total = sum((amount for _, amount in known_lines), Decimal("0"))
            plan["currency"] = currency
            plan["known_cost_subtotal"] = self._money(known_total)

            if not has_missing_price and not has_uncertain_part:
                plan["parts_subtotal"] = self._money(known_total)
                plan["price_completeness"] = "complete"
            else:
                plan["price_completeness"] = "partial"
        elif confirmed_lines:
            plan["price_completeness"] = "unknown"
        elif plan["parts"]:
            plan["price_completeness"] = "unknown"
        else:
            plan["price_completeness"] = "unknown"

        has_model = bool(self._normalise(candidate.get("model_number")))

        if not has_model:
            plan["status"] = "insufficient_equipment_information"
            plan["limitations"].append(
                "The verified registry candidate has no model number; model-specific compatibility cannot be confirmed."
            )
        elif not confirmed_lines:
            plan["status"] = "requires_technical_assessment"
            plan["limitations"].append(
                "No explicitly compatible catalogue part was identified."
            )
        elif plan["price_completeness"] == "complete":
            plan["status"] = "parts_estimate_ready_for_review"
        else:
            plan["status"] = "awaiting_supplier_quote"
            plan["limitations"].append(
                "At least one compatible part lacks a reliable, sourced price."
            )

        if plan["price_completeness"] != "complete":
            plan["requires_supplier_quote"] = True

        try:
            plan["procurement"] = self._procurement_service.create_proposal(
                state
            )
        except Exception:
            # Research must never make the identity confirmation, approval
            # interrupt, or the rest of a repair plan fail.  Do not surface a
            # provider response or exception details in the client response.
            plan["procurement"] = ProcurementService.blocked_proposal(
                "research_unavailable",
                "Supplier research was unavailable; technician review remains required.",
            )
            plan["limitations"].append(
                "Supplier research could not be completed; no supplier findings were used."
            )

        # There is intentionally no total: non-part costs have no configured,
        # sourced estimates, so an all-in repair total would be misleading.
        return plan
