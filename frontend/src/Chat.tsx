import { useRef, useState, type FormEvent } from "react";
import { type Api, dateTime, useAction, useResource } from "./api";
import { ErrorNotice, ResourceState } from "./components";

type Status = { configured: boolean; provider: string; model: string };
type Conversation = { id: string; title: string; created_at: string };
type Reply = {
  status: "guidance" | "needs_tools" | "refused";
  answer: string;
  request_id: string;
  run_id: string;
  provider: string;
  model: string;
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
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
        Ask for general banking explanations. This chat cannot look up accounts,
        verify policies, or perform banking actions yet. Use the banking pages for those tasks.
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
