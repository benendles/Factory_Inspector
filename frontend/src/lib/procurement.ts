import type { SupplierOffer } from "@/lib/api";

const UNKNOWN_VALUES = new Set([
  "",
  "unknown",
  "not available",
  "not listed",
  "n/a",
  "na",
  "none",
  "pending",
  "tbd",
  "unavailable",
]);

function isKnownText(value: string | null | undefined) {
  return value !== null
    && value !== undefined
    && !UNKNOWN_VALUES.has(value.trim().toLowerCase());
}

function hasListedPrice(value: SupplierOffer["original_price"]) {
  return value !== null
    && value !== undefined
    && !UNKNOWN_VALUES.has(String(value).trim().toLowerCase());
}

function normalise(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function priceLooksLikeShippingCharge(offer: SupplierOffer) {
  if (offer.price_observation === "shipping_only") return true;
  if (!hasListedPrice(offer.original_price) || !offer.evidence_excerpt) return false;

  const amount = String(offer.original_price).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?:\\$|USD\\s*)?${amount}(?:0)?`, "i").exec(offer.evidence_excerpt);
  if (!match) return false;

  const prefix = offer.evidence_excerpt.slice(Math.max(0, match.index - 36), match.index);
  const suffix = offer.evidence_excerpt.slice(match.index + match[0].length, match.index + match[0].length + 24);
  return /\b(shipping|postage|delivery|freight|handling)\b/i.test(prefix)
    || /^\s*(?:for\s+)?(?:shipping|postage|delivery|freight|handling)\b/i.test(suffix);
}

export function hasReliableProductPrice(offer: SupplierOffer) {
  return hasListedPrice(offer.original_price) && !priceLooksLikeShippingCharge(offer);
}

export function supplierOffersNeedingPriceReview(offers: SupplierOffer[]) {
  return offers.filter((offer) => isKnownText(offer.availability) && priceLooksLikeShippingCharge(offer));
}

export function offerHasExplicitModelMismatch(offer: SupplierOffer, verifiedModel?: string | null) {
  if (/different model|model mismatch/i.test(offer.compatibility_basis ?? "")) return true;
  if (!verifiedModel) return false;

  const expected = normalise(verifiedModel);
  const sourceCandidates = Array.isArray(offer.evidence_used?.source_model_candidates)
    ? offer.evidence_used.source_model_candidates.filter((value): value is string => typeof value === "string")
    : [];
  const sourceText = `${offer.product_name} ${offer.evidence_excerpt ?? ""}`;
  const modelLikeTokens = sourceText.match(/\b(?=[A-Za-z0-9-]{5,}\b)(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b/g) ?? [];
  const candidates = [...sourceCandidates, ...modelLikeTokens];
  const normalisedCandidates = new Set(candidates.map(normalise).filter(Boolean));

  return normalisedCandidates.size > 0
    && !normalisedCandidates.has(expected)
    && [...normalisedCandidates].some((candidate) => candidate !== expected);
}

/**
 * Supplier research can contain partial search results. The streamlined table
 * intentionally presents only listings with a product price and meaningful
 * availability. Shipping charges are not product prices.
 */
export function supplierOffersWithKnownPriceAndAvailability(offers: SupplierOffer[]) {
  return offers.filter((offer) => hasReliableProductPrice(offer) && isKnownText(offer.availability));
}
