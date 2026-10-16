"""Build bounded supplier-search requirements from preliminary diagnosis."""

from __future__ import annotations

from typing import Any


class PartsResearchService:
    """Convert hypotheses into search queries without inventing part numbers."""

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _text(value: Any, maximum: int = 200) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).split())
        return text[:maximum] or None

    def build_requirements(
        self,
        equipment: dict[str, Any],
        diagnosis: dict[str, Any],
    ) -> dict[str, Any]:
        manufacturer = self._text(equipment.get("manufacturer"))
        model = self._text(equipment.get("model_number"))
        equipment_type = self._text(equipment.get("equipment_type"))
        causes = diagnosis.get("possible_causes", [])
        cause_text = " ".join(
            self._text(self._as_dict(item).get("cause")) or ""
            for item in causes
        ).casefold()

        category = "technical_inspection"
        reason = "Preliminary diagnosis requires technician assessment."
        if "cooling" in cause_text:
            category = "cooling_system_component"
            reason = (
                "Cooling-system inspection is required before any component "
                "replacement can be justified."
            )

        base = " ".join(item for item in (manufacturer, model) if item)
        queries: list[str] = []
        if base and category == "cooling_system_component":
            queries.extend([
                f"{base} cooling fan spare part",
                f"{base} cooling system component supplier",
                f"{base} technical documentation cooling fan",
            ])
        elif base:
            queries.append(f"{base} technical documentation spare parts")

        return {
            "equipment_manufacturer": manufacturer,
            "equipment_model": model,
            "equipment_type": equipment_type,
            "candidate_part_category": category,
            "known_part_number": None,
            "research_reason": reason,
            "replacement_justified": False,
            "queries": queries[:3],
            "limitations": [
                "Search queries are research requests, not compatibility evidence or part recommendations."
            ],
        }
