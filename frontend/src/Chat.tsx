import { lazy, Suspense, useRef, useState, type FormEvent } from "react";
import { CheckCheck, Send, Sparkles, UserRound } from "lucide-react";
import { type Api, type Pending, dateTime, money, label, useAction, useResource } from "./api";
import { Confirmation, ErrorNotice, ResourceState } from "./components";
import DemoData from "./DemoData";
import Voice from "./Voice";
import Phone from "./Phone";
import TextComparison from "./TextComparison";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const AgentWorkflow = lazy(() => import("./AgentWorkflow"));

type Status = { configured: boolean; provider: string; model: string; mode?: "guidance" | "agents"; voice_configured?: boolean; phone_configured?: boolean };
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
  sources?: { citation_id: string; title: string; source: string; section: string; excerpt: string; checksum: string }[];
};
type Detail = Conversation & {
  turns: { message_id: string; user_text: string; response: Reply; created_at: string }[];
};

export default function Chat({ api, comparisonEnabled = false }: { api: Api; comparisonEnabled?: boolean }) {
  const status = useResource<Status>(api, "/chat/status");
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const conversations = useResource<Conversation[]>(api, `/chat/conversations?offset=${offset}`);
  const create = useAction();
  const active = selected || conversations.data?.[0]?.id;
  return (
    <section className="panel chat-panel">
      <h2>Text assistant</h2>
      <p className="muted">
        {status.data?.mode === "agents"
          ? "Ask about your fictional accounts, cards, loan calculations, or published demo policies. Policy answers include sources. Sensitive requests require a separate confirmation. "
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
      {status.data?.phone_configured && <Phone api={api} disabled={busy} busyChanged={setPhoneBusy} />}
      <DemoData api={api} />
      <div className="form-actions">
        <button className="primary" disabled={busy || phoneBusy || create.busy} onClick={() => void create.run(async () => {
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
          <select aria-label="Saved conversations" disabled={busy || phoneBusy || create.busy || conversations.loading}
            value={active || ""} onChange={(event) => setSelected(event.target.value)}>
            {active && !conversations.data?.some((item) => item.id === active) && (
              <option value={active}>Current conversation</option>
            )}
            {!active && <option value="">Start a new conversation</option>}
            {conversations.data?.map((item) => <option key={item.id} value={item.id}>{item.title} · {dateTime(item.created_at)}</option>)}
          </select>
        </label>
        <div className="form-actions">
          <button className="secondary" disabled={busy || phoneBusy || conversations.loading || offset === 0} onClick={() => { setSelected(""); setOffset(Math.max(0, offset - 50)); }}>Newer conversations</button>
          <button className="secondary" disabled={busy || phoneBusy || conversations.loading || (conversations.data?.length || 0) < 50} onClick={() => { setSelected(""); setOffset(offset + 50); }}>Older conversations</button>
        </div>
      </ResourceState>
      {active ? <ConversationChat key={active} api={api} id={active}
        configured={status.data?.configured === true} setBusy={setBusy}
        changed={() => { setSelected(active); conversations.reload(); }} voiceEnabled={status.data?.voice_configured === true} phoneBusy={phoneBusy} comparisonEnabled={comparisonEnabled} />
        : <p className="empty-state">Start a conversation to ask a question.</p>}
    </section>
  );
}

function ConversationChat({ api, id, configured, setBusy, changed, voiceEnabled, phoneBusy, comparisonEnabled }: {
  api: Api; id: string; configured: boolean; setBusy: (value: boolean) => void; changed: () => void; voiceEnabled: boolean; phoneBusy: boolean; comparisonEnabled: boolean;
}) {
  const detail = useResource<Detail>(api, `/chat/conversations/${id}`);
  const [message, setMessage] = useState("");
  const pending = useRef<{ text: string; id: string } | undefined>(undefined);
  const action = useAction();
  const comparison = useAction();
  const [costAcknowledged, setCostAcknowledged] = useState(false);
  const [comparisonJobId, setComparisonJobId] = useState("");
  const [voiceBusy, setVoiceBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim() || !configured || action.busy || voiceBusy || phoneBusy) return;
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
  async function compare() {
    if (!message.trim() || !costAcknowledged || comparison.busy || action.busy) return;
    await comparison.run(async () => {
      const job = await api<{ id: string }>("/evaluation/text-comparisons", {
        conversation_id: id, question: message.trim(), acknowledge_provider_cost: true,
      });
      setComparisonJobId(job.id);
      setCostAcknowledged(false);
      setMessage("");
    });
  }
  return (
    <>
      {voiceEnabled && <Voice api={api} conversationId={id} disabled={action.busy || phoneBusy}
        changed={() => { detail.reload(); changed(); }} busyChanged={(value) => { setVoiceBusy(value); setBusy(value); }} />}
      <Suspense fallback={<p role="status" className="muted">Loading agent canvas…</p>}>
        <AgentWorkflow api={api} runId={detail.data?.turns.at(-1)?.response.run_id}
          sources={detail.data?.turns.at(-1)?.response.sources} processing={action.busy || voiceBusy} />
      </Suspense>
      <ResourceState {...detail}>
        <div className="chat-transcript" role="log" aria-label="Conversation messages" aria-live="polite">
          {!detail.data?.turns.length && <p>No messages yet.</p>}
          {detail.data?.turns.map((turn) => <article key={turn.message_id} className="chat-turn">
            <div className="chat-message chat-message-user"><div className="chat-message-heading"><UserRound size={17} /><h3>You</h3><time>{dateTime(turn.created_at)}</time></div><p className="chat-text">{turn.user_text}</p></div>
            <div className="chat-message chat-message-assistant"><div className="chat-message-heading"><Sparkles size={17} /><h3>BankAI</h3><span className={`response-status response-${turn.response.status}`}><CheckCheck size={14} />{turn.response.status.replaceAll("_", " ")}</span></div>
            <div className="chat-text markdown-answer"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{turn.response.answer}</ReactMarkdown></div>
            {!!turn.response.sources?.length && <section aria-label="Policy sources">
              <h4>Fictional policy sources</h4>
              {turn.response.sources.map((source) => <details key={source.citation_id}>
                <summary>{source.title} · {source.section}</summary>
                <p className="chat-text">{source.excerpt}</p>
                <p className="muted">[{source.citation_id}] · {source.source} · Version {source.checksum.slice(0, 12)}</p>
              </details>)}
            </section>}
            <details><summary>Response details</summary>
              <p className="muted">{turn.response.model} · {turn.response.duration_ms} ms · {turn.response.total_tokens ?? "Unavailable"} model tokens</p>
              <p className="muted">Request: {turn.response.request_id}</p>
              <p className="muted">Status: {label(turn.response.status)} · Provider: {turn.response.provider} · Run: {turn.response.run_id || "Unavailable"}</p>
            </details>
            {turn.response.run_id && <RunActivity api={api} runId={turn.response.run_id} />}
            {turn.response.pending_actions?.map((pending) => <PendingChatAction key={pending.id} api={api} pending={pending} />)}</div>
          </article>)}
        </div>
      </ResourceState>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="chat-message">Your question</label>
        <textarea id="chat-message" value={message} maxLength={2000} rows={3}
          disabled={action.busy || voiceBusy || phoneBusy} onChange={(event) => setMessage(event.target.value)} />
        <button type="button" className="secondary" disabled={action.busy || voiceBusy || phoneBusy}
          onClick={() => setMessage("Check my demo savings account balance, show my card statuses, calculate the monthly EMI for INR 12000 at 12% annual interest over 12 months, and check my existing support ticket. Summarize each verified result. Do not create or change anything.")}>Fill five-agent demo question</button>
        <ErrorNotice error={action.error} />
        <p className="muted">Only the latest 10 exchanges are sent as context. After a connection error, refresh history before changing and resending your question.</p>
        <div className="form-actions">
          <button className="primary" disabled={!configured || !message.trim() || action.busy || voiceBusy || phoneBusy || detail.loading || !!detail.error || (detail.data?.turns.length || 0) >= 100}>
            <Send size={15} aria-hidden="true" /> {action.busy ? "Generating…" : "Send message"}
          </button>
          <button type="button" className="secondary" disabled={action.busy} onClick={detail.reload}>Refresh history</button>
        </div>
        {comparisonEnabled && <div className="text-comparison-action">
          <label className="evaluation-check"><input type="checkbox" checked={costAcknowledged} onChange={(event) => setCostAcknowledged(event.target.checked)} />I understand this comparison runs three model evaluations and may use paid credits.</label>
          <button type="button" className="secondary" disabled={!configured || !message.trim() || !costAcknowledged || action.busy || comparison.busy || voiceBusy || phoneBusy}
            onClick={() => void compare()}>{comparison.busy ? "Starting comparison…" : "Compare 2/3/5 agents"}</button>
          <p className="muted">Uses this typed question and your signed-in demo account. The three answers and metrics appear below.</p>
          <ErrorNotice error={comparison.error} />
        </div>}
        {action.busy && <p role="status">Waiting for the assistant…</p>}
        {(detail.data?.turns.length || 0) >= 100 && <p role="status">This conversation is full. Start a new conversation.</p>}
      </form>
      {comparisonEnabled && <TextComparison api={api} conversationId={id} selectedJobId={comparisonJobId} />}
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
    configuration: { agent_count: number; architecture: string; prompt_strategy: string };
    configured_roles: Record<string, string>;
    events: { id: string; at: string; role: string; kind: string; metadata: unknown }[];
    artifacts: { id: string; role: string; revision: number; consumed: string[];
      summary: { status: string; answer: string }; facts: { tool: string }[] }[];
  }>(api, `/chat/runs/${runId}`);
  return <ResourceState {...trace}>
    {trace.data && <>
      <h4>{trace.data.configuration.agent_count}-agent workflow</h4>
      <p className="muted">{label(trace.data.configuration.architecture)} context · {label(trace.data.configuration.prompt_strategy)} prompts · {trace.data.status} · {trace.data.model_calls} model calls · {trace.data.tool_calls} tool calls</p>
      <p className="muted">Agents are called when their role is relevant. A configured agent may not be needed for every question.</p>
      <div className="agent-contributions" aria-label="Agent contributions">
        {Object.entries(trace.data.configured_roles).map(([role, framework]) => {
          const artifact = trace.data!.artifacts.find((item) => item.role === role);
          const started = trace.data!.events.some((event) => event.role === role && event.kind === "agent_start");
          const consumed = artifact?.consumed.map((id) => trace.data!.artifacts.find((item) => item.id === id)?.role || "prior agent") || [];
          return <section className="agent-contribution" key={role} aria-label={`${label(role)} agent`}>
            <h5>{label(role)} <small>· {framework}</small></h5>
            <p className="muted">{role === "supervisor"
              ? trace.data!.events.some((event) => event.kind === "guardrail_rejected") ? "Rejected unsafe request"
                : trace.data!.events.some((event) => event.kind === "output_validated") ? "Coordinated and validated the response"
                  : "Coordinated the request"
              : artifact ? `Contributed · ${artifact.summary.status}` : started ? "Started; no verified result" : "Not called for this question"}</p>
            {artifact && <>
              <p className="chat-text">{artifact.summary.answer}</p>
              {!!artifact.facts.length && <p className="muted">Tools: {[...new Set(artifact.facts.map((fact) => label(fact.tool)))].join(", ")}</p>}
              {!!consumed.length && <p className="muted">Used shared context from: {consumed.map(label).join(", ")}</p>}
            </>}
          </section>;
        })}
      </div>
      <ol className="agent-timeline" tabIndex={0} aria-label="Agent execution timeline">{trace.data.events.map((event) => <li key={event.id}>
        <strong>{event.role}</strong> · {event.kind.replaceAll("_", " ")}
      </li>)}</ol>
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
