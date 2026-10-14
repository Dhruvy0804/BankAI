import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { type Api, type Pending } from "./api";
import { Confirmation } from "./components";
import { Cards, Loans, Support, Transactions } from "./pages";

const account = {
  id: "a1",
  account_number: "DEMO-ACCT-TEST",
  account_type: "savings",
  currency: "INR",
  balance: "98765.43",
  status: "active",
};
const customer = {
  id: "u1",
  full_name: "Demo Test",
  email: "demo.test@bankai.example",
};
const card = {
  id: "c1",
  account_id: "a1",
  masked_card_number: "DEMO-XXXX-0099",
  card_type: "debit",
  status: "active",
  expiry_month: 12,
  expiry_year: 2030,
};
const pending: Pending = {
  id: "p1",
  resource_id: "c1",
  kind: "block_card",
  expires_at: new Date(Date.now() + 300000).toISOString(),
  payload: {},
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function saved() {
  sessionStorage.setItem(
    "bankai-session",
    JSON.stringify({ token: "fixture-token", expiresAt: Date.now() + 60000 }),
  );
}
function standardFetch() {
  return vi.fn(async (url: string) => {
    if (url.endsWith("/auth/login"))
      return json({ access_token: "fixture-token", expires_in: 1800 });
    if (url.endsWith("/auth/me")) return json(customer);
    if (url.endsWith("/accounts")) return json([account]);
    if (url.includes("/transactions"))
      return json({ items: [], next_cursor: null });
    if (url.endsWith("/kyc/status"))
      return json({ status: "verified", notes: "Demo verification" });
    if (url.endsWith("/cards")) return json([card]);
    if (url.endsWith("/loans") || url.endsWith("/support/tickets"))
      return json([]);
    return json({ error: { message: "Unexpected fixture request" } }, 404);
  });
}

beforeEach(() => {
  sessionStorage.clear();
  window.location.hash = "";
  vi.stubGlobal("fetch", standardFetch());
  // jsdom does not implement native modal dialogs.
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    }),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    }),
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

test("signs in, displays fetched balance, and signs out without keeping customer data", async () => {
  const fetchMock = standardFetch();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: customer.email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "fictional-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("₹98,765.43")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Demo Test",
  );
  const request = fetchMock.mock.calls.find(([url]) =>
    url.endsWith("/accounts"),
  );
  expect(request).toBeDefined();
  expect(sessionStorage.getItem("bankai-session")).toContain("fixture-token");
  fireEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0]);
  expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  expect(screen.queryByText("₹98,765.43")).not.toBeInTheDocument();
  expect(sessionStorage.getItem("bankai-session")).toBeNull();
});

test("restores a session but clears it on a protected 401", async () => {
  saved();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json({ error: { message: "Expired token" } }, 401)),
  );
  render(<App />);
  expect(
    await screen.findByText("Your session ended. Sign in again."),
  ).toBeInTheDocument();
  expect(sessionStorage.getItem("bankai-session")).toBeNull();
});

test("rejects expired or corrupt saved session without fetching banking data", () => {
  sessionStorage.setItem(
    "bankai-session",
    JSON.stringify({ token: "old", expiresAt: Date.now() - 1000 }),
  );
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(screen.getByLabelText("Email address")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("failed login preserves a useful error and does not store a session", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json(
        {
          error: {
            message: "Invalid email or password.",
            request_id: "request-test",
          },
        },
        401,
      ),
    ),
  );
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: customer.email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "wrong-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Invalid email or password.",
  );
  expect(sessionStorage.getItem("bankai-session")).toBeNull();
});

test("shows a resource error and retries without displaying invented balances", async () => {
  saved();
  const fetchMock = standardFetch();
  fetchMock.mockImplementationOnce(async () =>
    json({ error: { message: "Database unavailable" } }, 503),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Database unavailable",
  );
  expect(screen.queryByText("₹98,765.43")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("₹98,765.43")).toBeInTheDocument();
});

