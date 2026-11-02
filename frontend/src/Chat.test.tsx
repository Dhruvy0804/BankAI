import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Api } from "./api";
import Chat from "./Chat";

afterEach(cleanup);

test("shows the owner phone test before a text conversation exists", async () => {
  const api = vi.fn(async (path: string) => {
    if (path === "/chat/status") return {
      configured: true, provider: "gemini", model: "demo", mode: "agents", phone_configured: true,
    };
    if (path.startsWith("/chat/conversations")) return [];
    if (path === "/phone/config") return { allowed_numbers: ["+919876543210"], max_duration_seconds: 300 };
    if (path === "/phone/calls") return [];
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<Chat api={api as Api} />);
  expect(await screen.findByRole("heading", { name: "Phone test with Twilio" })).toBeInTheDocument();
  expect(screen.getByText("Start a conversation to ask a question.")).toBeInTheDocument();
});

test("shows verified work and unused roles in the five-agent trace", async () => {
  const api = vi.fn(async (path: string) => {
    if (path === "/chat/status") return { configured: true, provider: "gemini", model: "demo", mode: "agents" };
    if (path === "/chat/conversations?offset=0") return [{ id: "c1", title: "Demo", created_at: "2026-01-01T00:00:00Z" }];
    if (path === "/chat/conversations/c1") return {
      id: "c1", title: "Demo", created_at: "2026-01-01T00:00:00Z",
      turns: [{ message_id: "m1", user_text: "Check account and EMI", created_at: "2026-01-01T00:00:00Z",
        response: { status: "answered", answer: "**Verified** answer <script>alert(1)</script>", run_id: "r1", request_id: "q1",
          provider: "gemini", model: "demo", duration_ms: 100, input_tokens: 10, output_tokens: 10, total_tokens: 20 } }],
    };
    if (path === "/chat/runs/r1") return {
      status: "completed", model_calls: 4, tool_calls: 2,
      configuration: { agent_count: 5, architecture: "blackboard", prompt_strategy: "react" },
      configured_roles: { supervisor: "Google ADK", account: "CrewAI", card: "CrewAI", loan: "CrewAI", support: "CrewAI" },
      events: [{ id: "e1", at: "2026-01-01T00:00:00Z", role: "supervisor", kind: "agent_start", metadata: {} },
        { id: "e2", at: "2026-01-01T00:00:00Z", role: "loan", kind: "state_consume", metadata: { artifact_id: "a1" } }],
      artifacts: [
        { id: "a1", role: "account", revision: 1, consumed: [], summary: { status: "answered", answer: "Balance confirmed" }, facts: [{ tool: "account_snapshot" }] },
        { id: "a2", role: "loan", revision: 2, consumed: ["a1"], summary: { status: "answered", answer: "EMI calculated" }, facts: [{ tool: "calculate_emi" }] },
      ],
    };
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<Chat api={api as Api} />);
  expect(await screen.findByText("Verified")).toHaveProperty("tagName", "STRONG");
  expect(screen.queryByText("alert(1)")).not.toBeInTheDocument();
  fireEvent.click(await screen.findByText("Agent activity and shared context"));
  expect(await screen.findByRole("heading", { name: "5-agent workflow" })).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "loan agent" })).getByText("EMI calculated")).toBeInTheDocument();
  expect(screen.getByText("Used shared context from: account")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "card agent" })).getByText("Not called for this question")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Fill five-agent demo question" }));
  expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).value).toContain("support ticket");
});

test("shows current customer-scoped demo records for an agent demonstration", async () => {
  const api = vi.fn(async (path: string) => {
    if (path === "/chat/status") return { configured: true, provider: "gemini", model: "demo", mode: "agents" };
    if (path === "/chat/conversations?offset=0") return [];
    if (path === "/accounts") return [{ id: "a1", account_number: "DEMO-ACCT-0001", account_type: "savings", currency: "INR", balance: "11825.25", status: "active" }];
    if (path === "/transactions?limit=100") return { items: [{ id: "t1", account_id: "a1", description: "Demo grocery purchase", merchant: "Demo Merchant", reference_code: "DEMO-TXN-0001-01", occurred_at: "2026-10-02T09:00:00Z", status: "completed", transaction_type: "debit", amount: "125.50" }], next_cursor: null };
    if (path === "/cards") return [{ id: "card1", account_id: "a1", masked_card_number: "DEMO-XXXX-0001", card_type: "debit", status: "active" }];
    if (path === "/loans") return [{ id: "loan1", loan_type: "personal", requested_amount: "100000.00", annual_interest_rate: "10.5000", tenure_months: 12, status: "draft" }];
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<Chat api={api as Api} />);
  expect(api).not.toHaveBeenCalledWith("/accounts", undefined, expect.anything());
  fireEvent.click(screen.getByText("View my demo banking records"));
  expect(await within(await screen.findByRole("region", { name: "Demo accounts" })).findByText("DEMO-ACCT-0001")).toBeInTheDocument();
  expect(await within(screen.getByRole("region", { name: "Demo transactions" })).findByText("Demo grocery purchase")).toBeInTheDocument();
  expect(await within(screen.getByRole("region", { name: "Demo cards" })).findByText("DEMO-XXXX-0001")).toBeInTheDocument();
  expect(await within(screen.getByRole("region", { name: "Demo loans" })).findByText("personal")).toBeInTheDocument();
});
