import { type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("rounded-xl border border-slate-700/80 bg-slate-900/80 shadow-xl shadow-slate-950/15", className)} {...props} />;
}
