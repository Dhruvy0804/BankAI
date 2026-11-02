export type WorkflowEvent = {
  id: string;
  sequence: number;
  at: string;
  role: string;
  kind: string;
  metadata: Record<string, unknown>;
};

export type WorkflowArtifact = {
  id: string;
  role: string;
  revision: number;
  consumed: string[];
  summary: { status: string; answer: string };
  facts: { tool: string }[];
};

export type WorkflowTrace = {
  run_id: string;
  status: string;
  configuration: { agent_count: number; architecture: string; prompt_strategy: string };
  configured_roles: Record<string, string>;
  model_calls: number;
  tool_calls: number;
  total_tokens: number | null;
  artifacts: WorkflowArtifact[];
  events: WorkflowEvent[];
};

export const roleDescription: Record<string, string> = {
  supervisor: "Routes work and validates the response",
  account: "Accounts, balances, KYC, transactions",
  card: "Card status and pending block requests",
  loan: "EMI, demo eligibility, loan requests",
  support: "Tickets and policy retrieval",
  account_card: "Accounts and cards",
  loan_support: "Loans, tickets, policies",
  generalist: "Banking and support tasks",
};

export function roleState(trace: WorkflowTrace, role: string, events = trace.events) {
  if (events.some((event) => event.role === role && ["agent_error", "run_error", "tool_error"].includes(event.kind))) return "failed";
  if (role === "supervisor") return !events.some((event) => event.kind === "run_start") ? "idle" : trace.status === "failed" && events.some((event) => event.kind === "run_error") ? "failed" : trace.status === "completed" && events.some((event) => event.kind === "run_end") ? "completed" : "active";
  if (trace.artifacts.some((artifact) => artifact.role === role && events.some((event) => event.kind === "state_publish" && event.role === role))) return "completed";
  if (trace.status === "running" && events.some((event) => event.role === role && event.kind === "agent_start")) return "active";
  return events.some((event) => event.role === role && event.kind === "agent_start") ? "unknown" : "idle";
}

export function eventLabel(event: WorkflowEvent) {
  const tool = typeof event.metadata.tool === "string" ? event.metadata.tool.replaceAll("_", " ") : "banking tool";
  const target = typeof event.metadata.target === "string" ? event.metadata.target.replaceAll("_", " ") : "specialist";
  const labels: Record<string, string> = {
    run_start: "Run started", run_end: "Response completed", run_error: "Run failed",
    agent_start: "Agent started", agent_end: "Agent finished", agent_error: "Agent failed",
    a2a_send: `Delegated to ${target}`, a2a_received: "A2A task received", a2a_result: `Result from ${target}`,
    a2a_completed: "A2A task completed", state_consume: "Read Blackboard context",
    message_consume: "Received direct context", state_publish: "Published shared result",
    tool_start: `Started ${tool}`, tool_result: `Completed ${tool}`, tool_error: `Tool failed: ${tool}`,
    mcp_request: `MCP request: ${tool}`, mcp_response: `MCP response: ${tool}`,
    retrieval_result: "Policy retrieval returned", output_validated: "Structured output validated",
    guardrail_rejected: "Request rejected by guardrail", validation_error: "Output validation failed",
    model_end: "Model response received", model_error: "Model call failed", agent_step: "Agent step recorded",
  };
  return labels[event.kind] || event.kind.replaceAll("_", " ");
}

export function eventCategory(event: WorkflowEvent) {
  if (event.kind.includes("error") || event.kind === "guardrail_rejected") return "failed";
  if (event.kind.includes("tool") || event.kind.startsWith("mcp_")) return "tool";
  if (event.kind === "retrieval_result") return "retrieval";
  if (event.kind.startsWith("a2a_") || event.kind.includes("consume") || event.kind === "state_publish") return "handoff";
  return "agent";
}
