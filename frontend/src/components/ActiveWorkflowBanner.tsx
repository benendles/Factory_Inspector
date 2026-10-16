"use client";

import Link from "next/link";
import { ArrowRight, ClipboardCheck, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import { api, type WorkflowResponse } from "@/lib/api";
import {
  CURRENT_WORKFLOW_CHANGED_EVENT,
  CURRENT_WORKFLOW_STORAGE_KEY,
  clearCurrentWorkflow,
  getCurrentWorkflowId,
} from "@/lib/currentWorkflow";

/** A global entry point to the locally remembered, server-owned workflow. */
export function ActiveWorkflowBanner() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadWorkflow = useCallback(async (id: string | null) => {
    if (!id) {
      setWorkflow(null);
      setError(null);
      return;
    }

    setRefreshing(true);
    setError(null);
    try {
      setWorkflow(await api.getWorkflow(id));
    } catch (reason) {
      setWorkflow(null);
      setError(reason instanceof Error ? reason.message : "Could not retrieve the active workflow.");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const syncActiveWorkflow = () => {
      const id = getCurrentWorkflowId();
      setThreadId(id);
      void loadWorkflow(id);
    };

    syncActiveWorkflow();
    window.addEventListener(CURRENT_WORKFLOW_CHANGED_EVENT, syncActiveWorkflow);
    const onStorage = (event: StorageEvent) => {
      if (event.key === CURRENT_WORKFLOW_STORAGE_KEY) syncActiveWorkflow();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(CURRENT_WORKFLOW_CHANGED_EVENT, syncActiveWorkflow);
      window.removeEventListener("storage", onStorage);
    };
  }, [loadWorkflow]);

  if (!threadId) return null;

  const label = workflow
    ? `${workflow.machine_id} · ${workflow.workflow_status.replaceAll("_", " ")}`
    : "Workflow update unavailable";

  return (
    <aside className="mb-6 flex flex-col gap-3 rounded-xl border border-emerald-300/25 bg-emerald-400/10 p-4 sm:flex-row sm:items-center sm:justify-between" aria-live="polite">
      <div className="flex min-w-0 gap-3">
        <ClipboardCheck className="mt-0.5 size-5 shrink-0 text-emerald-200" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-emerald-100">Active AI inspection</p>
          <p className="mt-0.5 truncate text-sm text-slate-300">{label}</p>
          <p className="mt-1 font-mono text-xs text-slate-500">Workflow {threadId}</p>
          {error && <p className="mt-2 text-xs text-amber-200">{error} You can retry from the workflow page when the API is available.</p>}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {workflow && <StatusBadge value={workflow.workflow_status} />}
        <Button variant="secondary" onClick={() => void loadWorkflow(threadId)} disabled={refreshing} aria-label="Refresh active workflow">
          <RefreshCw className={refreshing ? "size-4 animate-spin" : "size-4"} />
          Refresh
        </Button>
        {error && (
          <Button
            variant="secondary"
            onClick={clearCurrentWorkflow}
            aria-label="Clear unavailable workflow"
          >
            <X className="size-4" />
            Clear unavailable workflow
          </Button>
        )}
        <Link href={`/workflow/${encodeURIComponent(threadId)}`} className="inline-flex items-center gap-2 rounded-md bg-emerald-400 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300">
          Open workflow <ArrowRight className="size-4" />
        </Link>
      </div>
    </aside>
  );
}
