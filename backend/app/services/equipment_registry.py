from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MatchStatus(str, Enum):
    VERIFIED = "verified_match"
    POSSIBLE = "possible_match"
    NOT_FOUND = "no_match"


@dataclass
class EquipmentRecord:
    """Authoritative record for a registered piece of equipment."""

    asset_id: str
    equipment_type: str
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    asset_tag: str | None = None
    location: str | None = None
    specifications: dict[str, str] = field(default_factory=dict)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "equipment_type": self.equipment_type,
            "manufacturer": self.manufacturer,
            "model_number": self.model_number,
            "serial_number": self.serial_number,
            "asset_tag": self.asset_tag,
            "location": self.location,
            "specifications": self.specifications.copy(),
            "notes": self.notes,
        }


@dataclass
class RegistryMatch:
    """Result of comparing identified equipment against the registry."""

    status: MatchStatus
    matched_asset: EquipmentRecord | None
    confidence: float
    matched_fields: list[str] = field(default_factory=list)
    conflicting_fields: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "matched_asset": (
                self.matched_asset.to_dict()
                if self.matched_asset
                else None
            ),
            "confidence": self.confidence,
            "matched_fields": self.matched_fields.copy(),
            "conflicting_fields": self.conflicting_fields.copy(),
            "notes": self.notes.copy(),
        }


