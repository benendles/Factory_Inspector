import { CheckCircle2, Fingerprint, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { WorkflowResponse } from "@/lib/api";

export function RegistryMatchPanel({ workflow }: { workflow: WorkflowResponse }) {
  const candidate = workflow.registry_match?.candidate;
  const conflicts = workflow.registry_match?.identifier_conflicts ?? [];
  const ocrFields = workflow.nameplate_ocr_result?.fields ?? {};
  const visionEquipment = workflow.image_inspection_result?.equipment ?? {};
  const identifiers = [
    ["Machine", "machine_id"],
    ["Manufacturer", "manufacturer"],
    ["Model", "model_number"],
    ["Serial", "serial_number"],
  ] as const;
  const observed = (key: string) => ocrFields[key] ?? visionEquipment[key];
  const raw = workflow.registry_match;

  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><h3 className="flex items-center gap-2 font-semibold text-white"><Fingerprint className="size-4 text-emerald-300" />SQL registry comparison</h3><p className="mt-1 text-sm text-slate-400">Observed identifiers are compared with a registry candidate; only a human can confirm the physical asset.</p></div><StatusBadge value={workflow.registry_match_status} /></div><div className="mt-5 overflow-x-auto"><table className="w-full min-w-135 text-left text-sm"><thead className="border-b border-slate-700 text-xs tracking-wide text-slate-500 uppercase"><tr><th className="px-2 py-2">Identifier</th><th className="px-2 py-2">Observed</th><th className="px-2 py-2">Registry candidate</th></tr></thead><tbody>{identifiers.map(([label, key]) => <tr className="border-b border-slate-800" key={key}><th className="px-2 py-3 font-medium text-slate-300">{label}</th><td className="px-2 py-3 text-slate-100">{String(observed(key) ?? "Not available")}</td><td className="px-2 py-3 text-slate-100">{String(candidate?.[key] ?? "Not available")}</td></tr>)}</tbody></table></div>{conflicts.length > 0 ? <div className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100"><p className="flex items-center gap-2 font-semibold"><ShieldAlert className="size-4" />Identifier conflicts</p><ul className="mt-2 list-disc space-y-1 pl-5">{conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}</ul></div> : <div className="mt-4 flex gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-100"><CheckCircle2 className="mt-0.5 size-4 shrink-0" /><p>No identifier conflicts were reported. A human physical-identity decision is still required.</p></div>}<details className="mt-4 rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs text-slate-400"><summary className="cursor-pointer font-semibold text-slate-300">Technical registry evidence (raw JSON)</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5">{JSON.stringify(raw ?? "Not available", null, 2)}</pre></details></Card>;
}
