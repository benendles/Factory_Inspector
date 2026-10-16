"""Match inspected equipment against the PostgreSQL equipment registry.

A verified registry match means one unique candidate was found using a
strong identifier. It does NOT mean the physical machine has been
human-verified.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.repositories import EquipmentRepository


REGISTRY_MATCHED = "verified_match"
REGISTRY_POSSIBLE = "possible_match"
REGISTRY_NOT_FOUND = "no_match"


def normalize_identifier(value: Any) -> str | None:
    """Normalize identifiers for comparisons without guessing missing data."""

    if value is None:
        return None

    text = str(value).strip().upper()

    if not text:
        return None

    # Ignore separators that commonly vary in printed identifiers.
    return re.sub(r"[\s\-_:./]+", "", text)


def _value(record: Any, field: str) -> Any:
    """Read a field from an ORM object or dictionary."""

    if isinstance(record, dict):
        return record.get(field)

    return getattr(record, field, None)


def _public_equipment_record(record: Any) -> dict[str, Any]:
    """Return safe, relevant registry fields for workflow state."""

    record_id = _value(record, "id")

    return {
        "id": str(record_id) if record_id is not None else None,
        "machine_id": _value(record, "machine_id"),
        "name": _value(record, "name"),
        "manufacturer": _value(record, "manufacturer"),
        "model_number": _value(record, "model_number"),
        "serial_number": _value(record, "serial_number"),
        "asset_tag": _value(record, "asset_tag"),
        "location": _value(record, "location"),
        "equipment_type": _value(record, "equipment_type"),
    }


class SQLEquipmentMatcher:
    """Search the SQL equipment registry using observed identifiers."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = EquipmentRepository(db)

    def _load_all_equipment(self) -> list[Any]:
        """Load registry records in pages instead of silently checking one page."""

        results: list[Any] = []
        offset = 0
        page_size = 100

        while True:
            page = self.repository.list_all(
                limit=page_size,
                offset=offset,
            )

            if not page:
                break

            results.extend(page)

            if len(page) < page_size:
                break

            offset += len(page)

        return results

    def match(
        self,
        *,
        machine_id: str | None = None,
        serial_number: str | None = None,
        asset_tag: str | None = None,
        manufacturer: str | None = None,
        model_number: str | None = None,
    ) -> dict[str, Any]:
        """Match identifiers against registry records.

        Rules:
        - A unique exact machine ID, serial number, or asset tag is a strong
          registry match.
        - Multiple strong matches are ambiguous.
        - Conflicting strong identifiers are ambiguous.
        - Manufacturer/model alone can only produce a possible match.
        - No match never results in a guessed equipment identity.
        """

        observed = {
            "machine_id": normalize_identifier(machine_id),
            "serial_number": normalize_identifier(serial_number),
            "asset_tag": normalize_identifier(asset_tag),
            "manufacturer": normalize_identifier(manufacturer),
            "model_number": normalize_identifier(model_number),
        }

        strong_observed = {
            key: value
            for key, value in observed.items()
            if key in {"machine_id", "serial_number", "asset_tag"} and value
        }

        if not any(observed.values()):
            return {
                "status": REGISTRY_NOT_FOUND,
                "reason": "No usable equipment identifiers were provided.",
                "candidate": None,
                "candidates": [],
                "identifier_conflicts": [],
                "physical_identity_confirmed": False,
                "physical_verification_required": True,
            }

        equipment = self._load_all_equipment()

        if not equipment:
            return {
                "status": REGISTRY_NOT_FOUND,
                "reason": "The SQL equipment registry contains no records.",
                "candidate": None,
                "candidates": [],
                "identifier_conflicts": [],
                "physical_identity_confirmed": False,
                "physical_verification_required": True,
            }

        strong_hits: dict[str, list[Any]] = {
            key: [] for key in strong_observed
        }

        for record in equipment:
            for key, observed_value in strong_observed.items():
                registry_value = normalize_identifier(
                    _value(record, key)
                )

                if registry_value and registry_value == observed_value:
                    strong_hits[key].append(record)

        matched_identifier_types = [
            key for key, records in strong_hits.items() if records
        ]

        candidate_ids: set[str] = set()

        for key in matched_identifier_types:
            for record in strong_hits[key]:
                record_id = _value(record, "id")

                if record_id is not None:
                    candidate_ids.add(str(record_id))

        conflicts: list[str] = []

        # If two strong identifiers point to different records, do not
        # choose whichever record happens to appear first.
        if len(candidate_ids) > 1:
            conflicts.append(
                "Strong identifiers point to different registry records."
            )

        # A strong identifier matching multiple records is also ambiguous.
        for key, records in strong_hits.items():
            unique_ids = {
                str(_value(record, "id"))
                for record in records
                if _value(record, "id") is not None
            }

            if len(unique_ids) > 1:
                conflicts.append(
                    f"The registry contains multiple matches for {key}."
                )

        if conflicts:
            candidates_by_id = {
                str(_value(record, "id")): record
                for record in equipment
                if str(_value(record, "id")) in candidate_ids
            }

            return {
                "status": REGISTRY_POSSIBLE,
                "reason": "The registry match is ambiguous.",
                "candidate": None,
                "candidates": [
                    _public_equipment_record(record)
                    for record in candidates_by_id.values()
                ],
                "matched_identifiers": matched_identifier_types,
                "identifier_conflicts": conflicts,
                "physical_identity_confirmed": False,
                "physical_verification_required": True,
            }

        # A candidate is eligible for a strong match only when at least one
        # strong identifier matches exactly and no conflicts were found.
        if len(candidate_ids) == 1 and matched_identifier_types:
            candidate_id = next(iter(candidate_ids))

            candidate = next(
                (
                    record
                    for record in equipment
                    if str(_value(record, "id")) == candidate_id
                ),
                None,
            )

            if candidate is not None:
                # Strong identifiers choose a candidate, but every supplied
                # registry-comparable identifier is relevant when explaining
                # whether that candidate conflicts with the observation.
                # The order is deliberate so API responses are deterministic.
                for key in (
                    "manufacturer",
                    "model_number",
                    "serial_number",
                    "asset_tag",
                    "machine_id",
                ):
                    observed_value = observed[key]

                    if observed_value is None:
                        continue

                    registry_value = normalize_identifier(
                        _value(candidate, key)
                    )

                    if (
                        registry_value is not None
                        and registry_value != observed_value
                    ):
                        conflicts.append(
                            f"Observed {key} conflicts with the candidate."
                        )

                if conflicts:
                    return {
                        "status": REGISTRY_POSSIBLE,
                        "reason": "Observed identifiers conflict with the candidate.",
                        "candidate": None,
                        "candidates": [
                            _public_equipment_record(candidate)
                        ],
                        "matched_identifiers": matched_identifier_types,
                        "identifier_conflicts": conflicts,
                        "physical_identity_confirmed": False,
                        "physical_verification_required": True,
                    }

                return {
                    "status": REGISTRY_MATCHED,
                    "reason": "One unique candidate matched a strong identifier.",
                    "candidate": _public_equipment_record(candidate),
                    "candidates": [
                        _public_equipment_record(candidate)
                    ],
                    "matched_identifiers": matched_identifier_types,
                    "identifier_conflicts": [],
                    # A database match is not physical confirmation.
                    "physical_identity_confirmed": False,
                    "physical_verification_required": True,
                }

        # No strong match: manufacturer/model similarity is only a lead
        # for a human reviewer, never an identity confirmation.
        possible_candidates = []

        for record in equipment:
            manufacturer_value = normalize_identifier(
                _value(record, "manufacturer")
            )
            model_value = normalize_identifier(
                _value(record, "model_number")
            )

            manufacturer_matches = (
                observed["manufacturer"] is not None
                and manufacturer_value == observed["manufacturer"]
            )
            model_matches = (
                observed["model_number"] is not None
                and model_value == observed["model_number"]
            )

            if manufacturer_matches and model_matches:
                possible_candidates.append(record)

        return {
            "status": (
                REGISTRY_POSSIBLE
                if possible_candidates
                else REGISTRY_NOT_FOUND
            ),
            "reason": (
                "Manufacturer and model suggest possible candidates, "
                "but no strong identifier confirmed a registry record."
                if possible_candidates
                else "No registry record matched the supplied identifiers."
            ),
            "candidate": None,
            "candidates": [
                _public_equipment_record(record)
                for record in possible_candidates
            ],
            "matched_identifiers": [],
            "identifier_conflicts": [],
            "physical_identity_confirmed": False,
            "physical_verification_required": True,
        }
