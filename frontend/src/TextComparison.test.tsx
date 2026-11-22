import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import TextComparison from "./TextComparison";
import { type Api } from "./api";

afterEach(cleanup);

test("shows measured text answers and metrics for 2, 3, and 5 agents", async () => {
  const manifest = { dataset: "text", question: "What is my demo balance?", conversation_id: "chat-1",
    input_usd_per_million: "1", output_usd_per_million: "2", price_date: "2026-11-22" };
  const attempts = [2, 3, 5].map((count) => ({ id: String(count), result: {
    status: "completed", answer: { status: "answered", answer: `Balance from ${count} agents`, source_ids: [] },
    configuration: { agent_count: count }, duration_ms: count * 100,
    usage: { input_tokens: 100, output_tokens: 50 }, model_calls: count, tool_calls: 1,
    roles_used: ["supervisor", "account"],
  } }));
  const api: Api = async <T,>(path: string): Promise<T> => {
    if (path === "/evaluation/jobs") return [{ id: "job-1", status: "completed", created_at: "2026-11-22T00:00:00Z", error: null, manifest }] as T;
    if (path === "/evaluation/jobs/job-1?limit=3") return { id: "job-1", status: "completed", completed_count: 3, error: null, manifest, attempts } as T;
    throw new Error(`Unexpected request ${path}`);
  };
  render(<TextComparison api={api} conversationId="chat-1" />);
  expect(await screen.findByText("Balance from 2 agents")).toBeInTheDocument();
  const cards = screen.getAllByRole("article");
  expect(cards).toHaveLength(3);
  expect(within(cards[2]).getByText("Balance from 5 agents")).toBeInTheDocument();
  expect(within(cards[2]).getByText("150")).toBeInTheDocument();
  expect(within(cards[2]).getByText("USD 0.000200")).toBeInTheDocument();
  expect(screen.getByText(/not phone calls/)).toBeInTheDocument();
});
