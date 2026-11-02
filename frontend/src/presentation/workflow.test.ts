import { expect, test } from "vitest";
import { eventCategory, eventLabel, roleState, type WorkflowTrace } from "./workflow";

const trace: WorkflowTrace = {
  run_id: "run", status: "completed", configuration: { agent_count: 5, architecture: "blackboard", prompt_strategy: "react" },
  configured_roles: { supervisor: "Google ADK", account: "CrewAI", card: "CrewAI", loan: "CrewAI", support: "CrewAI" },
  model_calls: 4, tool_calls: 1, total_tokens: 80,
  artifacts: [{ id: "a1", role: "account", revision: 1, consumed: [], summary: { status: "answered", answer: "Verified balance" }, facts: [{ tool: "account_snapshot" }] }],
  events: [
    { id: "1", sequence: 1, at: "2026-01-01T00:00:00Z", role: "supervisor", kind: "run_start", metadata: {} },
    { id: "2", sequence: 2, at: "2026-01-01T00:00:01Z", role: "supervisor", kind: "a2a_send", metadata: { target: "account" } },
    { id: "3", sequence: 3, at: "2026-01-01T00:00:02Z", role: "account", kind: "tool_result", metadata: { tool: "account_snapshot" } },
    { id: "4", sequence: 4, at: "2026-01-01T00:00:03Z", role: "account", kind: "state_publish", metadata: { revision: 1 } },
    { id: "5", sequence: 5, at: "2026-01-01T00:00:04Z", role: "supervisor", kind: "run_end", metadata: {} },
  ],
};

test("workflow presentation uses only observed events and artifacts", () => {
  expect(roleState(trace, "account")).toBe("completed");
  expect(roleState(trace, "card")).toBe("idle");
  expect(roleState(trace, "supervisor")).toBe("completed");
  expect(roleState(trace, "account", trace.events.slice(0, 2))).toBe("idle");
  expect(eventLabel(trace.events[1])).toBe("Delegated to account");
  expect(eventCategory(trace.events[2])).toBe("tool");
});
