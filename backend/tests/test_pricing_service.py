from app.services.pricing_service import PricingService


COMPATIBILITY = {
    "compatibility_status": "possibly_compatible",
    "compatibility_basis": "Search snippet only.",
    "evidence_used": {"source_url": "https://supplier.example/item"},
}


def test_missing_price_stays_null_and_does_not_become_zero():
    offer = PricingService.offer_from_source({
        "title": "Motor fan",
        "url": "https://supplier.example/item",
        "content": "Contact for price.",
    }, COMPATIBILITY)

    assert offer["price_status"] == "quote_required"
    assert offer["original_price"] is None
    assert offer["price_usd"] is None


def test_non_usd_price_is_preserved_without_inventing_conversion():
    offer = PricingService.offer_from_source({
        "title": "Motor fan EUR 120.00",
        "url": "https://supplier.example/item",
        "content": "Example listing.",
    }, COMPATIBILITY)
    totals = PricingService.summarize_usd([offer])

    assert offer["original_price"] == "120.00"
    assert offer["original_currency"] == "EUR"
    assert offer["price_usd"] is None
    assert totals["known_parts_subtotal_usd"] is None
    assert totals["estimated_total_usd"] is None


def test_snippet_price_is_unverified_and_excluded_from_total():
    offer = PricingService.offer_from_source({
        "title": "Motor fan $42.50",
        "url": "https://supplier.example/item",
        "content": "Search result snippet.",
    }, COMPATIBILITY)

    assert offer["original_price"] == "42.50"
    assert offer["original_currency"] == "USD"
    assert offer["price_status"] == "unverified_listing"
    assert offer["price_observation"] == "product_price"
    assert PricingService.summarize_usd([offer])["known_parts_subtotal_usd"] is None


def test_shipping_charge_is_never_presented_as_a_product_price():
    offer = PricingService.offer_from_source({
        "title": "Industrial motor listing",
        "url": "https://supplier.example/item",
        "content": "Shipping charge: $9.95. Contact the supplier for the item price.",
    }, COMPATIBILITY)

    assert offer["original_price"] is None
    assert offer["price_usd"] is None
    assert offer["price_status"] == "unknown"
    assert offer["price_observation"] == "shipping_only"
    assert "shipping" in offer["price_note"].casefold()


def test_product_price_is_retained_when_a_separate_shipping_charge_is_present():
    offer = PricingService.offer_from_source({
        "title": "Industrial motor $2,521.50",
        "url": "https://supplier.example/item",
        "content": "Product price $2,521.50. Shipping charge: $9.95.",
    }, COMPATIBILITY)

    assert offer["original_price"] == "2521.50"
    assert offer["price_usd"] == "2521.50"
    assert offer["price_observation"] == "product_price"
