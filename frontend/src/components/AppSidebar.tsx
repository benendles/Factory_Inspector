"use client";

import Link from "next/link";
import { Activity, Bot, Building2, ClipboardCheck, Factory, LayoutDashboard } from "lucide-react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/registry", label: "Equipment registry", icon: Building2 },
  { href: "/inspection", label: "AI inspection", icon: Bot },
  { href: "/incidents", label: "Incidents", icon: ClipboardCheck },
];

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="border-b border-slate-700/80 bg-slate-950/80 px-4 py-4 backdrop-blur lg:min-h-screen lg:border-r lg:border-b-0 lg:px-5 lg:py-7">
      <Link href="/" className="flex items-center gap-3 px-2">
        <span className="grid size-10 place-items-center rounded-xl bg-emerald-400 text-slate-950"><Factory className="size-5" /></span>
        <span><strong className="block text-sm tracking-wide">FACTORY INSPECTOR</strong><small className="text-xs text-slate-400">Evidence-first operations</small></span>
      </Link>
      <nav className="mt-6 flex gap-2 overflow-x-auto lg:flex-col">
        {links.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === href : pathname.startsWith(href);
          return <Link key={href} href={href} className={cn("flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition", active ? "bg-emerald-400/15 text-emerald-200" : "text-slate-300 hover:bg-slate-800 hover:text-white")}><Icon className="size-4" />{label}</Link>;
        })}
      </nav>
      <div className="mt-8 hidden rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-slate-400 lg:block">
        <div className="mb-2 flex items-center gap-2 text-emerald-200"><Activity className="size-3.5" /> SIMULATION SAFETY</div>
        Simulated readings and verification never establish real-world safety certification.
      </div>
    </aside>
  );
}