class EquipmentRegistry:
    """
    Search registered factory equipment.

    Matching is deliberately conservative:
    - An exact serial-number match can verify asset identity if it is unique
      and there are no conflicting identifiers.
    - An exact asset-tag match can verify asset identity if it is unique
      and there are no conflicting identifiers.
    - Manufacturer/model matches alone are not sufficient to verify identity.
    - Missing or conflicting information is surfaced for human review.

    Records are stored in memory; they are not persisted between restarts.
    """

    def __init__(self, records: list[EquipmentRecord] | None = None):
        self._records: dict[str, EquipmentRecord] = {}

        for record in records or []:
            self.register(record)

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.strip().casefold().split())
        return normalized or None

    @classmethod
    def _same(
        cls,
        first: str | None,
        second: str | None,
    ) -> bool:
        first_normalized = cls._normalize(first)
        second_normalized = cls._normalize(second)

        return (
            first_normalized is not None
            and second_normalized is not None
            and first_normalized == second_normalized
        )

    def register(self, record: EquipmentRecord) -> None:
        """Add an equipment record or update an existing asset ID."""
        asset_id = record.asset_id.strip()

        if not asset_id:
            raise ValueError("asset_id must not be empty.")

        if not record.equipment_type.strip():
            raise ValueError("equipment_type must not be empty.")

        if asset_id in self._records:
            raise ValueError(
                f"Asset ID '{asset_id}' is already registered. "
                "Use update() to modify an existing record."
            )

        # Avoid registering duplicate serial numbers or asset tags.
        for existing in self._records.values():
            if (
                record.serial_number
                and self._same(
                    record.serial_number,
                    existing.serial_number,
                )
            ):
                raise ValueError(
                    f"Serial number '{record.serial_number}' is already "
                    f"registered to asset '{existing.asset_id}'."
                )

            if (
                record.asset_tag
                and self._same(record.asset_tag, existing.asset_tag)
            ):
                raise ValueError(
                    f"Asset tag '{record.asset_tag}' is already "
                    f"registered to asset '{existing.asset_id}'."
                )

        record.asset_id = asset_id
        self._records[asset_id] = record

    def update(self, asset_id: str, **changes: Any) -> EquipmentRecord:
        """Update an existing asset while preserving registry constraints."""
        existing = self._records.get(asset_id)

        if existing is None:
            raise KeyError(f"Asset '{asset_id}' was not found.")

        allowed_fields = {
            "equipment_type",
            "manufacturer",
            "model_number",
            "serial_number",
            "asset_tag",
            "location",
            "specifications",
            "notes",
        }

        unknown_fields = set(changes) - allowed_fields

        if unknown_fields:
            raise ValueError(
                f"Unsupported fields: {', '.join(sorted(unknown_fields))}"
            )

        candidate_values = existing.to_dict()
        candidate_values.update(changes)

        candidate = EquipmentRecord(**candidate_values)

        # Validate uniqueness against all other records.
        for other_id, other in self._records.items():
            if other_id == asset_id:
                continue

            if (
                candidate.serial_number
                and self._same(
                    candidate.serial_number,
                    other.serial_number,
                )
            ):
                raise ValueError(
                    f"Serial number '{candidate.serial_number}' is already "
                    f"registered to asset '{other.asset_id}'."
                )

            if (
                candidate.asset_tag
                and self._same(candidate.asset_tag, other.asset_tag)
            ):
                raise ValueError(
                    f"Asset tag '{candidate.asset_tag}' is already "
                    f"registered to asset '{other.asset_id}'."
                )

        if not candidate.equipment_type.strip():
            raise ValueError("equipment_type must not be empty.")

        self._records[asset_id] = candidate
        return candidate

    def get(self, asset_id: str) -> EquipmentRecord | None:
        """Retrieve a registered asset by its internal asset ID."""
        return self._records.get(asset_id)

    def list_all(self) -> list[EquipmentRecord]:
        """Return all registered assets."""
        return list(self._records.values())

    def search(
        self,
        *,
        asset_id: str | None = None,
        asset_tag: str | None = None,
        serial_number: str | None = None,
        manufacturer: str | None = None,
        model_number: str | None = None,
        equipment_type: str | None = None,
    ) -> list[EquipmentRecord]:
        """
        Search by supplied fields.

        All supplied fields must match. This method is useful for exact
        lookups; use identify() for conservative candidate matching.
        """
        supplied = {
            "asset_id": asset_id,
            "asset_tag": asset_tag,
            "serial_number": serial_number,
            "manufacturer": manufacturer,
            "model_number": model_number,
            "equipment_type": equipment_type,
        }

        supplied = {
            key: value
            for key, value in supplied.items()
            if self._normalize(value) is not None
        }

        results = []

        for record in self._records.values():
            values = record.to_dict()

            if all(
                self._same(str(values.get(key) or ""), value)
                for key, value in supplied.items()
            ):
                results.append(record)

        return results

    def identify(
        self,
        candidate: dict[str, Any],
    ) -> RegistryMatch:
        """
        Compare candidate equipment details with registered records.

        Expected candidate keys include:
        asset_id, asset_tag, serial_number, manufacturer,
        model_number, equipment_type.

        OCR and vision results should be passed here as unverified candidates.
        """

        candidate_asset_id = candidate.get("asset_id")
        candidate_asset_tag = candidate.get("asset_tag")
        candidate_serial = candidate.get("serial_number")
        candidate_manufacturer = candidate.get("manufacturer")
        candidate_model = candidate.get("model_number")
        candidate_type = candidate.get("equipment_type")

        # Strong identity signals: serial number or assigned asset tag.
        strong_candidates: dict[str, list[EquipmentRecord]] = {}

        if self._normalize(candidate_serial):
            strong_candidates["serial_number"] = [
                record
                for record in self._records.values()
                if self._same(candidate_serial, record.serial_number)
            ]

        if self._normalize(candidate_asset_tag):
            strong_candidates["asset_tag"] = [
                record
                for record in self._records.values()
                if self._same(candidate_asset_tag, record.asset_tag)
            ]

        if self._normalize(candidate_asset_id):
            strong_candidates["asset_id"] = [
                record
                for record in self._records.values()
                if self._same(candidate_asset_id, record.asset_id)
            ]

        strong_matches = [
            record
            for records in strong_candidates.values()
            for record in records
        ]

        unique_strong_matches = {
            record.asset_id: record for record in strong_matches
        }

        if len(unique_strong_matches) > 1:
            return RegistryMatch(
                status=MatchStatus.POSSIBLE,
                matched_asset=None,
                confidence=0.0,
                conflicting_fields=list(strong_candidates.keys()),
                notes=[
                    "Supplied serial number, asset tag, or asset ID point "
                    "to different registered assets. Manual verification "
                    "is required."
                ],
            )

        if len(unique_strong_matches) == 1:
            record = next(iter(unique_strong_matches.values()))

            # Detect contradictions with other supplied identifiers.
            conflicts: list[str] = []
            matched_fields: list[str] = []

            comparisons = {
                "serial_number": (
                    candidate_serial,
                    record.serial_number,
                ),
                "asset_tag": (
                    candidate_asset_tag,
                    record.asset_tag,
                ),
                "asset_id": (
                    candidate_asset_id,
                    record.asset_id,
                ),
                "manufacturer": (
                    candidate_manufacturer,
                    record.manufacturer,
                ),
                "model_number": (
                    candidate_model,
                    record.model_number,
                ),
                "equipment_type": (
                    candidate_type,
                    record.equipment_type,
                ),
            }

            for field_name, (candidate_value, registered_value) in (
                comparisons.items()
            ):
                if not self._normalize(candidate_value):
                    continue

                if not self._normalize(registered_value):
                    continue

                if self._same(candidate_value, registered_value):
                    matched_fields.append(field_name)
                else:
                    conflicts.append(field_name)

            if conflicts:
                return RegistryMatch(
                    status=MatchStatus.POSSIBLE,
                    matched_asset=record,
                    confidence=0.0,
                    matched_fields=matched_fields,
                    conflicting_fields=conflicts,
                    notes=[
                        "A strong identifier matched, but other supplied "
                        "details conflict with the registry. Do not treat "
                        "this asset identity as verified until reviewed."
                    ],
                )

            # An OCR-extracted serial number or tag is not independently
            # authenticated. It can produce a registry match candidate,
            # but human confirmation is still needed.
            return RegistryMatch(
                status=MatchStatus.VERIFIED,
                matched_asset=record,
                confidence=100.0,
                matched_fields=matched_fields,
                notes=[
                    "The supplied identity fields match one registered "
                    "record. Confirm that the identifiers were read "
                    "correctly from the physical equipment before acting."
                ],
            )

        # If no strong identifier matched, look for weaker descriptive matches.
        possible: list[tuple[EquipmentRecord, list[str], list[str]]] = []

        for record in self._records.values():
            matched_fields: list[str] = []
            conflicting_fields: list[str] = []

            comparisons = {
                "manufacturer": (
                    candidate_manufacturer,
                    record.manufacturer,
                ),
                "model_number": (
                    candidate_model,
                    record.model_number,
                ),
                "equipment_type": (
                    candidate_type,
                    record.equipment_type,
                ),
            }

            for field_name, (candidate_value, registered_value) in (
                comparisons.items()
            ):
                if not self._normalize(candidate_value):
                    continue

                if not self._normalize(registered_value):
                    continue

                if self._same(candidate_value, registered_value):
                    matched_fields.append(field_name)
                else:
                    conflicting_fields.append(field_name)

            if matched_fields and not conflicting_fields:
                possible.append(
                    (record, matched_fields, conflicting_fields)
                )

        if len(possible) == 1:
            record, matched_fields, _ = possible[0]

            return RegistryMatch(
                status=MatchStatus.POSSIBLE,
                matched_asset=record,
                confidence=50.0,
                matched_fields=matched_fields,
                notes=[
                    "Descriptive details match a registered asset, but no "
                    "unique serial number or asset tag was verified."
                ],
            )

        if len(possible) > 1:
            return RegistryMatch(
                status=MatchStatus.POSSIBLE,
                matched_asset=None,
                confidence=0.0,
                notes=[
                    "Multiple registered assets have compatible descriptive "
                    "details. A serial number, asset tag, or human review "
                    "is needed to distinguish them."
                ],
            )

        return RegistryMatch(
            status=MatchStatus.NOT_FOUND,
            matched_asset=None,
            confidence=0.0,
            notes=[
                "No sufficiently compatible equipment record was found. "
                "Do not invent registry details; request asset information "
                "or register the equipment through an authorized workflow."
            ],
        )