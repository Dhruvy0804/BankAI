import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { type Api, dateTime, useResource } from "./api";
import { ResourceState } from "./components";

type Job = { id: string; status: string; created_at: string; error: string | null; manifest: {
  dataset: string; question: string; conversation_id: string; input_usd_per_million: string | null;
  output_usd_per_million: string | null; price_date: string | null;
} };
type Attempt = { id: string; result: {
  status: string; answer?: { status: string; answer: string; source_ids: string[] };
  configuration: { agent_count: number }; duration_ms: number;
  usage?: { input_tokens: number | null; output_tokens: number | null };
  model_calls?: number; tool_calls?: number; roles_used?: string[]; error_type?: string;
} };
type Detail = Job & { completed_count: number; attempts: Attempt[] };

export default function TextComparison({ api, conversationId, selectedJobId }: {
  api: Api; conversationId?: string; selectedJobId?: string;
}) {
  const jobs = useResource<Job[]>(api, "/evaluation/jobs");
  const available = jobs.data?.filter((job) => job.manifest.dataset === "text" &&
    (!conversationId || job.manifest.conversation_id === conversationId)) || [];
  const [chosen, setChosen] = useState("");
  const id = chosen || selectedJobId || available[0]?.id;
  useEffect(() => { if (selectedJobId) setChosen(selectedJobId); }, [selectedJobId]);
  useEffect(() => {
    if (!selectedJobId) return;
    jobs.reload();
  }, [selectedJobId, jobs.reload]);
  return <section className="text-comparison" aria-label="Text agent comparison">
    <h3>2 vs 3 vs 5 agents · Text comparison</h3>
    <p className="muted">Each answer uses the same question and your signed-in fictional account. These are measured model runs, not phone calls. Answer quality needs your review.</p>
    <ResourceState {...jobs}>
      {available.length > 0 && <label>Previous text comparisons
        <select value={id || ""} onChange={(event) => setChosen(event.target.value)}>
          {available.map((job) => <option key={job.id} value={job.id}>{dateTime(job.created_at)} · {job.manifest.question.slice(0, 80)} · {job.status}</option>)}
        </select>
      </label>}
      {!id && !jobs.loading && <p className="muted">No text comparisons yet. Ask a question in Text assistant and choose Compare 2/3/5.</p>}
    </ResourceState>
    {id && <ComparisonDetail key={id} api={api} id={id} />}
  </section>;
}

function ComparisonDetail({ api, id }: { api: Api; id: string }) {
  const detail = useResource<Detail>(api, `/evaluation/jobs/${id}?limit=3`);
  useEffect(() => {
    if (!["queued", "running", "cancel_requested"].includes(detail.data?.status || "")) return;
    const timer = setInterval(detail.reload, 3000);
    return () => clearInterval(timer);
  }, [detail.data?.status, detail.reload]);
  const job = detail.data;
  return <ResourceState {...detail}>
    {job && <>
      <p><strong>Question:</strong> {job.manifest.question}</p>
      <p role="status" className="muted">{job.status} · {job.completed_count}/3 answers saved</p>
      {job.error && <p className="notice error">{job.error === "PROVIDER_QUOTA_EXCEEDED"
        ? "Gemini request quota was reached. Wait for the provider limit to reset before starting another comparison."
        : `Comparison stopped: ${job.error}`}</p>}
      {job.status === "running" && <p className="muted">The worker pauses between agent counts to reduce free-tier rate-limit failures.</p>}
      <div className="evaluation-compare-grid">
        {[2, 3, 5].map((count) => {
          const result = job.attempts.find((item) => item.result.configuration.agent_count === count)?.result;
          const input = result?.usage?.input_tokens;
          const output = result?.usage?.output_tokens;
          const rates = job.manifest;
          const cost = input != null && output != null && rates.input_usd_per_million != null && rates.output_usd_per_million != null
            ? (input * Number(rates.input_usd_per_million) + output * Number(rates.output_usd_per_million)) / 1_000_000 : null;
          return <article className="evaluation-attempt" key={count}>
            <h4>{count} agents</h4>
            {result ? <>
              <p className="muted">{result.answer?.status || result.status}</p>
              <div className="markdown-answer"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{result.answer?.answer ||
                (result.error_type === "PROVIDER_QUOTA_EXCEEDED" ? "Gemini request quota reached; this answer was not completed." : result.error_type) || "No answer saved"}</ReactMarkdown></div>
              <dl className="evaluation-metrics">
                <div><dt>Input tokens</dt><dd>{input ?? "Unavailable"}</dd></div>
                <div><dt>Output tokens</dt><dd>{output ?? "Unavailable"}</dd></div>
                <div><dt>Total tokens</dt><dd>{input != null && output != null ? input + output : "Unavailable"}</dd></div>
                <div><dt>Time</dt><dd>{result.duration_ms} ms</dd></div>
                <div><dt>Model calls</dt><dd>{result.model_calls ?? "Unavailable"}</dd></div>
                <div><dt>Tool calls</dt><dd>{result.tool_calls ?? "Unavailable"}</dd></div>
                <div><dt>Agents used</dt><dd>{result.roles_used?.join(", ") || "Unavailable"}</dd></div>
                <div><dt>Estimated cost</dt><dd>{cost == null ? "Unavailable" : `USD ${cost.toFixed(6)}`}</dd></div>
              </dl>
              {!!result.answer?.source_ids?.length && <p className="muted">Sources: {result.answer.source_ids.join(", ")}</p>}
            </> : <p className="muted">{["queued", "running"].includes(job.status) ? "Waiting for agent run…" : "No result"}</p>}
          </article>;
        })}
      </div>
      <p className="muted">{job.manifest.price_date
        ? `Cost uses the saved provider price dated ${job.manifest.price_date}. Actual billing may differ.`
        : "Cost estimate unavailable: no dated token-price snapshot was saved. Provider charges may still apply."}</p>
    </>}
  </ResourceState>;
}
