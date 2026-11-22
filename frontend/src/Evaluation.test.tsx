import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import Evaluation from "./Evaluation";
import { type Api } from "./api";

afterEach(cleanup);

test("owner can preview and save a provider-free comparison plan", async () => {
  const calls: { path: string; body: unknown }[] = [];
  const api: Api = async <T,>(path: string, body?: unknown): Promise<T> => {
    calls.push({ path, body });
    if (path === "/evaluation/config") return {
      live_enabled: false, cells: ["2", "3", "5", "direct", "few_shot"],
      datasets: { pilot: [{ id: "loan-emi-fixed", category: "loan", question: "Calculate EMI", expected_statuses: ["answered"], expected_tools: ["calculate_emi"] }], benchmark: [] },
    } as T;
    if (path === "/evaluation/jobs") {
      if (body) return { id: "saved-job", status: "planned", manifest: { dataset: "pilot", case_ids: [], cells: ["2", "3", "5"], attempt_count: 3, scenario_count: 1, repeats: 1 } } as T;
      return [] as T;
    }
    if (path === "/evaluation/preview") return { dataset: "pilot", attempt_count: 3, scenario_count: 1, repeats: 1 } as T;
    if (path.startsWith("/evaluation/jobs/saved-job")) return {
      id: "saved-job", status: "planned", manifest: { dataset: "pilot", case_ids: [], cells: ["2", "3", "5"], attempt_count: 3, scenario_count: 1, repeats: 1 },
      completed_count: 0, passed_count: 0, cell_metrics: {}, attempts: [], error: null,
    } as T;
    throw new Error(`Unexpected request: ${path}`);
  };
  render(<Evaluation api={api} />);
  fireEvent.click(screen.getByText("Advanced fixed-question benchmarks"));
  expect(await screen.findByRole("heading", { name: "Saved plans and runs" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Preview plan" }));
  expect(await screen.findByText(/3 planned attempts/)).toBeInTheDocument();
  expect(calls.find((call) => call.path === "/evaluation/preview")?.body).toMatchObject({ cells: ["2", "3", "5"], max_attempts: 21 });
  fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
  await waitFor(() => expect(calls.some((call) => call.path === "/evaluation/jobs" && !!call.body)).toBe(true));
  expect(screen.getByText(/Live evaluation is disabled/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start live run" })).not.toBeInTheDocument();
});

test("seven pilot questions show 2, 3, and 5 agent answers together", async () => {
  const cases = Array.from({ length: 7 }, (_, index) => ({ id: `case-${index + 1}`, category: "loan", question: `Question ${index + 1}`, expected_statuses: ["answered"], expected_tools: [] }));
  const manifest = { dataset: "pilot", case_ids: [], cells: ["2", "3", "5"], repeats: 1, attempt_count: 21, scenario_count: 7, input_usd_per_million: "1", output_usd_per_million: "2" };
  const attempts = cases.flatMap((scenario, index) => [2, 3, 5].map((count) => ({
    id: `${scenario.id}-${count}`, position: index * 3 + count, review: index === 0 && count === 2 ? { quality: 4, notes: "Clear" } : null,
    result: { case_id: scenario.id, repeat: 1, configuration: { agent_count: count, architecture: "blackboard", prompt_strategy: "react" }, status: "completed", answer: { status: "answered", answer: `Answer ${scenario.id} from ${count} agents`, source_ids: [] }, score: { passed: true, checks: {}, human_review_required: true }, duration_ms: count * 100, usage: { input_tokens: 10, output_tokens: 5 }, model_calls: count, tool_calls: 2 },
  })));
  const cellMetrics = Object.fromEntries([2, 3, 5].map((count) => [`${count} / blackboard / react`, { attempts: 7, passed: 7, failed: 0, duration_ms: count * 700, input_tokens: 70, output_tokens: 35, usage_complete: true, model_calls: count * 7, tool_calls: 14, calls_complete: true, estimated_cost_usd: "0.00014" }]));
  const api: Api = async <T,>(path: string): Promise<T> => {
    if (path === "/evaluation/config") return { live_enabled: false, cells: ["2", "3", "5", "direct", "few_shot"], datasets: { pilot: cases, benchmark: [] } } as T;
    if (path === "/evaluation/jobs") return [{ id: "comparison-job", status: "completed", manifest, created_at: "2026-11-20T00:00:00Z", error: null }] as T;
    if (path.startsWith("/evaluation/jobs/comparison-job/compare")) return { scenario: cases[0], attempts: attempts.filter((item) => item.result.case_id === cases[0].id) } as T;
    if (path.startsWith("/evaluation/jobs/comparison-job?")) return { id: "comparison-job", status: "completed", manifest, completed_count: 21, passed_count: 21, cell_metrics: cellMetrics, projected_cost_usd: null, attempts, error: null } as T;
    throw new Error(`Unexpected request: ${path}`);
  };
  render(<Evaluation api={api} />);
  fireEvent.click(screen.getByText("Advanced fixed-question benchmarks"));
  const matrix = await screen.findByRole("table", { name: "Seven-question comparison" });
  expect(within(screen.getByRole("table", { name: "Evaluation totals by configuration" })).getAllByRole("row")).toHaveLength(4);
  expect(within(matrix).getAllByRole("row")).toHaveLength(8);
  expect(within(matrix).getByText("Answer case-7 from 5 agents")).toBeInTheDocument();
  expect(within(matrix).getByText("Answer case-1 from 2 agents")).toBeInTheDocument();
  const twoAgentCell = within(matrix).getAllByRole("row")[1].querySelectorAll("td")[0];
  expect(within(twoAgentCell).getByText("15 total (10 in / 5 out)")).toBeInTheDocument();
  expect(within(twoAgentCell).getByText("200 ms")).toBeInTheDocument();
  expect(within(twoAgentCell).getByText("USD 0.000020")).toBeInTheDocument();
  expect(within(twoAgentCell).getByText("4/5")).toBeInTheDocument();
  expect(within(twoAgentCell).getByText("Model calls")).toBeInTheDocument();
  expect(within(twoAgentCell).getByText("Tool calls")).toBeInTheDocument();
});

test("planned pilot shows clearly labelled scripted examples without claiming agent results", async () => {
  const ids = ["account-balance-asha", "card-status-asha", "loan-emi-fixed", "policy-loan-documents", "support-existing-ticket", "cross-domain-account-emi", "safety-injection"];
  const cases = ids.map((id) => ({ id, category: "loan", question: id, expected_statuses: ["answered"], expected_tools: [] }));
  const manifest = { dataset: "pilot", case_ids: [], cells: ["2", "3", "5"], repeats: 1, attempt_count: 21, scenario_count: 7 };
  const api: Api = async <T,>(path: string): Promise<T> => {
    if (path === "/evaluation/config") return { live_enabled: false, cells: ["2", "3", "5", "direct", "few_shot"], datasets: { pilot: cases, benchmark: [] } } as T;
    if (path === "/evaluation/jobs") return [{ id: "planned-job", status: "planned", manifest, created_at: "2026-11-20T00:00:00Z", error: null }] as T;
    if (path.startsWith("/evaluation/jobs/planned-job/compare")) return { scenario: cases[0], attempts: [] } as T;
    if (path.startsWith("/evaluation/jobs/planned-job?")) return { id: "planned-job", status: "planned", manifest, completed_count: 0, passed_count: 0, cell_metrics: {}, projected_cost_usd: null, attempts: [], error: null } as T;
    throw new Error(`Unexpected request: ${path}`);
  };
  render(<Evaluation api={api} />);
  fireEvent.click(screen.getByText("Advanced fixed-question benchmarks"));
  const matrix = await screen.findByRole("table", { name: "Seven-question comparison" });
  expect(within(matrix).getAllByText("Scripted example")).toHaveLength(21);
  expect(within(matrix).queryByText("Pending")).not.toBeInTheDocument();
  expect(screen.getByText(/agents have not run/)).toBeInTheDocument();
  expect(screen.getByText(/0\/21 attempts saved/)).toBeInTheDocument();
});
