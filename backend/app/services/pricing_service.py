"""Price extraction that preserves source uncertainty and currency limits."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any


class PricingService:
    """Extract directly quoted amounts without generating price estimates."""

    _SHIPPING_TERMS = re.compile(
        r"\b(?:shipping|postage|delivery|freight|handling)\b", re.IGNORECASE
    )

    _PRICE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "USD",
            re.compile(
                r"(?:\bUSD\s*|\$)"
                r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "EUR",
            re.compile(
                r"(?:\bEUR\s*|€\s*)"
                r"(?P<amount>\d{1,3}(?:[ ,.\d])*(?:,\d{1,2}|\.\d{1,2})?)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "GBP",
            re.compile(
                r"(?:\bGBP\s*|£\s*)"
                r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\b",
                re.IGNORECASE,
            ),
        ),
    )

    @staticmethod
    def _text(value: Any, maximum: int = 2_500) -> str:
        return " ".join(str(value or "").split())[:maximum]

    @staticmethod
    def _money(value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None

    @classmethod
    def _extract_price(
        cls,
        text: str,
    ) -> tuple[Decimal | None, str | None, str, str | None]:
        """Extract a product price without treating a shipping fee as one.

        Search-result snippets are not structured product pages.  A monetary
        amount next to ``shipping`` is useful evidence, but it must never be
        displayed as the item price.  We deliberately return no price when a
        snippet contains only shipping charges rather than guessing.
        """

        shipping_amount_seen = False
        for currency, pattern in cls._PRICE_PATTERNS:
            for match in pattern.finditer(text):
                candidate = match.group("amount").replace(",", "")
                try:
                    amount = Decimal(candidate)
                except InvalidOperation:
                    continue
                if not amount.is_finite() or amount < 0:
                    continue

                # A compact context avoids classifying an actual product
                # price as shipping merely because a separate shipping offer
                # appears later in the result snippet.
                prefix = text[max(0, match.start() - 36):match.start()]
                suffix = text[match.end():match.end() + 24]
                is_shipping_charge = bool(
                    cls._SHIPPING_TERMS.search(prefix)
                    or re.match(
                        r"\s*(?:for\s+)?(?:shipping|postage|delivery|freight|handling)"
                        r"(?:\s+(?:charge|cost|fee))?\b",
                        suffix,
                        re.IGNORECASE,
                    )
                )
                if is_shipping_charge:
                    shipping_amount_seen = True
                    continue

                return amount, currency, "product_price", None

        if shipping_amount_seen:
            return (
                None,
                None,
                "shipping_only",
                "Only a shipping or delivery charge was found; the product price is unverified.",
            )
        return None, None, "not_found", None

    @classmethod
    def offer_from_source(
        cls,
        source: dict[str, Any],
        compatibility: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an offer observation from an untrusted search result."""

        content = cls._text(source.get("content"))
        title = cls._text(source.get("title"), 500) or "Unnamed supplier result"
        searchable = f"{title} {content}"
        price, currency, price_observation, price_note = cls._extract_price(
            searchable
        )
        quote_language = any(
            phrase in searchable.casefold()
            for phrase in ("contact for price", "request a quote", "quote required")
        )

        if quote_language:
            price_status = "quote_required"
            price = None
            currency = None
            price_observation = "quote_required"
            price_note = "The source requests a supplier quote instead of listing a product price."
        elif price is not None:
            # Search snippets are not direct product-page verification.
            price_status = "unverified_listing"
        else:
            price_status = "unknown"

        availability = "unknown"
        if "out of stock" in searchable.casefold():
            availability = "reported_out_of_stock"
        elif "in stock" in searchable.casefold():
            availability = "reported_in_stock"

        retrieved_at = source.get("retrieved_at")
        if not isinstance(retrieved_at, str):
            retrieved_at = datetime.now(timezone.utc).isoformat()

        return {
            "supplier_name": None,
            "product_url": source.get("url"),
            "product_name": title,
            "part_number": None,
            "original_price": cls._money(price),
            "original_currency": currency,
            "price_usd": cls._money(price) if currency == "USD" else None,
            "price_status": price_status,
            "price_observation": price_observation,
            "price_note": price_note,
            "compatibility_status": compatibility["compatibility_status"],
            "compatibility_basis": compatibility["compatibility_basis"],
            "availability": availability,
            "price_checked_at": retrieved_at,
            "evidence_excerpt": content or None,
            "evidence_used": compatibility["evidence_used"],
            "requires_technician_review": True,
        }

    @classmethod
    def summarize_usd(cls, offers: list[dict[str, Any]]) -> dict[str, Any]:
        """Sum only directly verified USD listings with verified fitment.

        Current Tavily search-only integration deliberately has no such
        verified listing, so totals stay null.  The rule is here for a future
        product-page verifier without changing the public result shape.
        """

        known: list[Decimal] = []
        for offer in offers:
            if (
                offer.get("price_status") != "verified_listing"
                or offer.get("compatibility_status") != "verified_compatible"
                or offer.get("original_currency") != "USD"
            ):
                continue
            try:
                amount = Decimal(str(offer.get("price_usd")))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if amount.is_finite() and amount >= 0:
                known.append(amount)

        return {
            "known_parts_subtotal_usd": cls._money(sum(known, Decimal("0")))
            if known else None,
            "estimated_total_usd": None,
            "cost_status": "incomplete",
            "limitations": [
                "Labour, transport, tax, downtime, and any unverified supplier prices are excluded from totals.",
                "Non-USD prices are preserved without inventing an exchange rate.",
            ],
        }
