import { Check, CircleAlert, Clock3, LockKeyhole, X } from "lucide-react";
import { type DisplayStageStatus, type WorkflowStage } from "@/lib/workflow";
import { cn } from "@/lib/utils";

const iconFor: Record<DisplayStageStatus, typeof Check> = { completed: Check, awaiting_review: CircleAlert, awaiting_approval: Clock3, blocked: LockKeyhole, failed: X, pending: Clock3 };
const classFor: Record<DisplayStageStatus, string> = { completed: "border-emerald-400/50 bg-emerald-400/10 text-emerald-200", awaiting_review: "border-amber-400/50 bg-amber-400/10 text-amber-100", awaiting_approval: "border-amber-400/50 bg-amber-400/10 text-amber-100", blocked: "border-slate-600 bg-slate-800 text-slate-400", failed: "border-rose-400/50 bg-rose-400/10 text-rose-100", pending: "border-slate-600 bg-slate-800 text-slate-300" };

export function WorkflowStepper({ stages }: { stages: WorkflowStage[] }) {
  return <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{stages.map((stage, index) => { const Icon = iconFor[stage.status]; return <li key={stage.id} className={cn("flex gap-3 rounded-lg border p-3", classFor[stage.status])}><span className="grid size-7 shrink-0 place-items-center rounded-full border border-current/30 text-xs font-bold">{stage.status === "completed" ? <Icon className="size-4" /> : index + 1}</span><span><span className="block text-sm font-semibold">{stage.label}</span><span className="mt-1 block text-xs opacity-80">{stage.detail}</span></span></li>; })}</ol>;
}
