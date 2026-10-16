import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearCurrentWorkflow,
  CURRENT_WORKFLOW_CHANGED_EVENT,
  CURRENT_WORKFLOW_STORAGE_KEY,
  getCurrentWorkflowId,
  rememberCurrentWorkflow,
} from "@/lib/currentWorkflow";

describe("current workflow pointer", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
      },
    });
  });

  it("persists only the active thread ID and announces a change", () => {
    const listener = vi.fn();
    window.addEventListener(CURRENT_WORKFLOW_CHANGED_EVENT, listener);

    rememberCurrentWorkflow("workflow-123");

    expect(getCurrentWorkflowId()).toBe("workflow-123");
    expect(window.localStorage.getItem(CURRENT_WORKFLOW_STORAGE_KEY)).toBe("workflow-123");
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(CURRENT_WORKFLOW_CHANGED_EVENT, listener);
  });

  it("can explicitly clear the stored pointer without touching backend state", () => {
    rememberCurrentWorkflow("workflow-123");
    clearCurrentWorkflow();
    expect(getCurrentWorkflowId()).toBeNull();
  });
});
