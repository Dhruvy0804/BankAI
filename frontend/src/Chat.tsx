import { useRef, useState, type FormEvent } from "react";
import { type Api, type Pending, dateTime, money, label, useAction, useResource } from "./api";
import { Confirmation, ErrorNotice, ResourceState } from "./components";

type Status = { configured: boolean; provider: string; model: string; mode?: "guidance" | "agents" };
type Conversation = { id: string; title: string; created_at: string };
type Reply = {
  status: "guidance" | "needs_tools" | "refused" | "answered" | "clarification" | "confirmation_required";
  answer: string;
  request_id: string;
  run_id: string;
  provider: string;
  model: string;
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  pending_actions?: Pending[];
  prompt_version?: string;
};
type Detail = Conversation & {
  turns: { message_id: string; user_text: string; response: Reply; created_at: string }[];
};

export default function Chat({ api }: { api: Api }) {
  const status = useResource<Status>(api, "/chat/status");
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const conversations = useResource<Conversation[]>(api, `/chat/conversations?offset=${offset}`);
  const create = useAction();
  const active = selected || conversations.data?.[0]?.id;
  return (
    <section className="panel chat-panel">
      <h2>Text assistant</h2>
      <p className="muted">
        {status.data?.mode === "agents"
          ? "Ask about your fictional accounts, cards, or demo loan calculations. Sensitive requests require a separate confirmation. Verified policy answers are coming later. "
          : "Ask for general banking explanations. This chat cannot look up accounts, verify policies, or perform banking actions yet. Use the banking pages for those tasks. "}
        Do not enter passwords, PINs, OTPs, or real banking information.
      </p>
      <ResourceState {...status}>
        {status.data && (
          <p className="notice" role="status">
            {status.data.configured
              ? `Provider configured: ${status.data.provider} · ${status.data.model}. Responses are AI-generated guidance.`
              : "Text assistance is unavailable until the backend model provider is configured. Saved conversations remain accessible."}
          </p>
        )}
      </ResourceState>
      {status.data?.mode === "agents" && <p className="muted">Five-agent assistant · Facts are retrieved from BankSim. Preparing a request does not execute it.</p>}
      <div className="form-actions">
        <button className="primary" disabled={busy || create.busy} onClick={() => void create.run(async () => {
          const conversation = await api<Conversation>("/chat/conversations", {});
          setSelected(conversation.id);
          setOffset(0);
          conversations.reload();
        })}>New conversation</button>
      </div>
      <ErrorNotice error={create.error} />
      <ResourceState {...conversations}>
        <label>
          Saved conversations
          <select aria-label="Saved conversations" disabled={busy || create.busy || conversations.loading}
            value={active || ""} onChange={(event) => setSelected(event.target.value)}>
            {active && !conversations.data?.some((item) => item.id === active) && (
              <option value={active}>Current conversation</option>
            )}
            {!active && <option value="">Start a new conversation</option>}
            {conversations.data?.map((item) => <option key={item.id} value={item.id}>{item.title} · {dateTime(item.created_at)}</option>)}
          </select>
        </label>
        <div className="form-actions">
          <button className="secondary" disabled={busy || conversations.loading || offset === 0} onClick={() => { setSelected(""); setOffset(Math.max(0, offset - 50)); }}>Newer conversations</button>
          <button className="secondary" disabled={busy || conversations.loading || (conversations.data?.length || 0) < 50} onClick={() => { setSelected(""); setOffset(offset + 50); }}>Older conversations</button>
        </div>
      </ResourceState>
      {active ? <ConversationChat key={active} api={api} id={active}
        configured={status.data?.configured === true} setBusy={setBusy}
        changed={conversations.reload} />
        : <p className="empty-state">Start a conversation to ask a question.</p>}
    </section>
  );
}

