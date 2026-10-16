import { describe, expect, it } from "vitest";
import type { SupplierOffer } from "@/lib/api";
import { offerHasExplicitModelMismatch, supplierOffersNeedingPriceReview, supplierOffersWithKnownPriceAndAvailability } from "@/lib/procurement";

function offer(overrides: Partial<SupplierOffer> = {}): SupplierOffer {
  return {
    supplier_name: "Demo supplier",
    product_url: "https://supplier.example/item",
    product_name: "Motor cooling fan",
    original_price: 125,
    original_currency: "USD",
    price_usd: 125,
    price_status: "verified_listing",
    compatibility_status: "unknown",
    compatibility_basis: "Not displayed in the streamlined list.",
    availability: "In stock",
    price_checked_at: null,
    evidence_excerpt: null,
    requires_technician_review: true,
    ...overrides,
  };
}

describe("supplier listing display filter", () => {
  it("keeps only listings with a listed price and meaningful availability", () => {
    const visible = supplierOffersWithKnownPriceAndAvailability([
      offer(),
      offer({ product_url: "https://supplier.example/no-price", original_price: null }),
      offer({ product_url: "https://supplier.example/unknown-availability", availability: "Unknown" }),
      offer({ product_url: "https://supplier.example/not-listed", original_price: "Not listed" }),
    ]);

    expect(visible).toHaveLength(1);
    expect(visible[0]?.product_url).toBe("https://supplier.example/item");
  });

  it("does not use compatibility status to decide visibility", () => {
    const visible = supplierOffersWithKnownPriceAndAvailability([
      offer({ compatibility_status: "incompatible" }),
    ]);

    expect(visible).toHaveLength(1);
  });

  it("does not present a shipping charge as an equipment price", () => {
    const shippingOnly = offer({
      product_url: "https://supplier.example/shipping-only",
      original_price: 9.95,
      evidence_excerpt: "Shipping charge: $9.95. Product price available on request.",
    });

    expect(supplierOffersWithKnownPriceAndAvailability([shippingOnly])).toHaveLength(0);
    expect(supplierOffersNeedingPriceReview([shippingOnly])).toHaveLength(1);
  });

  it("flags a source that explicitly names a different model", () => {
    const mismatched = offer({
      product_name: "Siemens motor 1LE1001-1BA23-4AA4",
      evidence_excerpt: "Listing for Siemens 1LE1001-1BA23-4AA4.",
    });

    expect(offerHasExplicitModelMismatch(mismatched, "1LE1001-1AB23-4AA4")).toBe(true);
    expect(offerHasExplicitModelMismatch(mismatched, "1LE1001-1BA23-4AA4")).toBe(false);
  });
});
