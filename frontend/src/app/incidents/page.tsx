"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { Card } from "@/components/ui/Card";
import { api, type DatabaseIncident, type Severity } from "@/lib/api";
import { filterIncidents, isOpenIncident } from "@/lib/incidents";
import { cn, formatDate } from "@/lib/utils";

const severities: Severity[] = ["critical", "high", "medium", "low"];

function FilterButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} aria-pressed={active} className={cn("rounded-full border px-3 py-1.5 text-xs font-semibold transition focus:outline-none focus:ring-2 focus:ring-emerald-300", active ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-100" : "border-slate-600 bg-slate-950/40 text-slate-300 hover:border-slate-500 hover:text-white")}>{children}</button>;
}

export default function IncidentsPage() {
  return <Suspense fallback={<Card className="p-8 text-sm text-slate-400">Loading incident ledger…</Card>}><IncidentLedger /></Suspense>;
}

function IncidentLedger() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [incidents, setIncidents] = useState<DatabaseIncident[]>([]);
  const [error, setError] = useState<string | null>(null);
  const severityParam = searchParams.get("severity");
  const severity = severities.includes(severityParam as Severity) ? severityParam as Severity : null;
  const status = searchParams.get("status");

  useEffect(() => {
    api.listIncidents().then(setIncidents).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load incidents."));
  }, []);

  const setFilter = (key: "severity" | "status", value: string) => {
    const next = new URLSearchParams(searchParams.toString());
    if (next.get(key) === value) next.delete(key);
    else next.set(key, value);
    const query = next.toString();
    router.replace(query ? `/incidents?${query}` : "/incidents", { scroll: false });
  };

  const clearFilters = () => router.replace("/incidents", { scroll: false });
  const filteredIncidents = useMemo(() => filterIncidents(incidents, { severity, status }), [incidents, severity, status]);
  const filterActive = Boolean(severity || status);

  return <>
    <PageHeader eyebrow="INCIDENT LEDGER" title="Persisted incidents" description="Select a severity or status to filter the database incident API. Open includes every incident that is not resolved or closed." />
    {error && <ApiErrorAlert message={error} />}
    <Card className="mb-6 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-bold tracking-wider text-slate-400 uppercase">Filter incidents</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {severities.map((item) => <FilterButton key={item} active={severity === item} onClick={() => setFilter("severity", item)}>Severity: {item}</FilterButton>)}
            <FilterButton active={status === "open"} onClick={() => setFilter("status", "open")}>Status: open</FilterButton>
          </div>
        </div>
        {filterActive && <button type="button" onClick={clearFilters} className="w-fit text-sm font-semibold text-emerald-300 hover:text-emerald-100 focus:outline-none focus:ring-2 focus:ring-emerald-300">Clear filters</button>}
      </div>
    </Card>
    <div className="grid gap-3">
      {filteredIncidents.map((incident) => {
        const incidentStatus = isOpenIncident(incident) ? "open" : incident.status;
        return <Card className="p-5" key={incident.id}>
          <div className="flex flex-col justify-between gap-3 sm:flex-row">
            <div><p className="font-semibold text-white">{incident.title}</p><p className="mt-1 text-sm text-slate-400">{incident.incident_number} · {incident.machine_id}</p><p className="mt-3 max-w-3xl text-sm text-slate-300">{incident.description || "No description provided."}</p></div>
            <div className="flex h-fit gap-2">
              <button type="button" onClick={() => setFilter("severity", incident.severity)} aria-label={`Filter by ${incident.severity} severity`} className="rounded-full focus:outline-none focus:ring-2 focus:ring-emerald-300"><StatusBadge value={incident.severity} /></button>
              <button type="button" onClick={() => setFilter("status", incidentStatus)} aria-label={`Filter by ${incidentStatus} status`} className="rounded-full focus:outline-none focus:ring-2 focus:ring-emerald-300"><StatusBadge value={incidentStatus} /></button>
            </div>
          </div>
          <p className="mt-4 text-xs text-slate-500">Updated {formatDate(incident.updated_at)}</p>
        </Card>;
      })}
      {!filteredIncidents.length && <Card className="p-10 text-center text-sm text-slate-400">{filterActive ? "No persisted incidents match the selected filters." : "No database incidents are available."}</Card>}
    </div>
  </>;
}
