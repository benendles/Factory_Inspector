import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";

const workflow = (overrides: Record<string, unknown> = {}) => ({
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
});

describe("mocked workflow API journey", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("uploads evidence, records identity, approves maintenance, and receives simulated verification", async () => {
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(workflow()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(workflow({ physical_identity_confirmed: true, physical_verification_required: false, physical_identity_verification_decision: "confirmed", physical_identity_verification_audit_id: "audit-001", repair_plan: { procurement: null } })), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(workflow({ workflow_status: "incident_resolved", approval_required: false, maintenance_status: "completed", verification_result: { outcome: "verified" }, resolved: true })), { status: 200 }));
    vi.stubGlobal("fetch", mockFetch);

    const image = new File(["image"], "motor.png", { type: "image/png" });
    const started = await api.startWorkflowWithImage({ scenarioId: "overheating", machineId: "HACKATHON-SIEMENS-001", image });
    const verified = await api.verifyIdentity(started.thread_id, { decision: "confirmed", reviewer: "demo-reviewer" });
    const completed = await api.decideApproval(verified.thread_id, { decision: "approved", approvalUser: "demo-approver" });

    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(String(mockFetch.mock.calls[0][0])).toContain("/simulator/workflow/with-image");
    expect(mockFetch.mock.calls[0][1]?.body).toBeInstanceOf(FormData);
    expect(String(mockFetch.mock.calls[1][0])).toContain("/identity-verification");
    expect(String(mockFetch.mock.calls[2][0])).toContain("/approval");
    expect(completed.verification_result?.outcome).toBe("verified");
  });

  it("normalizes failed API requests into centralized errors", async () => {
    const response = new Response(
      JSON.stringify({ detail: "Workflow not found." }),
      { status: 404 },
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    await expect(api.getWorkflow("missing-workflow")).rejects.toMatchObject({
      status: 404,
      detail: "Workflow not found.",
    } satisfies Partial<ApiError>);
  });
});