test("an old customer request cannot repopulate the page after sign out", async () => {
  saved();
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );
  render(<App />);
  fireEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0]);
  await act(async () => resolve(json(customer)));
  expect(
    screen.queryByRole("heading", { name: /Demo Test/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Email address")).toBeInTheDocument();
});

test("card cancel never confirms; explicit confirmation sends the bound action once", async () => {
  let blocked = false;
  const api = vi.fn(async (path: string) => {
    if (path === "/cards")
      return [{ ...card, status: blocked ? "blocked" : "active" }];
    if (path.endsWith("/confirm")) {
      blocked = true;
      return { ...card, status: "blocked" };
    }
    return pending;
  }) as unknown as Api;
  render(<Cards api={api} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Block demo card" }),
  );
  expect(await screen.findByRole("dialog")).toHaveTextContent("DEMO-XXXX-0099");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(
    vi.mocked(api).mock.calls.filter(([path]) => path.endsWith("/confirm")),
  ).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Block demo card" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Confirm action" }),
  );
  expect(
    await screen.findByText("DEMO-XXXX-0099 was blocked in BankSim."),
  ).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/cards/c1/block/confirm", {
    action_id: "p1",
    confirmation: true,
  });
});

test("double confirmation clicks cannot submit duplicate writes", async () => {
  let resolve!: () => void;
  const confirm = vi.fn(
    () =>
      new Promise<void>((done) => {
        resolve = done;
      }),
  );
  render(
    <Confirmation
      pending={pending}
      title="Confirm test"
      confirm={confirm}
      close={() => {}}
    >
      <p>Demo action</p>
    </Confirmation>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm action" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirming…" }));
  expect(confirm).toHaveBeenCalledTimes(1);
  await act(async () => resolve());
});

test("expired confirmation is disabled and reports the expiry", () => {
  render(
    <Confirmation
      pending={{
        ...pending,
        expires_at: new Date(Date.now() - 1).toISOString(),
      }}
      title="Expired request"
      confirm={vi.fn()}
      close={() => {}}
    >
      <p>Demo action</p>
    </Confirmation>,
  );
  expect(screen.getByRole("button", { name: "Confirm action" })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("expired");
});

test("transaction paging and filters are passed to the API, and empty results are clear", async () => {
  const api = vi.fn(async (path: string) =>
    path === "/accounts"
      ? [account]
      : { items: [], next_cursor: path.includes("cursor=0") ? 10 : null },
  ) as unknown as Api;
  render(<Transactions api={api} />);
  expect(
    await screen.findByText("No transactions match this view."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/transactions?limit=10&cursor=10",
      undefined,
      expect.any(AbortSignal),
    ),
  );
  fireEvent.change(screen.getByLabelText("Type"), {
    target: { value: "debit" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/transactions?limit=10&cursor=0&transaction_type=debit",
      undefined,
      expect.any(AbortSignal),
    ),
  );
});

test("loan submission is staged before confirmation and uses server-returned inputs", async () => {
  const payload = {
    loan_type: "personal",
    requested_amount: "15000",
    annual_interest_rate: "10",
    tenure_months: 12,
    monthly_income: "50000",
    monthly_obligations: "0",
  };
  const api = vi.fn(async (path: string) =>
    path === "/loans"
      ? []
      : path.endsWith("/confirm")
        ? { status: "submitted" }
        : { ...pending, kind: "loan_application", resource_id: null, payload },
  ) as unknown as Api;
  render(<Loans api={api} />);
  fireEvent.change(screen.getByLabelText("Loan amount (INR)"), {
    target: { value: "15000" },
  });
  fireEvent.change(screen.getByLabelText("Annual interest (%)"), {
    target: { value: "10" },
  });
  fireEvent.change(screen.getByLabelText("Tenure (months)"), {
    target: { value: "12" },
  });
  fireEvent.change(screen.getByLabelText("Demo monthly income (INR)"), {
    target: { value: "50000" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Request application" }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("₹15,000.00");
  expect(
    vi.mocked(api).mock.calls.filter(([path]) => path.endsWith("/confirm")),
  ).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Confirm action" }));
  expect(
    await screen.findByText(/Your simulated loan application was submitted/),
  ).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith("/loans/applications/p1/confirm", {
    confirmation: true,
  });
});

test("support form preserves input on failure and resets only after verified success", async () => {
  let fail = true;
  const api = vi.fn(async (path: string, body?: unknown) => {
    if (!body) return [];
    if (fail) throw new Error("Ticket service unavailable");
    return { id: "t1" };
  }) as unknown as Api;
  render(<Support api={api} />);
  fireEvent.change(screen.getByLabelText("Subject"), {
    target: { value: "Demo issue" },
  });
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Fictional support request" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create demo ticket" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Ticket service unavailable",
  );
  expect(screen.getByLabelText("Subject")).toHaveValue("Demo issue");
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Create demo ticket" }));
  expect(
    await screen.findByText("Your demo support ticket was created."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Subject")).toHaveValue("");
});
