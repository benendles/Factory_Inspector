"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { IdentityVerificationPanel } from "@/components/IdentityVerificationPanel";
import { EvolusAssessmentPanel } from "@/components/EvolusAssessmentPanel";
import { IncidentTimeline } from "@/components/IncidentTimeline";
import { InspectionEvidencePanel } from "@/components/InspectionEvidencePanel";
import { MaintenanceApprovalPanel } from "@/components/MaintenanceApprovalPanel";
import { MaintenanceSimulation } from "@/components/MaintenanceSimulation";
import { ProcurementPanel } from "@/components/ProcurementPanel";
import { RegistryMatchPanel } from "@/components/RegistryMatchPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api, type ApprovalDecision, type Decision, type WorkflowResponse } from "@/lib/api";
import { rememberCurrentWorkflow } from "@/lib/currentWorkflow";
import { deriveWorkflowStages } from "@/lib/workflow";
import { WorkflowStepper } from "@/components/WorkflowStepper";

export function WorkflowDashboard({ threadId }: { threadId: string }) {
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => { setRefreshing(true); setError(null); try { const response = await api.getWorkflow(threadId); setWorkflow(response); rememberCurrentWorkflow(threadId); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load the workflow."); } finally { setRefreshing(false); } }, [threadId]);
  useEffect(() => { void refresh(); }, [refresh]);
  const verifyIdentity = async (input: { decision: Decision; reviewer: string; comment?: string }) => { const response = await api.verifyIdentity(threadId, input); setWorkflow(response); rememberCurrentWorkflow(threadId); };
  const decideApproval = async (input: { decision: ApprovalDecision; approvalUser: string; approvalComment?: string }) => { const response = await api.decideApproval(threadId, input); setWorkflow(response); rememberCurrentWorkflow(threadId); };
  if (!workflow && !error) return <Card className="p-8 text-sm text-slate-400">Loading workflow…</Card>;
  if (!workflow) return <ApiErrorAlert message={error ?? "Workflow unavailable."} />;
  const stages = deriveWorkflowStages(workflow);
  const workflowStatusLabel = workflow.workflow_status === "incident_resolved" ? "Simulated incident resolved" : workflow.workflow_status;
  return <div className="space-y-6">{error && <ApiErrorAlert message={error} />}<Card className="p-5"><div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start"><div><div className="flex flex-wrap items-center gap-2"><StatusBadge value={workflowStatusLabel} /><StatusBadge value={workflow.safety_certified ? "safety certified" : "not safety certified"} /></div><h2 className="mt-3 text-xl font-semibold text-white">{workflow.machine_id}</h2><p className="mt-1 font-mono text-xs text-slate-500">Workflow {workflow.thread_id}</p></div><Button variant="secondary" onClick={() => void refresh()} disabled={refreshing}><RefreshCw className={refreshing ? "size-4 animate-spin" : "size-4"} />Refresh workflow</Button></div>{workflow.error && <p className="mt-4 rounded-md border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-100">{workflow.error}</p>}</Card><section><div className="mb-3"><p className="text-xs font-bold tracking-[0.16em] text-emerald-300">AGENT WORKFLOW</p><h2 className="mt-1 text-xl font-semibold text-white">Evidence, decisions, and human checkpoints</h2></div><WorkflowStepper stages={stages} /></section><InspectionEvidencePanel workflow={workflow} /><div className="grid gap-6 xl:grid-cols-2"><RegistryMatchPanel workflow={workflow} /><IncidentTimeline workflow={workflow} /></div><EvolusAssessmentPanel result={workflow.evolus_maintenance_assessment} /><div className="grid gap-6 xl:grid-cols-2"><IdentityVerificationPanel workflow={workflow} onDecide={verifyIdentity} /><MaintenanceApprovalPanel workflow={workflow} onDecide={decideApproval} /></div><ProcurementPanel procurement={workflow.repair_plan?.procurement} verifiedModel={workflow.registry_match?.candidate?.model_number} /><MaintenanceSimulation workflow={workflow} /></div>;
}
