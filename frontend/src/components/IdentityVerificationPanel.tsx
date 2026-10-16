"use client";

import { CheckCircle2, LockKeyhole } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { Decision, WorkflowResponse } from "@/lib/api";
import { canConfirmIdentity } from "@/lib/workflow";

export function IdentityVerificationPanel({ workflow, onDecide }: { workflow: WorkflowResponse; onDecide: (input: { decision: Decision; reviewer: string; comment?: string }) => Promise<void> }) {
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [decision, setDecision] = useState<Decision>("confirmed");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eligible = canConfirmIdentity(workflow);
  const submit = async (event: React.FormEvent) => { event.preventDefault(); if (!reviewer.trim()) { setError("A reviewer name is required."); return; } setSubmitting(true); setError(null); try { await onDecide({ decision, reviewer, comment }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not record the identity decision."); } finally { setSubmitting(false); } };
  return <Card className="p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row"><div><h3 className="flex items-center gap-2 font-semibold text-white"><CheckCircle2 className="size-4 text-emerald-300" />Human identity verification</h3><p className="mt-1 text-sm text-slate-400">Audited reviewer action. It does not approve or execute maintenance.</p></div><StatusBadge value={workflow.physical_identity_verification_decision ?? (eligible ? "awaiting review" : "blocked")} /></div>{workflow.physical_identity_confirmed ? <div className="mt-5 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-4 text-sm text-emerald-100">Physical identity was confirmed. Audit ID: <span className="font-mono text-xs">{workflow.physical_identity_verification_audit_id}</span>. Maintenance remains separately gated.</div> : eligible ? <form className="mt-5 grid gap-3" onSubmit={submit}><div className="grid gap-3 sm:grid-cols-2"><label className="grid gap-1 text-sm text-slate-300">Decision<select value={decision} onChange={(event) => setDecision(event.target.value as Decision)} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"><option value="confirmed">Confirm physical identity</option><option value="rejected">Reject physical identity</option></select></label><label className="grid gap-1 text-sm text-slate-300">Reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={150} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" placeholder="Qualified reviewer" /></label></div><label className="grid gap-1 text-sm text-slate-300">Audit comment (optional)<textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={1000} className="min-h-20 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" placeholder="Reference the independently checked physical evidence." /></label>{error && <ApiErrorAlert message={error} />}<Button className="w-fit" type="submit" disabled={submitting}>{submitting ? "Recording…" : "Record identity decision"}</Button></form> : <div className="mt-5 flex gap-3 rounded-lg border border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400"><LockKeyhole className="size-5 shrink-0" />Identity confirmation is unavailable until the registry reports one conflict-free verified match. The API remains the final authority.</div>}</Card>;
}
