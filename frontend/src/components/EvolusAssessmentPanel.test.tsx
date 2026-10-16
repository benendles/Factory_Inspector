import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvolusAssessmentPanel } from "@/components/EvolusAssessmentPanel";

describe("EvolusAssessmentPanel", () => {
  it("renders a completed advisory assessment without presenting it as approval or safety certification", () => {
    render(
      <EvolusAssessmentPanel
        result={{
          status: "completed",
          assessment: {
            incident_id: "INC-3F2B6D04",
            equipment_id: "HACKATHON-SIEMENS-001",
            severity: "critical",
            observed_evidence: ["Simulated temperature: 95 C"],
            possible_causes: ["Restricted cooling airflow"],
            recommended_actions: ["Inspect cooling fins"],
            required_parts: [],
            safety_precautions: ["Use qualified technicians"],
            human_approval_required: true,
            next_steps: ["Await maintenance approval"],
            safety_certified: false,
          },
          raw_answer: "Structured advisory response",
          requires_human_approval: true,
          safety_certified: false,
          limitations: ["Advisory output only."],
        }}
      />,
    );

    expect(screen.getByText("Evolus Digital Maintenance Foreman")).toBeVisible();
    expect(screen.getByText("completed")).toBeVisible();
    expect(screen.getByText("INC-3F2B6D04")).toBeVisible();
    expect(screen.getByText("Simulated temperature: 95 C")).toBeVisible();
    expect(screen.getByText("Restricted cooling airflow")).toBeVisible();
    expect(screen.getByText("Human approval remains required.")).toBeVisible();
    expect(
      screen.getByText(/cannot confirm identity, approve maintenance, or certify safety/i),
    ).toBeVisible();
  });
});
