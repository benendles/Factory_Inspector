"use client";

import Link from "next/link";
import { AlertTriangle, ClipboardCheck, Cpu, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type DatabaseIncident, type Equipment } from "@/lib/api";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { MetricCard } from "@/components/MetricCard";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { incidentsHref, isOpenIncident } from "@/lib/incidents";

export function FactoryOverview() {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [incidents, setIncidents] = useState<DatabaseIncident[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listEquipment(), api.listIncidents()])
      .then(([registered, listed]) => { setEquipment(registered); setIncidents(listed); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load factory metrics."));
  }, []);

  const critical = incidents.filter((incident) => incident.severity === "critical").length;
  const open = incidents.filter(isOpenIncident).length;

  return <>
    {error && <ApiErrorAlert message={error} />}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Registered machines" value={equipment.length} detail="From the PostgreSQL equipment registry." icon={Cpu} />
      <MetricCard label="Database incidents" value={incidents.length} detail="Persisted incident records; workflow incidents are tracked separately." icon={ClipboardCheck} href="/incidents" />
      <MetricCard label="Critical alerts" value={critical} detail="Based on persisted incident severity." icon={AlertTriangle} href={incidentsHref({ severity: "critical" })} />
      <MetricCard label="Open incidents" value={open} detail="Excludes resolved and closed records." icon={Wrench} href={incidentsHref({ status: "open" })} />
    </div>

    <div className="mt-7 grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
      <Card className="p-6">
        <div className="flex items-center justify-between">
          <div><h2 className="font-semibold text-white">Recent incident records</h2><p className="mt-1 text-sm text-slate-400">Database incidents available through the registry API.</p></div>
          <Link href="/incidents" className="text-sm font-semibold text-emerald-300 hover:text-emerald-200">View all</Link>
        </div>
        <div className="mt-5 space-y-3">
          {incidents.slice(0, 4).map((incident) => {
            const status = isOpenIncident(incident) ? "open" : incident.status;
            return <div key={incident.id} className="flex flex-col gap-2 rounded-lg border border-slate-700 bg-slate-950/30 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div><p className="font-medium text-slate-100">{incident.title}</p><p className="mt-1 text-xs text-slate-400">{incident.incident_number} · {incident.machine_id}</p></div>
              <div className="flex gap-2">
                <Link className="rounded-full focus:outline-none focus:ring-2 focus:ring-emerald-300" href={incidentsHref({ severity: incident.severity })} aria-label={`Show ${incident.severity} incidents`}><StatusBadge value={incident.severity} /></Link>
                <Link className="rounded-full focus:outline-none focus:ring-2 focus:ring-emerald-300" href={incidentsHref({ status })} aria-label={`Show ${status} incidents`}><StatusBadge value={status} /></Link>
              </div>
            </div>;
          })}
          {!incidents.length && <p className="py-8 text-center text-sm text-slate-400">No database incidents are available.</p>}
        </div>
      </Card>
      <Card className="p-6"><p className="text-xs font-bold tracking-[0.15em] text-emerald-300">LIVE DEMO PATH</p><h2 className="mt-3 text-xl font-semibold text-white">Inspect with evidence, then require humans.</h2><ol className="mt-5 space-y-3 text-sm text-slate-300">{["Upload inspection image and scenario.", "Review vision, OCR, sensor, and registry evidence.", "Record an audited physical identity decision.", "Review diagnosis and supplier research.", "Give separate maintenance approval for simulation."].map((step, index) => <li key={step} className="flex gap-3"><span className="grid size-6 shrink-0 place-items-center rounded-full border border-emerald-400/50 text-xs text-emerald-200">{index + 1}</span>{step}</li>)}</ol><Link href="/inspection" className="mt-7 inline-flex rounded-md bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950">Start an AI inspection</Link></Card>
    </div>
  </>;
}
