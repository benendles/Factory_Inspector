export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type Severity = "low" | "medium" | "high" | "critical";
export type Decision = "confirmed" | "rejected";
export type ApprovalDecision = "approved" | "rejected";

export interface Equipment {
  id: string;
  machine_id: string;
  name: string | null;
  manufacturer: string | null;
  model_number: string | null;
  serial_number: string | null;
  asset_tag: string | null;
  location: string | null;
  equipment_type: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DatabaseIncident {
  id: string;
  incident_number: string;
  machine_id: string;
  title: string;
  description: string;
  severity: Severity;
  status: string;
  requires_human_review: boolean;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface Scenario {
  scenario_id: string;
  name?: string;
  description?: string;
  [key: string]: unknown;
}

export interface ScenarioResponse {
  scenarios: Scenario[];
  thresholds_are_simulated: boolean;
}

export interface RegistryCandidate {
  id?: string;
  machine_id?: string;
  manufacturer?: string | null;
  model_number?: string | null;
  serial_number?: string | null;
  asset_tag?: string | null;
  equipment_type?: string | null;
  [key: string]: unknown;
}

export interface RegistryMatch {
  status?: string;
  candidate?: RegistryCandidate | null;
  identifier_conflicts?: string[];
  physical_identity_confirmed?: boolean;
  physical_verification_required?: boolean;
  [key: string]: unknown;
}

export interface EvidenceResult {
  status?: string;
  provider?: string;
  fields?: Record<string, unknown>;
  confidence?: number | null;
  observations?: Array<string | Record<string, unknown>>;
  equipment?: Record<string, unknown>;
  contradictions?: Array<Record<string, unknown>>;
  missing_fields?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface SupplierOffer {
  supplier_name: string | null;
  product_url: string;
  product_name: string;
  original_price: string | number | null;
  original_currency: string | null;
  price_usd: string | number | null;
  price_status: "verified_listing" | "unverified_listing" | "quote_required" | "unknown";
  price_observation?: "product_price" | "shipping_only" | "quote_required" | "not_found";
  price_note?: string | null;
  compatibility_status: "verified_compatible" | "possibly_compatible" | "incompatible" | "unknown";
  compatibility_basis: string;
  availability: string;
  price_checked_at: string | null;
  evidence_excerpt: string | null;
  evidence_used?: Record<string, unknown>;
  requires_technician_review: boolean;
}

export interface RepairDiagnosis {
  diagnosis_status: string;
  provider: string;
  confirmed_findings: string[];
  possible_causes: Array<{
    cause: string;
    evidence: string[];
    confirmation_required: boolean;
    source?: string;
  }>;
  recommended_actions: Array<{
    action: string;
    action_type: string;
    priority: string;
    requires_qualified_technician: boolean;
    source?: string;
  }>;
  replacement_justified: boolean;
  requires_technician_review: boolean;
  amd_enrichment?: {
    status: string;
    response_format: string;
    hypotheses_proposed: number;
    hypotheses_accepted: number;
    actions_proposed: number;
    actions_accepted: number;
  };
  limitations: string[];
}

export interface ProcurementProposal {
  research_status: string;
  diagnosis: RepairDiagnosis | null;
  research_requirements: {
    queries: string[];
    candidate_part_category: string;
    research_reason: string;
    [key: string]: unknown;
  } | null;
  supplier_offers: SupplierOffer[];
  verified_compatible_parts: SupplierOffer[];
  possibly_compatible_parts: SupplierOffer[];
  excluded_incompatible_parts: SupplierOffer[];
  known_parts_subtotal_usd: string | null;
  estimated_total_usd: string | null;
  cost_status: string;
  requires_supplier_quote: boolean;
  requires_technician_review: boolean;
  requires_human_approval: boolean;
  limitations: string[];
}

export interface RepairPlan {
  plan_id: string | null;
  status: string;
  equipment_identity_confirmed: boolean;
  requires_technician_review: boolean;
  requires_human_approval: boolean;
  parts: Array<Record<string, unknown>>;
  excluded_incompatible_parts: Array<Record<string, unknown>>;
  procurement: ProcurementProposal | null;
  [key: string]: unknown;
}

export interface EvolusMaintenanceAssessment {
  incident_id: string;
  equipment_id: string;
  severity: string;
  observed_evidence: Array<string | Record<string, unknown>>;
  possible_causes: Array<string | Record<string, unknown>>;
  recommended_actions: Array<string | Record<string, unknown>>;
  required_parts: Array<string | Record<string, unknown>>;
  safety_precautions: Array<string | Record<string, unknown>>;
  human_approval_required: true;
  next_steps: Array<string | Record<string, unknown>>;
  safety_certified: false;
}

export interface EvolusMaintenanceAssessmentResult {
  status: string;
  assessment: EvolusMaintenanceAssessment | null;
  raw_answer?: string | null;
  conversation_id?: string | null;
  agent_id?: string | null;
  requires_human_approval: true;
  safety_certified: false;
  retry_after_seconds?: number | null;
  limitations?: string[];
}

export interface EvolusEvidenceContext {
  schema_version?: string;
  observed_evidence?: {
    sensor_anomalies?: Array<Record<string, unknown>>;
    amd_vision?: {
      source?: string;
      status?: string;
      summary?: string | null;
      equipment_identification_candidate?: Record<string, unknown>;
      visual_observations?: Array<string | Record<string, unknown>>;
      requires_human_review?: boolean;
      is_physical_identity_proof?: false;
    };
    nameplate_ocr?: {
      source?: string;
      status?: string;
      provider?: string | null;
      confidence?: number | null;
      fields?: Record<string, unknown>;
      requires_human_review?: boolean;
      is_physical_identity_proof?: false;
    };
    evidence_reconciliation?: {
      status?: string;
      agreements?: Array<Record<string, unknown>>;
      contradictions?: Array<Record<string, unknown>>;
    };
  };
  registry_comparison?: {
    source?: string;
    status?: string;
    candidate?: RegistryCandidate | null;
    matched_identifiers?: string[];
    identifier_conflicts?: string[];
    is_physical_identity_proof?: false;
  };
  interpretation_constraints?: string[];
  safety_certified?: false;
}

export interface MaintenanceTask {
  task_id?: string;
  title?: string;
  problem?: string;
  severity?: Severity;
  status?: string;
  requires_human_approval?: boolean;
  recommended_actions?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface WorkflowResponse {
  thread_id: string;
  machine_id: string;
  scenario_id?: string;
  workflow_status: string;
  approval_required: boolean;
  pending_approval: Array<Record<string, unknown>>;
  physical_identity_confirmed: boolean;
  physical_verification_required: boolean;
  physical_identity_verification_decision: Decision | null;
  physical_identity_verification_audit_id: string | null;
  registry_match_status?: string;
  registry_match?: RegistryMatch;
  image_evidence?: EvidenceResult;
  image_inspection_result?: EvidenceResult;
  nameplate_ocr_result?: EvidenceResult;
  evidence_reconciliation?: EvidenceResult;
  incident_details?: Record<string, unknown>;
  maintenance_status?: string;
  maintenance_task_details?: MaintenanceTask;
  repair_plan?: RepairPlan | null;
  evolus_maintenance_assessment?: EvolusMaintenanceAssessmentResult;
  evolus_evidence_context?: EvolusEvidenceContext;
  sensor_readings?: Record<string, unknown>;
  pre_maintenance_readings?: Record<string, unknown>;
  post_maintenance_readings?: Record<string, unknown>;
  verification_result?: Record<string, unknown>;
  resolved?: boolean;
  safety_certified?: boolean;
  error?: string | null;
  [key: string]: unknown;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "The Factory Inspector API is unavailable.");
  }

  const body = await response.json().catch(() => null) as unknown;
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String(body.detail)
      : "The request could not be completed.";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export const api = {
  listEquipment: () => request<Equipment[]>("/equipment"),
  listIncidents: () => request<DatabaseIncident[]>("/incidents"),
  listScenarios: () => request<ScenarioResponse>("/simulator/scenarios"),
  getWorkflow: (threadId: string) => request<WorkflowResponse>(`/simulator/workflow/${threadId}`),
  startWorkflowWithImage: (input: { scenarioId: string; machineId: string; image: File }) => {
    const form = new FormData();
    form.set("scenario_id", input.scenarioId);
    form.set("machine_id", input.machineId);
    form.set("image", input.image);
    return request<WorkflowResponse>("/simulator/workflow/with-image", { method: "POST", body: form });
  },
  verifyIdentity: (threadId: string, input: {
    decision: Decision;
    reviewer: string;
    comment?: string;
    evidence?: Record<string, unknown>;
  }) => request<WorkflowResponse>(`/simulator/workflow/${threadId}/identity-verification`, {
    method: "POST",
    body: JSON.stringify({ evidence: {}, ...input }),
  }),
  decideApproval: (threadId: string, input: {
    decision: ApprovalDecision;
    approvalUser: string;
    approvalComment?: string;
  }) => request<WorkflowResponse>(`/simulator/workflow/${threadId}/approval`, {
    method: "POST",
    body: JSON.stringify({
      decision: input.decision,
      approval_user: input.approvalUser,
      approval_comment: input.approvalComment,
    }),
  }),
};
