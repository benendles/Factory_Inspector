import { ExternalLink, SearchCheck, TriangleAlert } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { ProcurementProposal, SupplierOffer } from "@/lib/api";
import { offerHasExplicitModelMismatch, supplierOffersNeedingPriceReview, supplierOffersWithKnownPriceAndAvailability } from "@/lib/procurement";
import { formatMoney } from "@/lib/utils";

function SupplierListingCard({ offer, verifiedModel }: { offer: SupplierOffer; verifiedModel?: string | null }) {
  const modelMismatch = offerHasExplicitModelMismatch(offer, verifiedModel);
  return <article className="rounded-lg border border-slate-700 bg-slate-950/40 p-4">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><a className="inline-flex items-center gap-1 font-medium text-emerald-300 hover:text-emerald-100" href={offer.product_url} target="_blank" rel="noreferrer">{offer.product_name}<ExternalLink className="size-3" /></a><p className="mt-2 text-xs leading-5 text-slate-500">{offer.evidence_excerpt ?? "No retained supplier excerpt."}</p></div><StatusBadge value={offer.price_status} /></div>
    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Listed product price</dt><dd className="mt-1 font-semibold text-slate-100">{formatMoney(offer.original_price, offer.original_currency ?? "USD")}</dd></div><div><dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Availability</dt><dd className="mt-1 text-slate-100">{offer.availability}</dd></div></dl>
    {offer.price_note ? <p className="mt-3 text-xs text-slate-400">{offer.price_note}</p> : null}
    {modelMismatch && <div className="mt-4 flex gap-2 rounded-md border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100"><TriangleAlert className="mt-0.5 size-4 shrink-0" /><p><strong>Different model detected.</strong> This listing does not match the verified model {verifiedModel ?? "for this workflow"}; it is not a compatible replacement recommendation.</p></div>}
  </article>;
}

function PriceReviewCard({ offer, verifiedModel }: { offer: SupplierOffer; verifiedModel?: string | null }) {
  const modelMismatch = offerHasExplicitModelMismatch(offer, verifiedModel);
  return <article className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="font-semibold">Price unverified</p><a className="mt-1 inline-flex items-center gap-1 text-amber-50 underline decoration-amber-200/50 underline-offset-2" href={offer.product_url} target="_blank" rel="noreferrer">{offer.product_name}<ExternalLink className="size-3" /></a></div><StatusBadge value="review required" /></div><p className="mt-3 text-amber-100/80">{offer.price_note ?? "The retained source did not provide a trustworthy product price."}</p>{modelMismatch && <p className="mt-3 rounded-md bg-rose-400/15 p-3 text-rose-100"><strong>Different model detected.</strong> This source must not be treated as compatible with {verifiedModel ?? "the verified asset"}.</p>}<details className="mt-3 text-xs text-amber-100/80"><summary className="cursor-pointer font-semibold">Show retained supplier excerpt</summary><p className="mt-2 whitespace-pre-wrap">{offer.evidence_excerpt ?? "No retained excerpt."}</p></details></article>;
}

export function ProcurementPanel({ procurement, verifiedModel }: { procurement?: ProcurementProposal | null; verifiedModel?: string | null }) {
  if (!procurement) {
    return <Card className="p-6 text-sm text-slate-400">Procurement research is unavailable until an audited identity confirmation produces a repair plan.</Card>;
  }

  const diagnosis = procurement.diagnosis;
  const listings = supplierOffersWithKnownPriceAndAvailability(procurement.supplier_offers);
  const priceReviewListings = supplierOffersNeedingPriceReview(procurement.supplier_offers);

  return (
    <Card className="p-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-white"><SearchCheck className="size-4 text-emerald-300" />AI repair & procurement research</h3>
          <p className="mt-1 text-sm text-slate-400">Only supplier listings with a product price and known availability are shown. Shipping charges are never displayed as an equipment price.</p>
        </div>
        <StatusBadge value={procurement.research_status} />
      </div>

      {diagnosis && (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-4">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Preliminary diagnosis</p>
            <p className="mt-2 text-sm font-semibold text-slate-100">{diagnosis.provider}</p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {diagnosis.possible_causes.map((cause) => <li key={cause.cause}>{cause.cause} <span className="text-slate-500">— confirmation required</span></li>)}
            </ul>
          </div>
          <div className="rounded-lg border border-slate-700 bg-slate-950/40 p-4">
            <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">AMD enrichment</p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-slate-500">Status</dt><dd className="mt-1"><StatusBadge value={diagnosis.amd_enrichment?.status ?? "not available"} /></dd></div>
              <div><dt className="text-slate-500">Provider</dt><dd className="mt-1 break-all text-slate-200">{diagnosis.provider}</dd></div>
              <div><dt className="text-slate-500">Hypotheses</dt><dd className="mt-1 text-slate-200">{diagnosis.amd_enrichment?.hypotheses_accepted ?? 0} accepted / {diagnosis.amd_enrichment?.hypotheses_proposed ?? 0} proposed</dd></div>
              <div><dt className="text-slate-500">Actions</dt><dd className="mt-1 text-slate-200">{diagnosis.amd_enrichment?.actions_accepted ?? 0} accepted / {diagnosis.amd_enrichment?.actions_proposed ?? 0} proposed</dd></div>
            </dl>
          </div>
        </div>
      )}

      {procurement.research_requirements?.queries?.length ? (
        <div className="mt-4 rounded-lg bg-slate-950/40 p-4">
          <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Research queries</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">{procurement.research_requirements.queries.map((query) => <li key={query}>{query}</li>)}</ul>
        </div>
      ) : null}

      <section className="mt-5"><div className="mb-3 flex items-center justify-between gap-3"><p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Supplier discovery</p><span className="text-xs text-slate-500">{listings.length} priced listing{listings.length === 1 ? "" : "s"}</span></div>{listings.length ? <div className="grid gap-3 lg:grid-cols-2">{listings.map((offer) => <SupplierListingCard offer={offer} verifiedModel={verifiedModel} key={offer.product_url} />)}</div> : <div className="rounded-lg bg-slate-950/40 p-4 text-sm text-slate-400">No supplier listings have both a product price and known availability.</div>}</section>

      {priceReviewListings.length ? <section className="mt-5"><p className="text-xs font-bold tracking-wider text-amber-200 uppercase">Excluded price observations</p><p className="mt-1 text-sm text-slate-400">These sources are retained for review but excluded from displayed prices and all totals.</p><div className="mt-3 grid gap-3 lg:grid-cols-2">{priceReviewListings.map((offer) => <PriceReviewCard offer={offer} verifiedModel={verifiedModel} key={offer.product_url} />)}</div></section> : null}

      <div className="mt-5 flex gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
        <TriangleAlert className="mt-0.5 size-5 shrink-0" />
        <div>
          <p className="font-semibold">Cost estimate remains intentionally incomplete</p>
          <p className="mt-1 text-amber-100/80">Known parts subtotal: {formatMoney(procurement.known_parts_subtotal_usd)} · Estimated total: {formatMoney(procurement.estimated_total_usd)}. Labour, transport, tax, unverified prices, and quote-only listings are excluded.</p>
        </div>
      </div>
    </Card>
  );
}
