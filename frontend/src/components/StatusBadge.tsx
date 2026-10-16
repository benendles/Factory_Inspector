import { cn } from "@/lib/utils";

const color = (value: string) => {
  const normalized = value.toLowerCase();
  if (/(critical|failed|rejected|blocked|error|incompatible)/.test(normalized)) return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  if (/(awaiting|pending|review|warning|unknown|possible|unverified)/.test(normalized)) return "border-amber-400/30 bg-amber-400/10 text-amber-100";
  if (/(completed|confirmed|verified|resolved|approved|healthy)/.test(normalized)) return "border-emerald-400/30 bg-emerald-400/10 text-emerald-100";
  return "border-slate-500/40 bg-slate-700/40 text-slate-200";
};

export function StatusBadge({ value, className }: { value?: string | null; className?: string }) {
  const label = value?.replaceAll("_", " ") ?? "not available";
  return <span className={cn("inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold capitalize tracking-wide", color(label), className)}>{label}</span>;
}
