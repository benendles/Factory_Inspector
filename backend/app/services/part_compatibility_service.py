"""Conservative compatibility assessment for web-discovered supplier offers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


class PartCompatibilityService:
    """Classify evidence without promoting search snippets to fitment proof."""

    @staticmethod
    def _normalise(value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"[^a-z0-9]+", "", str(value).casefold())
        return text or None

    @staticmethod
    def _text(value: Any, maximum: int = 2_500) -> str:
        return " ".join(str(value or "").split())[:maximum]

    @classmethod
    def _source_model_candidates(cls, text: str) -> list[str]:
        """Return explicit model-like tokens retained in a supplier result.

        A hyphenated identifier containing a digit is a deliberately narrow
        signal.  It lets us surface an explicit model mismatch without
        treating generic marketing prose as fitment evidence.
        """

        candidates: list[str] = []
        for match in re.finditer(
            r"\b(?=[A-Za-z0-9-]{5,}\b)(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b",
            text,
        ):
            value = match.group(0)
            if value not in candidates:
                candidates.append(value)
        return candidates

    @classmethod
    def _source_host(cls, value: Any) -> str | None:
        try:
            host = urlparse(str(value)).hostname
        except (TypeError, ValueError):
            return None
        return host.casefold() if host else None

    @classmethod
    def assess(
        cls,
        equipment: dict[str, Any],
        source: dict[str, Any],
    ) -> dict[str, Any]:
        """Return fitment status requiring explicit, authoritative evidence.

        Tavily search content itself is never marked authoritative.  A future
        supplier-page retrieval service may set ``source_authoritative`` only
        after it has independently retrieved and retained precise fitment
        evidence from a manufacturer or authorised distributor.
        """

        model = cls._normalise(equipment.get("model_number"))
        manufacturer = cls._normalise(equipment.get("manufacturer"))
        text = cls._text(source.get("title")) + " " + cls._text(
            source.get("content")
        )
        normalized_text = cls._normalise(text) or ""
        source_model_candidates = cls._source_model_candidates(text)
        normalized_source_models = {
            normalized
            for candidate in source_model_candidates
            if (normalized := cls._normalise(candidate))
        }
        host = cls._source_host(source.get("url"))
        evidence = {
            "source_url": source.get("url"),
            "source_title": source.get("title"),
            "source_host": host,
            "model_observed": equipment.get("model_number"),
            "manufacturer_observed": equipment.get("manufacturer"),
            "source_model_candidates": source_model_candidates,
        }

        if not model:
            return {
                "compatibility_status": "unknown",
                "compatibility_basis": (
                    "The verified registry candidate has no model number for a fitment assessment."
                ),
                "evidence_used": evidence,
                "requires_human_verification": True,
            }

        explicit_negative = any(
            phrase in text.casefold()
            for phrase in ("not compatible", "incompatible", "does not fit")
        )
        exact_model_present = model in normalized_text
        manufacturer_present = not manufacturer or manufacturer in normalized_text

        if explicit_negative and exact_model_present:
            return {
                "compatibility_status": "incompatible",
                "compatibility_basis": (
                    "The source explicitly reports incompatibility for the observed model."
                ),
                "evidence_used": evidence,
                "requires_human_verification": True,
            }

        if normalized_source_models and model not in normalized_source_models:
            return {
                "compatibility_status": "incompatible",
                "compatibility_basis": (
                    "The source names a different model "
                    f"({', '.join(source_model_candidates)}) than the verified model "
                    f"({equipment.get('model_number')})."
                ),
                "evidence_used": evidence,
                "requires_human_verification": True,
            }

        if exact_model_present and manufacturer_present:
            authoritative = source.get("source_authoritative") is True
            fitment_evidence = cls._text(source.get("authoritative_evidence"))
            if authoritative and fitment_evidence:
                return {
                    "compatibility_status": "verified_compatible",
                    "compatibility_basis": (
                        "Authoritative source explicitly states fitment for the exact verified model."
                    ),
                    "evidence_used": {
                        **evidence,
                        "authoritative_evidence": fitment_evidence,
                    },
                    "requires_human_verification": True,
                }
            return {
                "compatibility_status": "possibly_compatible",
                "compatibility_basis": (
                    "The search result mentions the exact verified model, but a search snippet is not authoritative fitment evidence."
                ),
                "evidence_used": evidence,
                "requires_human_verification": True,
            }

        return {
            "compatibility_status": "unknown",
            "compatibility_basis": (
                "The source does not provide explicit evidence for the exact verified model."
            ),
            "evidence_used": evidence,
            "requires_human_verification": True,
        }
