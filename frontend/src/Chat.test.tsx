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
