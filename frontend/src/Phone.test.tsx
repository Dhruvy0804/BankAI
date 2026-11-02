import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Api } from "./api";
import Phone from "./Phone";

afterEach(cleanup);

test("phone panel dials only after owner confirms recipient agreement and can end the call", async () => {
  let started = false;
  const request = vi.fn(async (path: string, body?: unknown) => {
    if (path === "/phone/config") return { allowed_numbers: ["+919876543210"], max_duration_seconds: 300 };
    if (path === "/phone/calls" && body) { started = true; return { id: "call-1", demo_customer: "asha", destination_hint: "…3210", status: "dialing" }; }
    if (path === "/phone/calls") return started ? [{ id: "call-1", demo_customer: "asha", destination_hint: "…3210", status: "dialing" }] : [];
    if (path === "/phone/calls/call-1") return { id: "call-1", demo_customer: "asha", destination_hint: "…3210", status: "dialing", events: [] };
    return { status: "ended" };
  });
  render(<Phone api={request as Api} busyChanged={vi.fn()} />);
  const dial = await screen.findByRole("button", { name: "Call approved number" });
  expect(dial).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /recipient agreed/ }));
  expect(dial).toBeEnabled();
  fireEvent.click(dial);
  await waitFor(() => expect(request).toHaveBeenCalledWith("/phone/calls", {
    demo_customer: "asha", number: "+919876543210", recipient_agreed: true,
  }));
  const end = await screen.findByRole("button", { name: "End call" });
  fireEvent.click(end);
  await waitFor(() => expect(request).toHaveBeenCalledWith("/phone/calls/call-1/end", {}));
});