function ConversationChat({ api, id, configured, setBusy, changed }: {
  api: Api; id: string; configured: boolean; setBusy: (value: boolean) => void; changed: () => void;
}) {
  const detail = useResource<Detail>(api, `/chat/conversations/${id}`);
  const [message, setMessage] = useState("");
  const pending = useRef<{ text: string; id: string } | undefined>(undefined);
  const action = useAction();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || !configured || action.busy) return;
    await action.run(async () => {
      setBusy(true);
      try {
        const text = message.trim();
        if (pending.current?.text !== text) pending.current = { text, id: crypto.randomUUID() };
        await api<Reply>("/chat", { conversation_id: id, message_id: pending.current.id, message: text });
        pending.current = undefined;
        setMessage("");
        detail.reload();
        changed();
      } finally {
        setBusy(false);
      }
    });
  }
  return (
    <>
      <ResourceState {...detail}>
        <div className="chat-transcript" role="log" aria-label="Conversation messages" aria-live="polite">
          {!detail.data?.turns.length && <p>No messages yet.</p>}
          {detail.data?.turns.map((turn) => <article key={turn.message_id} className="chat-turn">
            <h3>You</h3><p className="chat-text">{turn.user_text}</p>
            <h3>BankAI · {turn.response.status.replaceAll("_", " ")}</h3>
            <p className="chat-text">{turn.response.answer}</p>
            <details><summary>Response details</summary>
              <p className="muted">{turn.response.model} · {turn.response.duration_ms} ms · {turn.response.total_tokens ?? "Unavailable"} total tokens</p>
              <p className="muted">Request: {turn.response.request_id}</p>
              <pre className="chat-json">{JSON.stringify(turn.response, null, 2)}</pre>
            </details>
            {turn.response.prompt_version === "phase6-blackboard-v1" && <RunActivity api={api} runId={turn.response.run_id} />}
            {turn.response.pending_actions?.map((pending) => <PendingChatAction key={pending.id} api={api} pending={pending} />)}
          </article>)}
        </div>
      </ResourceState>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="chat-message">Your question</label>
        <textarea id="chat-message" value={message} maxLength={2000} rows={3}
          disabled={action.busy} onChange={(event) => setMessage(event.target.value)} />
        <ErrorNotice error={action.error} />
        <p className="muted">Only the latest 10 exchanges are sent as context. After a connection error, refresh history before changing and resending your question.</p>
        <div className="form-actions">
          <button className="primary" disabled={!configured || !message.trim() || action.busy || detail.loading || !!detail.error || (detail.data?.turns.length || 0) >= 100}>
            {action.busy ? "Generating…" : "Send message"}
          </button>
          <button type="button" className="secondary" disabled={action.busy} onClick={detail.reload}>Refresh history</button>
        </div>
        {action.busy && <p role="status">Waiting for the assistant…</p>}
        {(detail.data?.turns.length || 0) >= 100 && <p role="status">This conversation is full. Start a new conversation.</p>}
      </form>
    </>
  );
}

function RunActivity({ api, runId }: { api: Api; runId: string }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Agent activity and shared context</summary>
    {open && <RunTrace api={api} runId={runId} />}
  </details>;
}

function RunTrace({ api, runId }: { api: Api; runId: string }) {
  const trace = useResource<{
    status: string; model_calls: number; tool_calls: number;
    configured_roles: Record<string, string>;
    events: { id: string; at: string; role: string; kind: string; metadata: unknown }[];
    artifacts: unknown[];
  }>(api, `/chat/runs/${runId}`);
  return <ResourceState {...trace}>
    {trace.data && <>
      <p>{trace.data.status} · {trace.data.model_calls} model calls · {trace.data.tool_calls} tool calls</p>
      <p className="muted">{Object.entries(trace.data.configured_roles).map(([role, framework]) => `${role}: ${framework}`).join(" · ")}</p>
      <ol className="agent-timeline" tabIndex={0} aria-label="Agent execution timeline">{trace.data.events.map((event) => <li key={event.id}>
        <strong>{event.role}</strong> · {event.kind.replaceAll("_", " ")}
        <details><summary>Event details</summary><pre className="chat-json">{JSON.stringify(event.metadata, null, 2)}</pre></details>
      </li>)}</ol>
      <details><summary>Blackboard artifacts</summary><pre className="chat-json">{JSON.stringify(trace.data.artifacts, null, 2)}</pre></details>
    </>}
  </ResourceState>;
}

function PendingChatAction({ api, pending }: { api: Api; pending: Pending }) {
  const [open, setOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  return <div className="notice">
    <p>{confirmed ? "The simulated action was confirmed." : `Pending ${pending.kind.replaceAll("_", " ")} · expires ${dateTime(pending.expires_at)}`}</p>
    {!confirmed && <button type="button" className="secondary" onClick={() => setOpen(true)}>Review action</button>}
    {open && <Confirmation pending={pending} title="Review this simulated banking action"
      close={() => setOpen(false)} confirm={async () => {
        if (pending.kind === "block_card" && pending.resource_id) {
          await api(`/cards/${pending.resource_id}/block/confirm`, { action_id: pending.id, confirmation: true });
        } else if (pending.kind === "loan_application") {
          await api(`/loans/applications/${pending.id}/confirm`, { confirmation: true });
        } else {
          throw new Error("Unsupported pending action. Use the banking pages to review it.");
        }
        setConfirmed(true);
        setOpen(false);
      }}>
      <p>This changes fictional BankSim records only. Confirm the exact details below.</p>
      {pending.kind === "block_card" ? <p>Block card <strong>{String(pending.payload.masked_card_number || pending.resource_id)}</strong>.</p> : <>
        <p>{label(String(pending.payload.loan_type))} loan · <strong>{money(String(pending.payload.requested_amount))}</strong></p>
        <p>{String(pending.payload.tenure_months)} months at {String(pending.payload.annual_interest_rate)}% annual interest.</p>
        <p>Demo monthly income: {money(String(pending.payload.monthly_income))}; obligations: {money(String(pending.payload.monthly_obligations))}.</p>
        <p>This submits a simulated application, not a credit approval.</p>
      </>}
    </Confirmation>}
  </div>;
}
