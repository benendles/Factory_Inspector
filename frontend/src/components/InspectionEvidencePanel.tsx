import { CheckCircle2, CircleAlert, Eye, ScanText, Thermometer } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { EvidenceResult, WorkflowResponse } from "@/lib/api";

type EvidenceRecord = Record<string, unknown>;

function asRecord(value: unknown): EvidenceRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as EvidenceRecord
    : {};
}

function readable(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not available";
  return String(value);
}

function labelFor(key: string) {
  return key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function RawEvidence({ value }: { value: unknown }) {
  return <details className="mt-4 rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
    <summary className="cursor-pointer font-semibold text-slate-300">Technical evidence (raw JSON)</summary>
    <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-400">{JSON.stringify(value ?? "Not available", null, 2)}</pre>
  </details>;
}

function FieldGrid({ fields }: { fields: EvidenceRecord }) {
  const visible = Object.entries(fields).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!visible.length) return <p className="mt-4 text-sm text-slate-400">No structured fields were extracted.</p>;
  return <dl className="mt-4 grid gap-2 sm:grid-cols-2">
    {visible.map(([key, value]) => <div className="rounded-md bg-slate-950/50 p-3" key={key}>
      <dt className="text-[11px] font-bold tracking-wide text-slate-500 uppercase">{labelFor(key)}</dt>
      <dd className="mt-1 break-words text-sm text-slate-100">{readable(value)}</dd>
    </div>)}
  </dl>;
}

function observationText(value: string | EvidenceRecord) {
  if (typeof value === "string") return value;
  for (const key of ["description", "finding", "anomaly", "observation", "label", "message"]) {
    if (typeof value[key] === "string") return value[key];
  }
  return Object.entries(value).map(([key, item]) => `${labelFor(key)}: ${readable(item)}`).join(" · ");
}

function VisionCard({ result }: { result?: EvidenceResult }) {
  const equipment = asRecord(result?.equipment);
  const observations = (result?.observations ?? []).map((value) => observationText(value));
  return <Card className="p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 font-semibold text-white"><Eye className="size-4 text-emerald-300" />AMD vision inspection</h3><p className="mt-1 text-sm text-slate-400">Observed image evidence. It does not establish physical identity.</p></div><StatusBadge value={result?.status ?? "not available"} /></div>
    <p className="mt-5 text-xs font-bold tracking-wider text-slate-400 uppercase">Machine identification</p>
    <FieldGrid fields={equipment} />
    <p className="mt-5 text-xs font-bold tracking-wider text-slate-400 uppercase">Anomaly findings</p>
    {observations.length ? <ul className="mt-3 space-y-2 text-sm text-slate-300">{observations.map((observation, index) => <li className="flex gap-2" key={`${observation}-${index}`}><CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-300" />{observation}</li>)}</ul> : <p className="mt-3 text-sm text-slate-400">No image findings were reported.</p>}
    <RawEvidence value={result} />
  </Card>;
}

function OcrCard({ result }: { result?: EvidenceResult }) {
  const fields = asRecord(result?.fields);
  return <Card className="p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 font-semibold text-white"><ScanText className="size-4 text-emerald-300" />Nameplate OCR</h3><p className="mt-1 text-sm text-slate-400">Candidate identifiers extracted from the uploaded image.</p></div><StatusBadge value={result?.provider ?? result?.status ?? "not available"} /></div>
    <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm"><div><dt className="inline text-slate-500">Confidence: </dt><dd className="inline text-slate-100">{result?.confidence === null || result?.confidence === undefined ? "Not available" : `${result.confidence}%`}</dd></div><div><dt className="inline text-slate-500">Status: </dt><dd className="inline text-slate-100">{result?.status ?? "Not available"}</dd></div></dl>
    <FieldGrid fields={fields} />
    <RawEvidence value={result} />
  </Card>;
}

function SensorCard({ readings, workflow }: { readings?: Record<string, unknown>; workflow: WorkflowResponse }) {
  const numeric = Object.entries(readings ?? {}).filter(([, value]) => typeof value === "number") as Array<[string, number]>;
  const severity = workflow.maintenance_task_details?.severity ?? "simulated";
  return <Card className="p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 font-semibold text-white"><Thermometer className="size-4 text-emerald-300" />Simulated sensor evidence</h3><p className="mt-1 text-sm text-slate-400">Scenario readings, not live factory telemetry.</p></div><StatusBadge value={severity} /></div>
    {numeric.length ? <div className="mt-5 space-y-4">{numeric.map(([sensor, value]) => <div key={sensor}><div className="flex items-end justify-between gap-3"><p className="text-sm font-medium text-slate-100">{labelFor(sensor)}</p><p className="text-lg font-semibold text-slate-100">{sensor.endsWith("_c") ? `${value}°C` : value}</p></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-amber-400" style={{ width: `${Math.max(8, Math.min(100, (value / 120) * 100))}%` }} /></div></div>)}</div> : <p className="mt-5 text-sm text-slate-400">No numeric simulated readings are available.</p>}
    <RawEvidence value={readings} />
  </Card>;
}

function ReconciliationCard({ result }: { result?: EvidenceResult }) {
  const agreements = Array.isArray(result?.agreements) ? result.agreements : [];
  const contradictions = result?.contradictions ?? [];
  return <Card className="p-5">
    <div className="flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 font-semibold text-white"><CheckCircle2 className="size-4 text-emerald-300" />Evidence reconciliation</h3><p className="mt-1 text-sm text-slate-400">Cross-check of image and OCR evidence before registry comparison.</p></div><StatusBadge value={contradictions.length ? "review required" : result?.status ?? "not available"} /></div>
    <div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="rounded-md bg-emerald-400/10 p-3"><p className="text-xs font-bold tracking-wide text-emerald-200 uppercase">Agreements</p><p className="mt-2 text-2xl font-semibold text-white">{agreements.length}</p></div><div className="rounded-md bg-rose-400/10 p-3"><p className="text-xs font-bold tracking-wide text-rose-200 uppercase">Contradictions</p><p className="mt-2 text-2xl font-semibold text-white">{contradictions.length}</p></div></div>
    <RawEvidence value={result} />
  </Card>;
}

export function InspectionEvidencePanel({ workflow }: { workflow: WorkflowResponse }) {
  return <div className="grid gap-4 xl:grid-cols-2">
    <VisionCard result={workflow.image_inspection_result} />
    <OcrCard result={workflow.nameplate_ocr_result} />
    <SensorCard readings={workflow.sensor_readings} workflow={workflow} />
    <ReconciliationCard result={workflow.evidence_reconciliation} />
  </div>;
}
