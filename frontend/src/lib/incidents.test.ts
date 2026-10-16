import { describe, expect, it } from "vitest";
import type { DatabaseIncident } from "@/lib/api";
import { filterIncidents, incidentsHref, isOpenIncident } from "@/lib/incidents";

function incident(overrides: Partial<DatabaseIncident> = {}): DatabaseIncident {
  return {
    id: "incident-1",
    incident_number: "INC-1",
    machine_id: "MACHINE-1",
    title: "Temperature alert",
    description: "Simulated alert",
    severity: "critical",
    status: "open",
    requires_human_review: true,
    created_at: "2026-10-16T00:00:00Z",
    updated_at: "2026-10-16T00:00:00Z",
    closed_at: null,
    ...overrides,
  };
}

describe("incident filters", () => {
  it("treats open as every incident that is not closed or resolved", () => {
    expect(isOpenIncident(incident({ status: "open" }))).toBe(true);
    expect(isOpenIncident(incident({ status: "in_progress" }))).toBe(true);
    expect(isOpenIncident(incident({ status: "resolved" }))).toBe(false);
  });

  it("combines critical and open filters for the incident ledger", () => {
    const results = filterIncidents([
      incident(),
      incident({ id: "incident-2", severity: "medium" }),
      incident({ id: "incident-3", status: "resolved" }),
    ], { severity: "critical", status: "open" });

    expect(results.map((item) => item.id)).toEqual(["incident-1"]);
    expect(incidentsHref({ severity: "critical", status: "open" })).toBe("/incidents?severity=critical&status=open");
  });
});
