import { Bot, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { EvolusEvidenceContext, EvolusMaintenanceAssessmentResult } from "@/lib/api";

type AdvisoryValue = string | Record<string, unknown>;

function readable(value: AdvisoryValue) {
  if (typeof value === "string") return value;
  return Object.entries(value).map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`).join(" · ");
}

function AdvisoryList({ title, values }: { title: string; values: AdvisoryValue[] }) {
  return <div className="rounded-lg bg-slate-950/40 p-4"><p className="text-xs font-bold tracking-wider text-slate-400 uppercase">{title}</p>{values.length ? <ul className="mt-3 space-y-2 text-sm text-slate-200">{values.map((value, index) => <li className="flex gap-2" key={`${readable(value)}-${index}`}><span className="mt-2 size-1.5 shrink-0 rounded-full bg-emerald-300" />{readable(value)}</li>)}</ul> : <p className="mt-3 text-sm text-slate-500">No advisory items returned.</p>}</div>;
}

function candidateSummary(candidate?: Record<string, unknown> | null) {
  if (!candidate) return "No candidate identifiers supplied.";
  const values = [candidate.manufacturer, candidate.model_number, candidate.serial_number, candidate.equipment_type]
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  return values.length ? values.join(" · ") : "No candidate identifiers supplied.";
}

function EvidenceSourceSummary({ context }: { context?: EvolusEvidenceContext }) {
  const observed = context?.observed_evidence;
  const vision = observed?.amd_vision;
  const ocr = observed?.nameplate_ocr;
  const reconciliation = observed?.evidence_reconciliation;
  const registry = context?.registry_comparison;
  if (!context) return null;
  return <section className="mt-5 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-4"><div><p className="text-xs font-bold tracking-wider text-cyan-200 uppercase">Evidence supplied to advisory</p><p className="mt-1 text-sm text-slate-300">Source-labelled observations and candidates supplied to Evolus. None establish physical identity or safety.</p></div><div className="mt-4 grid gap-3 md:grid-cols-2"><div className="rounded-md bg-slate-950/50 p-3 text-sm"><p className="font-medium text-slate-100">AMD Vision <StatusBadge value={vision?.status ?? "unavailable"} /></p><p className="mt-2 text-slate-400">{candidateSummary(vision?.equipment_identification_candidate)}</p></div><div className="rounded-md bg-slate-950/50 p-3 text-sm"><p className="font-medium text-slate-100">Nameplate OCR <StatusBadge value={ocr?.status ?? "unavailable"} /></p><p className="mt-2 text-slate-400">{candidateSummary(ocr?.fields)}{ocr?.provider ? ` · ${ocr.provider}` : ""}{typeof ocr?.confidence === "number" ? ` · ${ocr.confidence.toFixed(1)}% confidence` : ""}</p></div><div className="rounded-md bg-slate-950/50 p-3 text-sm"><p className="font-medium text-slate-100">Evidence reconciliation <StatusBadge value={reconciliation?.status ?? "unavailable"} /></p><p className="mt-2 text-slate-400">{reconciliation?.agreements?.length ?? 0} agreement(s), {reconciliation?.contradictions?.length ?? 0} contradiction(s).</p></div><div className="rounded-md bg-slate-950/50 p-3 text-sm"><p className="font-medium text-slate-100">SQL registry <StatusBadge value={registry?.status ?? "not checked"} /></p><p className="mt-2 text-slate-400">{candidateSummary(registry?.candidate)} · {registry?.identifier_conflicts?.length ?? 0} identifier conflict(s).</p></div></div></section>;
}

export function EvolusAssessmentPanel({ result, evidenceContext }: { result?: EvolusMaintenanceAssessmentResult; evidenceContext?: EvolusEvidenceContext }) {
  const assessment = result?.assessment;
  const limitations = result?.limitations ?? [];
  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><h3 className="flex items-center gap-2 font-semibold text-white"><Bot className="size-4 text-emerald-300" />Evolus Digital Maintenance Foreman</h3><p className="mt-1 text-sm text-slate-400">AI advisory assessment only. It cannot confirm identity, approve maintenance, or certify safety.</p></div><StatusBadge value={result?.status ?? "not requested"} /></div><EvidenceSourceSummary context={evidenceContext} />{assessment ? <><dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3"><div className="rounded-md bg-slate-950/50 p-3"><dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Incident</dt><dd className="mt-1 break-all text-slate-100">{assessment.incident_id}</dd></div><div className="rounded-md bg-slate-950/50 p-3"><dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Equipment</dt><dd className="mt-1 break-all text-slate-100">{assessment.equipment_id}</dd></div><div className="rounded-md bg-slate-950/50 p-3"><dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">Severity</dt><dd className="mt-1 text-slate-100">{assessment.severity}</dd></div></dl><div className="mt-4 grid gap-4 xl:grid-cols-2"><AdvisoryList title="Observed evidence" values={assessment.observed_evidence} /><AdvisoryList title="Possible causes" values={assessment.possible_causes} /><AdvisoryList title="Recommended actions" values={assessment.recommended_actions} /><AdvisoryList title="Safety precautions" values={assessment.safety_precautions} /><AdvisoryList title="Required parts" values={assessment.required_parts} /><AdvisoryList title="Next steps" values={assessment.next_steps} /></div></> : <div className="mt-5 rounded-lg bg-slate-950/40 p-4 text-sm text-slate-400">{limitations[0] ?? "No Evolus assessment is available for this workflow."}</div>}<div className="mt-5 flex gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100"><ShieldAlert className="mt-0.5 size-5 shrink-0" /><p><strong>Human approval remains required.</strong> This advisory output does not execute maintenance and physical safety is not certified.</p></div>{result?.raw_answer ? <details className="mt-4 rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs text-slate-400"><summary className="cursor-pointer font-semibold text-slate-300">Technical agent response</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5">{result.raw_answer}</pre></details> : null}</Card>;
}
