import type { DatabaseIncident, Severity } from "@/lib/api";

const CLOSED_STATUSES = new Set(["closed", "resolved"]);

export type IncidentFilters = {
  severity?: Severity | null;
  status?: string | null;
};

export function isOpenIncident(incident: Pick<DatabaseIncident, "status">) {
  return !CLOSED_STATUSES.has(incident.status.toLowerCase());
}

export function filterIncidents(incidents: DatabaseIncident[], filters: IncidentFilters) {
  return incidents.filter((incident) => {
    const matchesSeverity = !filters.severity || incident.severity === filters.severity;
    const normalizedStatus = filters.status?.toLowerCase();
    const matchesStatus = !normalizedStatus
      || (normalizedStatus === "open" ? isOpenIncident(incident) : incident.status.toLowerCase() === normalizedStatus);
    return matchesSeverity && matchesStatus;
  });
}

export function incidentsHref(filters: IncidentFilters = {}) {
  const query = new URLSearchParams();
  if (filters.severity) query.set("severity", filters.severity);
  if (filters.status) query.set("status", filters.status);
  const value = query.toString();
  return value ? `/incidents?${value}` : "/incidents";
}
