import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Api } from "./api";
import Voice from "./Voice";

const mocks = vi.hoisted(() => ({
  mute: vi.fn(async () => {}), unmute: vi.fn(async () => {}), stop: vi.fn(),
  connect: vi.fn(async () => {}), disconnect: vi.fn(async () => {}), publish: vi.fn(async () => {}),
  create: vi.fn(),
}));
vi.mock("livekit-client", () => ({
  RoomEvent: { TrackSubscribed: "subscribed", TrackUnsubscribed: "unsubscribed", Disconnected: "disconnected" },
  createLocalAudioTrack: mocks.create,
  Room: class {
    localParticipant = { publishTrack: mocks.publish };
    on() { return this; }
    connect = mocks.connect;
    disconnect = mocks.disconnect;
    async startAudio() {}
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.create.mockResolvedValue({ mute: mocks.mute, unmute: mocks.unmute, stop: mocks.stop });
});
afterEach(cleanup);

test("voice publishes a muted microphone, sends one controlled turn, and releases resources", async () => {
  let status = "ready";
  const mock = vi.fn(async (path: string) => {
    if (path === "/voice/sessions") return { session_id: "v1", url: "ws://localhost:7880", token: "room-only-test-token" };
    if (path.endsWith("/listen")) { status = "listening"; return { status }; }
    if (path.endsWith("/send")) { status = "processing"; return { status }; }
    if (path.endsWith("/close")) return { status: "closed" };
    return { status, events: [] };
  });
  const busy = vi.fn();
  const view = render(<Voice api={mock as Api} conversationId="c1" changed={vi.fn()} busyChanged={busy} />);
  fireEvent.click(screen.getByRole("button", { name: "Start browser voice" }));
  expect(await screen.findByRole("button", { name: "Speak question" })).toBeEnabled();
  expect(mocks.connect).toHaveBeenCalledWith("ws://localhost:7880", "room-only-test-token");
  expect(mocks.mute).toHaveBeenCalled();
  expect(busy).toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Speak question" }));
  await waitFor(() => expect(mocks.unmute).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Send voice question" }));
  await waitFor(() => expect(mock.mock.calls.some(([path]) => path.endsWith("/send"))).toBe(true));
  expect(mock.mock.calls.filter(([path]) => path.endsWith("/listen"))).toHaveLength(1);
  expect(screen.getByText(/Confirm banking actions using the review dialog/)).toBeInTheDocument();
  view.unmount();
  await waitFor(() => expect(mocks.stop).toHaveBeenCalledOnce());
  expect(mocks.disconnect).toHaveBeenCalled();
  await waitFor(() => expect(mock.mock.calls.some(([path]) => path.endsWith("/close"))).toBe(true));
});

test("microphone denial closes the room and leaves text assistance usable", async () => {
  mocks.create.mockRejectedValueOnce(new Error("Microphone permission denied"));
  const mock = vi.fn(async (path: string) => path === "/voice/sessions"
    ? { session_id: "v1", url: "ws://localhost:7880", token: "test-token" } : { status: "closed" });
  render(<Voice api={mock as Api} conversationId="c1" changed={vi.fn()} busyChanged={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Start browser voice" }));
  expect(await screen.findByText("Microphone permission denied")).toBeInTheDocument();
  await waitFor(() => expect(mock.mock.calls.some(([path]) => path.endsWith("/close"))).toBe(true));
  expect(mocks.disconnect).toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Start browser voice" })).toBeEnabled();
});

test("leaving during connection closes a late session without opening the microphone", async () => {
  let resolveJoin!: (value: unknown) => void;
  const join = new Promise((resolve) => { resolveJoin = resolve; });
  const mock = vi.fn(async (path: string) => path === "/voice/sessions" ? join : { status: "closed" });
  const view = render(<Voice api={mock as Api} conversationId="c1" changed={vi.fn()} busyChanged={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Start browser voice" }));
  await waitFor(() => expect(mock).toHaveBeenCalledWith("/voice/sessions", { conversation_id: "c1" }));
  view.unmount();
  resolveJoin({ session_id: "late", url: "ws://localhost:7880", token: "test-token" });
  await waitFor(() => expect(mock.mock.calls.some(([path]) => path === "/voice/sessions/late/close")).toBe(true));
  expect(mocks.create).not.toHaveBeenCalled();
  expect(mocks.connect).not.toHaveBeenCalled();
});
