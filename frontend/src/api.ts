import { useCallback, useEffect, useRef, useState } from "react";

export type Customer = { id: string; full_name: string; email: string };
export type Account = {
  id: string;
  account_number: string;
  account_type: string;
  currency: string;
  balance: string;
  status: string;
};
export type Transaction = {
  id: string;
  account_id: string;
  transaction_type: string;
  amount: string;
  description: string;
  merchant: string | null;
  reference_code: string;
  status: string;
  occurred_at: string;
};
export type TransactionPage = {
  items: Transaction[];
  next_cursor: number | null;
};
export type Card = {
  id: string;
  account_id: string | null;
  masked_card_number: string;
  card_type: string;
  status: string;
  expiry_month: number;
  expiry_year: number;
};
export type Loan = {
  id: string;
  loan_type: string;
  requested_amount: string;
  annual_interest_rate: string;
  tenure_months: number;
  status: string;
  created_at: string;
};
export type Ticket = {
  id: string;
  category: string;
  subject: string;
  description: string;
  priority: string;
  status: string;
  created_at: string;
};
export type Pending = {
  id: string;
  kind: string;
  resource_id: string | null;
  payload: Record<string, string | number>;
  expires_at: string;
};
export type EMI = {
  monthly_payment: string;
  total_payment: string;
  total_interest: string;
};
export type Eligibility = {
  eligible: boolean;
  reasons: string[];
  monthly_payment: string;
  rule: string;
};
export type KYC = {
  status: string;
  notes: string | null;
  last_updated: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
    public requestId?: string,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  token?: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) abort();
  const timeout = setTimeout(abort, path === "/chat" ? 190000 : 10000);
  try {
    const response = await fetch(`/api/v1${path}`, {
      method: body === undefined ? "GET" : "POST",
      signal: controller.signal,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json();
    if (!response.ok)
      throw new ApiError(
        data.error?.message || "The request could not be completed.",
        response.status,
        data.error?.request_id,
      );
    return data as T;
  } catch (error) {
    if (error instanceof ApiError || signal?.aborted) throw error;
    throw new ApiError(
      "Connection interrupted or timed out. Check your connection and refresh to verify the latest state before repeating an action.",
    );
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export type Api = <T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
) => Promise<T>;

export function useResource<T>(api: Api, path: string) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{
    path: string;
    data?: T;
    error?: Error;
    loading: boolean;
  }>({ path, loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ path, loading: true });
    api<T>(path, undefined, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted)
          setState({ path, data, loading: false });
      },
      (error) => {
        if (!controller.signal.aborted)
          setState({ path, error, loading: false });
      },
    );
    return () => controller.abort();
  }, [api, path, version]);
  const reload = useCallback(() => setVersion((value) => value + 1), []);
  const current: typeof state =
    state.path === path ? state : { path, loading: true };
  return { ...current, reload };
}

export function useAction() {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (failure) {
      setError(
        failure instanceof Error ? failure : new Error("Request failed."),
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run };
}

export const money = (value: string | number, currency = "INR") =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(
    Number(value),
  );
export const dateTime = (value: string) =>
  new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
export const label = (value: string) => value.replaceAll("_", " ");
