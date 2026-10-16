"use client";

import { BadgeCheck, LockKeyhole } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/StatusBadge";
import type { ApprovalDecision, WorkflowResponse } from "@/lib/api";
import { canDecideMaintenance } from "@/lib/workflow";

export function MaintenanceApprovalPanel({ workflow, onDecide }: { workflow: WorkflowResponse; onDecide: (input: { decision: ApprovalDecision; approvalUser: string; approvalComment?: string }) => Promise<void> }) {
  const [approvalUser, setApprovalUser] = useState("");
  const [approvalComment, setApprovalComment] = useState("");
  const [decision, setDecision] = useState<ApprovalDecision>("approved");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eligible = canDecideMaintenance(workflow);
  const submit = async (event: React.FormEvent) => { event.preventDefault(); if (!approvalUser.trim()) { setError("An approver name is required."); return; } setSubmitting(true); setError(null); try { await onDecide({ decision, approvalUser, approvalComment }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not process maintenance approval."); } finally { setSubmitting(false); } };
  const status = workflow.maintenance_status === "completed" ? "Simulated maintenance completed" : workflow.maintenance_status ?? (eligible ? "awaiting approval" : "blocked");
  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row"><div><h3 className="flex items-center gap-2 font-semibold text-white"><BadgeCheck className="size-4 text-emerald-300" />Separate maintenance approval</h3><p className="mt-1 text-sm text-slate-400">This is the only dashboard action that resumes the paused simulation workflow.</p></div><StatusBadge value={status} /></div>{eligible ? <form className="mt-5 grid gap-3" onSubmit={submit}><div className="grid gap-3 sm:grid-cols-2"><label className="grid gap-1 text-sm text-slate-300">Decision<select value={decision} onChange={(event) => setDecision(event.target.value as ApprovalDecision)} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"><option value="approved">Approve simulated maintenance</option><option value="rejected">Reject maintenance</option></select></label><label className="grid gap-1 text-sm text-slate-300">Approver<input value={approvalUser} onChange={(event) => setApprovalUser(event.target.value)} maxLength={150} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" placeholder="Authorized reviewer" /></label></div><label className="grid gap-1 text-sm text-slate-300">Comment (optional)<textarea value={approvalComment} onChange={(event) => setApprovalComment(event.target.value)} maxLength={1000} className="min-h-20 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" placeholder="Document the approval decision." /></label>{error && <ApiErrorAlert message={error} />}<Button className="w-fit" type="submit" disabled={submitting}>{submitting ? "Processing…" : "Submit maintenance decision"}</Button></form> : <div className="mt-5 flex gap-3 rounded-lg border border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400"><LockKeyhole className="size-5 shrink-0" />Maintenance cannot be approved until a confirmed physical identity is audited and the workflow reports a pending approval. This action never certifies physical safety.</div>}</Card>;
}
