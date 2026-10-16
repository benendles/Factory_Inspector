import type { WorkflowResponse } from "@/lib/api";

export type DisplayStageStatus =
  | "pending"
  | "completed"
  | "awaiting_review"
  | "awaiting_approval"
  | "blocked"
  | "failed";

export interface WorkflowStage {
  id: string;
  label: string;
  status: DisplayStageStatus;
  detail: string;
}

const noConflicts = (workflow: WorkflowResponse) =>
  (workflow.registry_match?.identifier_conflicts?.length ?? 0) === 0;

export function canConfirmIdentity(workflow: WorkflowResponse) {
  return workflow.workflow_status !== "identity_rejected"
    && workflow.physical_identity_confirmed === false
    && workflow.registry_match_status === "verified_match"
    && workflow.registry_match?.status === "verified_match"
    && noConflicts(workflow)
    && workflow.approval_required;
}

export function canDecideMaintenance(workflow: WorkflowResponse) {
  return workflow.workflow_status === "awaiting_approval"
    && workflow.physical_identity_confirmed === true
    && workflow.physical_verification_required === false
    && workflow.approval_required === true;
}

function evidenceStatus(status: string | undefined): DisplayStageStatus {
  if (status === "error" || status === "failed") return "failed";
  if (status === "unavailable" || status === "not_available") return "pending";
  return status ? "completed" : "pending";
}

export function deriveWorkflowStages(workflow: WorkflowResponse): WorkflowStage[] {
  const rejected = workflow.workflow_status === "identity_rejected";
  const procurement = workflow.repair_plan?.procurement;
  const maintenanceCompleted = workflow.maintenance_status === "completed";
  const reconciliation = workflow.evidence_reconciliation;
  const reconciliationHasConflicts = (reconciliation?.contradictions?.length ?? 0) > 0;
  const incompatibleOffers = procurement?.excluded_incompatible_parts.length ?? 0;

  return [
    {
      id: "image",
      label: "Image upload",
      status: evidenceStatus(workflow.image_evidence?.status),
      detail: String(workflow.image_evidence?.status ?? "No image evidence"),
    },
    {
      id: "vision",
      label: "AMD vision inspection",
      status: evidenceStatus(workflow.image_inspection_result?.status),
      detail: String(workflow.image_inspection_result?.status ?? "Not available"),
    },
    {
      id: "ocr",
      label: "Nameplate OCR",
      status: evidenceStatus(workflow.nameplate_ocr_result?.status),
      detail: String(workflow.nameplate_ocr_result?.provider ?? workflow.nameplate_ocr_result?.status ?? "Not available"),
    },
    {
      id: "reconciliation",
      label: "Evidence reconciliation",
      status: reconciliationHasConflicts ? "awaiting_review" : evidenceStatus(reconciliation?.status),
      detail: reconciliationHasConflicts ? "Evidence disagreement requires review" : String(reconciliation?.status ?? "Not available"),
    },
    {
      id: "registry",
      label: "SQL equipment identification",
      status: workflow.registry_match_status === "verified_match" ? "completed" : "awaiting_review",
      detail: workflow.registry_match_status ?? "Not checked",
    },
    {
      id: "evolus",
      label: "Evolus maintenance foreman",
      status: workflow.evolus_maintenance_assessment?.status === "completed"
        ? "completed"
        : workflow.evolus_maintenance_assessment?.status === "invalid_assessment"
          ? "awaiting_review"
          : workflow.evolus_maintenance_assessment?.status === "not_requested"
            ? "pending"
            : "pending",
      detail: workflow.evolus_maintenance_assessment?.status === "completed"
        ? "Advisory assessment recorded"
        : workflow.evolus_maintenance_assessment?.limitations?.[0] ?? "Advisory assessment unavailable",
    },
    {
      id: "identity",
      label: "Human identity verification",
      status: rejected ? "blocked" : workflow.physical_identity_confirmed ? "completed" : "awaiting_review",
      detail: rejected ? "Identity rejected" : workflow.physical_identity_confirmed ? "Audited confirmation recorded" : "Human confirmation required",
    },
    {
      id: "diagnosis",
      label: "AMD repair diagnosis",
      status: procurement?.diagnosis ? "completed" : workflow.physical_identity_confirmed ? "pending" : "blocked",
      detail: procurement?.diagnosis?.provider ?? "Requires identity confirmation",
    },
    {
      id: "research",
      label: "Tavily supplier research",
      status: procurement?.research_status === "completed" ? "completed" : procurement?.research_status === "research_disabled" ? "pending" : procurement ? "awaiting_review" : "blocked",
      detail: procurement?.research_status ?? "Requires identity confirmation",
    },
    {
      id: "compatibility",
      label: "Compatibility review",
      status: procurement ? "awaiting_review" : "blocked",
      detail: procurement
        ? incompatibleOffers
          ? `${incompatibleOffers} incompatible supplier result${incompatibleOffers === 1 ? "" : "s"} excluded`
          : "Technician fitment review remains required"
        : "Requires identity confirmation",
    },
    {
      id: "approval",
      label: "Human maintenance approval",
      status: rejected ? "blocked" : maintenanceCompleted ? "completed" : canDecideMaintenance(workflow) ? "awaiting_approval" : "blocked",
      detail: maintenanceCompleted ? "Decision recorded" : canDecideMaintenance(workflow) ? "Separate approval required" : "Blocked pending identity review",
    },
    {
      id: "verification",
      label: "Simulated verification",
      status: workflow.verification_result ? "completed" : maintenanceCompleted ? "pending" : "blocked",
      detail: workflow.verification_result?.outcome === "verified" ? "Simulation verification passed" : workflow.verification_result ? String(workflow.verification_result.outcome ?? "Completed") : "Not run",
    },
  ];
}
