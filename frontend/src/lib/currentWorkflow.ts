export const CURRENT_WORKFLOW_STORAGE_KEY = "factory-inspector-current-thread";
export const CURRENT_WORKFLOW_CHANGED_EVENT = "factory-inspector-current-workflow-changed";

function isBrowser() {
  return typeof window !== "undefined";
}

/**
 * The dashboard intentionally keeps only one pointer in browser storage: the
 * workflow the operator most recently opened. Workflow state remains owned by
 * the FastAPI/LangGraph backend and is always fetched again before display.
 */
export function getCurrentWorkflowId() {
  if (!isBrowser()) return null;
  return window.localStorage.getItem(CURRENT_WORKFLOW_STORAGE_KEY);
}

export function rememberCurrentWorkflow(threadId: string) {
  if (!isBrowser() || !threadId) return;
  window.localStorage.setItem(CURRENT_WORKFLOW_STORAGE_KEY, threadId);
  window.dispatchEvent(new Event(CURRENT_WORKFLOW_CHANGED_EVENT));
}

export function clearCurrentWorkflow() {
  if (!isBrowser()) return;
  window.localStorage.removeItem(CURRENT_WORKFLOW_STORAGE_KEY);
  window.dispatchEvent(new Event(CURRENT_WORKFLOW_CHANGED_EVENT));
}
