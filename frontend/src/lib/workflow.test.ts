import { describe, expect, it } from "vitest";
import type { WorkflowResponse } from "@/lib/api";
import { canConfirmIdentity, canDecideMaintenance, deriveWorkflowStages } from "@/lib/workflow";

function workflow(overrides: Partial<WorkflowResponse> = {}): WorkflowResponse {
  return {
    thread_id: "workflow-001",
    machine_id: "HACKATHON-SIEMENS-001",
    workflow_status: "awaiting_approval",
    approval_required: true,
    pending_approval: [],
    physical_identity_confirmed: false,
    physical_verification_required: true,
    physical_identity_verification_decision: null,
    physical_identity_verification_audit_id: null,
    registry_match_status: "verified_match",
    registry_match: { status: "verified_match", identifier_conflicts: [] },
    ...overrides,
  };
}

describe("workflow safety mapping", () => {
  it("allows audited identity review only for a verified conflict-free candidate", () => {
    expect(canConfirmIdentity(workflow())).toBe(true);
    expect(canConfirmIdentity(workflow({ registry_match_status: "possible_match" }))).toBe(false);
    expect(canConfirmIdentity(workflow({ registry_match: { status: "verified_match", identifier_conflicts: ["serial conflict"] } }))).toBe(false);
  });

  it("keeps maintenance approval separate from identity confirmation", () => {
    expect(canDecideMaintenance(workflow())).toBe(false);
    expect(canDecideMaintenance(workflow({ physical_identity_confirmed: true, physical_verification_required: false }))).toBe(true);
  });

  it("maps unavailable evidence and rejected identity to transparent stage states", () => {
    const stages = deriveWorkflowStages(workflow({
      workflow_status: "identity_rejected",
      approval_required: false,
      image_inspection_result: { status: "unavailable" },
    }));

    expect(stages.find((stage) => stage.id === "vision")?.status).toBe("pending");
    expect(stages.find((stage) => stage.id === "identity")?.status).toBe("blocked");
    expect(stages.find((stage) => stage.id === "approval")?.status).toBe("blocked");
  });

  it("shows evidence reconciliation and compatibility review as explicit stages", () => {
    const stages = deriveWorkflowStages(workflow({
      evidence_reconciliation: { status: "completed", contradictions: [] },
      repair_plan: {
        plan_id: "RP-1",
        status: "requires_technical_assessment",
        equipment_identity_confirmed: true,
        requires_technician_review: true,
        requires_human_approval: true,
        parts: [],
        excluded_incompatible_parts: [],
        procurement: {
          research_status: "completed",
          diagnosis: null,
          research_requirements: null,
          supplier_offers: [],
          verified_compatible_parts: [],
          possibly_compatible_parts: [],
          excluded_incompatible_parts: [],
          known_parts_subtotal_usd: null,
          estimated_total_usd: null,
          cost_status: "incomplete",
          requires_supplier_quote: true,
          requires_technician_review: true,
          requires_human_approval: true,
          limitations: [],
        },
      },
    }));

    expect(stages.find((stage) => stage.id === "reconciliation")?.status).toBe("completed");
    expect(stages.find((stage) => stage.id === "compatibility")?.status).toBe("awaiting_review");
  });
});
