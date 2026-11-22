import { useEffect, useRef, useState } from "react";
import { type Api, useAction, useResource } from "./api";
import { ErrorNotice, ResourceState } from "./components";

type Call = { id: string; demo_customer: string; destination_hint: string; status: string; expires_at: string; events?: { kind: string; run_id: string | null; metadata: unknown }[]; turns?: { question: string; answer: string; status: string; run_id: string }[] };
type Config = { allowed_numbers: string[]; max_duration_seconds: number; max_daily_attempts: number; provider: "twilio" | "plivo" };
const ended = new Set(["completed", "canceled", "busy", "failed", "no-answer", "ended", "error", "expired"]);

export default function Phone({ api, busyChanged, disabled = false }: {
  api: Api; busyChanged: (value: boolean) => void; disabled?: boolean;
}) {
  const config = useResource<Config>(api, "/phone/config");
  const history = useResource<Call[]>(api, "/phone/calls");
  const action = useAction();
  const [agreed, setAgreed] = useState(false);
  const [number, setNumber] = useState("");
  const [demoCustomer, setDemoCustomer] = useState("owner");
  const [activeId, setActiveId] = useState("");
  const [call, setCall] = useState<Call>();
  const callbacks = useRef({ busyChanged });
  callbacks.current = { busyChanged };

  useEffect(() => {
    callbacks.current.busyChanged(!!activeId);
    return () => callbacks.current.busyChanged(false);
  }, [activeId]);

  useEffect(() => {
    if (!number && config.data?.allowed_numbers.length) setNumber(config.data.allowed_numbers[0]);
  }, [config.data, number]);
  useEffect(() => {
    if (!activeId) {
      const previous = history.data?.find((item) => !ended.has(item.status));
      if (previous) setActiveId(previous.id);
    }
  }, [history.data, activeId]);
  useEffect(() => {
    if (!activeId) return;
    let mounted = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await api<Call>(`/phone/calls/${activeId}`);
        if (!mounted) return;
        setCall(result);
        if (ended.has(result.status)) { setActiveId(""); history.reload(); return; }
      } catch { if (mounted) setActiveId(""); return; }
      timer = setTimeout(poll, 2500);
    }
    void poll();
    return () => { mounted = false; clearTimeout(timer); };
  }, [activeId, api]);

  return <section className="notice" aria-label="Phone test">
    <h3>Phone test with {config.data?.provider === "plivo" ? "Plivo" : "Twilio"}</h3>
    <p>Call an approved test recipient using a selected fictional customer. The recipient must press 1 to agree before asking questions. {config.data?.provider === "plivo" ? "Plivo" : "Twilio"} handles speech recognition and playback; questions and answers appear in the phone conversation below. No call audio is recorded. Confirm simulated banking actions in the web app.</p>
    <ResourceState {...config}>
      {config.data && <>
        <label>Approved number
          <select value={number} disabled={!!activeId || action.busy} onChange={(event) => setNumber(event.target.value)}>
            {config.data.allowed_numbers.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>Fictional customer
          <select value={demoCustomer} disabled={!!activeId || action.busy} onChange={(event) => setDemoCustomer(event.target.value)}>
            <option value="owner">My fictional demo account</option>
            <option value="asha">Asha · verified KYC</option>
            <option value="ravi">Ravi · pending KYC</option>
            <option value="mira">Mira · rejected KYC</option>
          </select>
        </label>
        <label className="phone-consent"><input type="checkbox" checked={agreed} disabled={!!activeId || action.busy} onChange={(event) => setAgreed(event.target.checked)} /> The recipient agreed to receive this test call.</label>
        <p role="status">{activeId ? `Call: ${call?.status || "connecting"} · ${call?.destination_hint || "approved number"}` : `Calls end after ${config.data.max_duration_seconds / 60} minutes. Maximum ${config.data.max_daily_attempts} call attempts per UTC day.`}</p>
        <div className="form-actions">
          {!activeId ? <button type="button" className="secondary" disabled={!agreed || !number || disabled || action.busy} onClick={() => void action.run(async () => {
            const result = await api<Call>("/phone/calls", { demo_customer: demoCustomer, number, recipient_agreed: true });
            setActiveId(result.id); setCall(result); history.reload();
          })}>Call approved number</button> : <button type="button" className="secondary" disabled={action.busy} onClick={() => void action.run(async () => {
            await api(`/phone/calls/${activeId}/end`, {}); setActiveId(""); history.reload();
          })}>End call</button>}
        </div>
      </>}
    </ResourceState>
    <ErrorNotice error={action.error} />
    {!!history.data?.length && <details><summary>Past phone tests</summary><ul>{history.data.map((item) => <li key={item.id}>
      {item.demo_customer} · {item.destination_hint} · {item.status}{" "}
      <button type="button" className="secondary" disabled={action.busy} onClick={() => void action.run(async () => setCall(await api<Call>(`/phone/calls/${item.id}`)))}>View conversation</button>
    </li>)}</ul></details>}
    {!!call?.turns?.length && <div role="log" aria-label="Phone conversation">{call.turns.map((turn) => <article key={turn.run_id}><strong>Question:</strong> {turn.question}<p><strong>BankAI:</strong> {turn.answer}</p></article>)}</div>}
    {!!call?.events?.length && <details><summary>Call activity</summary><pre className="chat-json">{JSON.stringify(call.events, null, 2)}</pre></details>}
  </section>;
}
