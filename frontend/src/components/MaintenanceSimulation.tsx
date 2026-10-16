"use client";

import { Activity, FlaskConical, ShieldAlert } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { WorkflowResponse } from "@/lib/api";

function numericReadings(readings?: Record<string, unknown>) {
  return Object.entries(readings ?? {}).flatMap(([sensor, value]) => typeof value === "number" ? [{ sensor, value }] : []);
}

export function MaintenanceSimulation({ workflow }: { workflow: WorkflowResponse }) {
  const before = numericReadings(workflow.pre_maintenance_readings ?? workflow.sensor_readings);
  const after = numericReadings(workflow.post_maintenance_readings);
  const data = Array.from(new Set([...before, ...after].map((item) => item.sensor))).map((sensor) => ({ sensor, before: before.find((item) => item.sensor === sensor)?.value, after: after.find((item) => item.sensor === sensor)?.value }));
  const outcome = String(workflow.verification_result?.outcome ?? "");
  const verificationLabel = outcome === "verified" ? "Simulation verification passed" : outcome ? `Simulation verification: ${outcome}` : workflow.maintenance_status === "completed" ? "Simulated maintenance completed" : "Simulation not run";
  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row"><div><h3 className="flex items-center gap-2 font-semibold text-white"><FlaskConical className="size-4 text-emerald-300" />Maintenance simulation & verification</h3><p className="mt-1 text-sm text-slate-400">All readings and outcomes below are simulated. They are not a physical safety certification.</p></div><StatusBadge value={verificationLabel} /></div>{data.length ? <div className="mt-5 h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={data}><CartesianGrid stroke="#233c55" vertical={false} /><XAxis dataKey="sensor" stroke="#94a8ba" tickLine={false} axisLine={false} /><YAxis stroke="#94a8ba" tickLine={false} axisLine={false} /><Tooltip contentStyle={{ background: "#0d1a29", border: "1px solid #233c55", borderRadius: 8 }} /><Bar dataKey="before" name="Before (simulated)" fill="#f3ba4c" radius={[4, 4, 0, 0]} /><Bar dataKey="after" name="After (simulated)" fill="#3dd6a2" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div> : <div className="mt-5 flex gap-3 rounded-lg bg-slate-950/40 p-5 text-sm text-slate-400"><Activity className="size-5 shrink-0" />Simulated before-and-after readings are published only after the workflow is approved and reaches verification.</div>}<div className="mt-5 flex gap-3 rounded-lg border border-rose-400/30 bg-rose-400/10 p-4 text-sm text-rose-100"><ShieldAlert className="mt-0.5 size-5 shrink-0" /><p><strong>Physical safety: {workflow.safety_certified ? "Safety state reported by API" : "Not certified"}.</strong> Simulation verification is limited to configured evidence and does not certify real-world safety.</p></div><details className="mt-4 rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs text-slate-400"><summary className="cursor-pointer font-semibold text-slate-300">Technical simulation evidence (raw JSON)</summary><pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5">{JSON.stringify({ before: workflow.pre_maintenance_readings ?? workflow.sensor_readings, after: workflow.post_maintenance_readings, verification: workflow.verification_result }, null, 2)}</pre></details></Card>;
}
