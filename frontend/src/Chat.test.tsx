import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { type Api, ApiError } from "./api";
import Chat from "./Chat";

afterEach(cleanup);
const conversation = { id: "c1", title: "New conversation", created_at: "2026-10-20T10:00:00Z" };
const reply = {
  status: "guidance", answer: "An EMI is a monthly instalment. <script>unsafe()</script>",
  request_id: "request-1", run_id: "run-1", provider: "gemini", model: "test-model",
  duration_ms: 20, total_tokens: 30,
};

function fixture(configured = true, failFirst = false) {
  const turns: unknown[] = [];
  let attempts = 0;
  const mock = vi.fn(async (path: string, body?: unknown) => {
    if (path === "/chat/status") return { configured, provider: "gemini", model: "test-model" };
    if (path.startsWith("/chat/conversations?")) return [conversation];
    if (path === "/chat/conversations/c1") return { ...conversation, turns: [...turns] };
    if (path === "/chat") {
      attempts++;
      if (failFirst && attempts === 1) throw new ApiError("Provider unavailable", 503, "request-failed");
      const data = body as { message: string; message_id: string };
      turns.push({ user_text: data.message, message_id: data.message_id, response: reply });
      return reply;
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  return { mock, api: mock as Api };
}

test("sends a question, shows saved plain-text response and structured details, reopens history", async () => {
  const { api, mock } = fixture();
  const view = render(<Chat api={api} />);
  fireEvent.change(await screen.findByLabelText("Your question"), { target: { value: "What is an EMI?" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText(reply.answer)).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByLabelText("Your question")).toHaveValue("");
  expect(screen.getByText("Response details")).toBeInTheDocument();
  const body = mock.mock.calls.find(([path]) => path === "/chat")![1] as Record<string, string>;
  expect(body.conversation_id).toBe("c1");
  expect(body.message_id).toMatch(/^[0-9a-f-]{36}$/);
  view.unmount();
  render(<Chat api={api} />);
  expect(await screen.findByText(reply.answer)).toBeInTheDocument();
});

test("preserves text and message ID when retrying a failed submission", async () => {
  const { api, mock } = fixture(true, true);
  render(<Chat api={api} />);
  fireEvent.change(await screen.findByLabelText("Your question"), { target: { value: "Explain interest" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Provider unavailable")).toBeInTheDocument();
  expect(screen.getByLabelText("Your question")).toHaveValue("Explain interest");
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText(reply.answer)).toBeInTheDocument();
  const calls = mock.mock.calls.filter(([path]) => path === "/chat");
  expect(calls[0][1]).toEqual(calls[1][1]);
});

test("missing configuration disables generation but keeps saved history accessible", async () => {
  const { api, mock } = fixture(false);
  render(<Chat api={api} />);
  expect(await screen.findByText(/unavailable until the backend model provider/)).toBeInTheDocument();
  fireEvent.change(await screen.findByLabelText("Your question"), { target: { value: "Hello" } });
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  expect(mock.mock.calls.filter(([path]) => path === "/chat")).toHaveLength(0);
});

test("agent activity opens lazily and a pending action requires explicit confirmation", async () => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) { this.removeAttribute("open"); },
  });
  const pending = {
    id: "pending-1", resource_id: "card-1", kind: "block_card",
    payload: { masked_card_number: "DEMO-XXXX-0001" },
    expires_at: new Date(Date.now() + 300000).toISOString(),
  };
  const mock = vi.fn(async (path: string) => {
    if (path === "/chat/status") return { configured: true, provider: "gemini", model: "test-model", mode: "agents" };
    if (path.startsWith("/chat/conversations?")) return [conversation];
    if (path === "/chat/conversations/c1") return { ...conversation, turns: [{
      message_id: "message-1", user_text: "Block my demo card", response: {
        ...reply, prompt_version: "phase6-blackboard-v1", pending_actions: [pending],
      },
    }] };
    if (path === "/chat/runs/run-1") return {
      status: "completed", model_calls: 4, tool_calls: 2,
      configured_roles: { supervisor: "Google ADK", card: "CrewAI" }, artifacts: [],
      events: [{ id: "event-1", role: "card", kind: "state_publish", metadata: {} }],
    };
    if (path === "/cards/card-1/block/confirm") return { status: "blocked" };
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<Chat api={mock as Api} />);
  expect(await screen.findByRole("button", { name: "Review action" })).toBeInTheDocument();
  expect(mock.mock.calls.some(([path]) => path.includes("/chat/runs/"))).toBe(false);
  fireEvent.click(screen.getByText("Agent activity and shared context"));
  expect(await screen.findByText(/4 model calls/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review action" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("DEMO-XXXX-0001");
  expect(mock.mock.calls.some(([path]) => path.endsWith("/confirm"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review action" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm action" }));
  expect(await screen.findByText("The simulated action was confirmed.")).toBeInTheDocument();
  expect(mock).toHaveBeenCalledWith("/cards/card-1/block/confirm", { action_id: "pending-1", confirmation: true });
});
