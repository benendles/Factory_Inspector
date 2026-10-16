import Link from "next/link";
import { type LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/Card";

type MetricCardProps = {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
  href?: string;
};

export function MetricCard({ label, value, detail, icon: Icon, href }: MetricCardProps) {
  const content = (
    <Card className={href ? "h-full p-5 transition hover:border-emerald-400/50 hover:bg-slate-900" : "p-5"}>
      <div className="flex items-start justify-between">
        <div><p className="text-xs font-bold tracking-wider text-slate-400 uppercase">{label}</p><p className="mt-3 text-3xl font-bold text-white">{value}</p></div>
        <span className="rounded-lg bg-emerald-400/10 p-2 text-emerald-300"><Icon className="size-5" /></span>
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-400">{detail}{href ? " Select to view matching incidents." : ""}</p>
    </Card>
  );

  return href ? <Link className="block focus:outline-none focus:ring-2 focus:ring-emerald-300" href={href} aria-label={`View ${label.toLowerCase()}`}>{content}</Link> : content;
}
