import { CircleDot } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { WorkflowResponse } from "@/lib/api";

export function IncidentTimeline({ workflow }: { workflow: WorkflowResponse }) {
  const task = workflow.maintenance_task_details;
  const simulatedIncidentResult = workflow.resolved ? "Simulated incident resolved" : "Simulated incident not resolved";
  const workflowStatus = workflow.workflow_status === "incident_resolved" ? "Simulated incident resolved" : workflow.workflow_status;
  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row"><div><h3 className="flex items-center gap-2 font-semibold text-white"><CircleDot className="size-4 text-emerald-300" />Incident & maintenance task</h3><p className="mt-1 text-sm text-slate-400">Workflow context generated from evidence and simulated sensor analysis.</p></div><StatusBadge value={workflowStatus} /></div><div className="mt-5 grid gap-3 md:grid-cols-2"><div className="rounded-lg bg-slate-950/50 p-4"><p className="text-xs font-bold tracking-wider text-slate-500 uppercase">Task</p><p className="mt-2 font-medium text-slate-100">{task?.title ?? "Task details unavailable"}</p><p className="mt-2 text-sm text-slate-400">{task?.problem ?? "No task problem statement available."}</p></div><div className="rounded-lg bg-slate-950/50 p-4"><p className="text-xs font-bold tracking-wider text-slate-500 uppercase">Simulation workflow state</p><dl className="mt-2 space-y-2 text-sm"><div className="flex justify-between gap-2"><dt className="text-slate-400">Maintenance</dt><dd><StatusBadge value={workflow.maintenance_status === "completed" ? "Simulated maintenance completed" : workflow.maintenance_status} /></dd></div><div className="flex justify-between gap-2"><dt className="text-slate-400">Incident result</dt><dd className="text-right text-slate-100">{simulatedIncidentResult}</dd></div><div className="flex justify-between gap-2"><dt className="text-slate-400">Approval required</dt><dd className="text-slate-100">{String(workflow.approval_required)}</dd></div></dl></div></div></Card>;
}
