import { type ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <header className="mb-8 flex flex-col justify-between gap-5 lg:flex-row lg:items-end"><div><p className="mb-2 text-xs font-bold tracking-[0.18em] text-emerald-300">{eyebrow}</p><h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{description}</p></div>{action}</header>;
}
