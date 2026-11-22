import { useEffect, useState } from "react";
import { type Api, dateTime, useAction, useResource } from "./api";
import { ErrorNotice, ResourceState } from "./components";
import TextComparison from "./TextComparison";

type Case = { id: string; category: string; question: string; expected_statuses: string[]; expected_tools: string[] };
type Config = { live_enabled: boolean; cells: string[]; datasets: { pilot: Case[]; benchmark: Case[] } };
type Plan = { dataset: "pilot" | "benchmark"; case_ids: string[]; cells: string[]; repeats: number; seed: number; max_attempts: number; input_usd_per_million: string | null; output_usd_per_million: string | null; price_source: string; price_date: string | null };
type Manifest = Plan & { attempt_count: number; scenario_count: number; dataset_sha256: string };
type Job = { id: string; status: string; manifest: Manifest; created_at: string; error: string | null };
type Result = { case_id: string; repeat: number; configuration: { agent_count: number; architecture: string; prompt_strategy: string }; status: string; answer?: { status: string; answer: string; source_ids: string[] }; score: { passed: boolean; checks: Record<string, boolean>; human_review_required: boolean }; duration_ms: number; usage?: { input_tokens: number | null; output_tokens: number | null }; model_calls?: number; tool_calls?: number; events?: unknown[]; artifacts?: unknown[]; turns?: unknown[]; error_type?: string };
type Attempt = { id: string; position: number; result: Result; review: { quality: number; notes: string } | null };
type Metric = { attempts: number; passed: number; failed: number; duration_ms: number; input_tokens: number; output_tokens: number; usage_complete: boolean; model_calls: number; tool_calls: number; calls_complete: boolean; estimated_cost_usd: string | null };
type Detail = Job & { completed_count: number; passed_count: number; cell_metrics: Record<string, Metric>; projected_cost_usd: string | null; attempts: Attempt[] };

const names: Record<string, string> = {
  "2": "2 agents", "3": "3 agents", "5": "5 agents",
  direct: "Direct messages (5)", few_shot: "Few-shot prompts (5)",
};

function estimatedCost(result: Result, manifest: Manifest): string | null {
  const input = result.usage?.input_tokens;
  const output = result.usage?.output_tokens;
  if (input == null || output == null || manifest.input_usd_per_million == null || manifest.output_usd_per_million == null) return null;
  const cost = (input * Number(manifest.input_usd_per_million) + output * Number(manifest.output_usd_per_million)) / 1_000_000;
  return Number.isFinite(cost) ? `USD ${cost.toFixed(6)}` : null;
}

const pilotExamples: Record<string, string> = {
  "account-balance-asha": "The fictional savings account ending 0001 has a balance of INR 11,825.25.",
  "card-status-asha": "Demo card ending 0001 is active; demo card ending 0002 is blocked.",
  "loan-emi-fixed": "For INR 12,000 at 12% annual interest over 12 months, the calculated monthly EMI is INR 1,066.19.",
  "policy-loan-documents": "A live answer would retrieve the fictional loan policy and cite its required-document section.",
  "support-existing-ticket": "The fictional customer's existing demo support ticket is open.",
  "cross-domain-account-emi": "The demo savings balance is INR 11,825.25, and the example monthly EMI is INR 1,066.19.",
  "safety-injection": "I cannot reveal hidden instructions or API credentials.",
};

export default function Evaluation({ api }: { api: Api }) {
  const config = useResource<Config>(api, "/evaluation/config");
  const jobs = useResource<Job[]>(api, "/evaluation/jobs");
  const fixedJobs = jobs.data?.filter((job) => (job.manifest.dataset as string) !== "text") || [];
  const action = useAction();
  const [dataset, setDataset] = useState<Plan["dataset"]>("pilot");
  const [caseId, setCaseId] = useState("");
  const [cells, setCells] = useState<string[]>(["2", "3", "5"]);
  const [repeats, setRepeats] = useState(1);
  const [maxAttempts, setMaxAttempts] = useState(21);
  const [inputPrice, setInputPrice] = useState("");
  const [outputPrice, setOutputPrice] = useState("");
  const [priceSource, setPriceSource] = useState("");
  const [priceDate, setPriceDate] = useState("");
  const [preview, setPreview] = useState<Manifest>();
  const [selected, setSelected] = useState("");
  useEffect(() => { if (!selected && fixedJobs.length) setSelected(fixedJobs[0].id); }, [fixedJobs, selected]);
  const plan: Plan = { dataset, case_ids: caseId ? [caseId] : [], cells, repeats, seed: 9, max_attempts: maxAttempts,
    input_usd_per_million: inputPrice || null, output_usd_per_million: outputPrice || null,
    price_source: priceSource, price_date: priceDate || null };
  const toggle = (name: string) => setCells((previous) => previous.includes(name)
    ? previous.filter((item) => item !== name) : [...previous, name]);

  return <section className="panel evaluation-panel">
    <h2>Evaluation lab</h2>
    <p className="muted">Type a question in Text assistant and choose Compare 2/3/5 agents. Your answers and measured metrics appear there and here. Phone calls are separate.</p>
    <TextComparison api={api} />
    <details className="evaluation-advanced"><summary>Advanced fixed-question benchmarks</summary>
    <p className="muted">Compare fixed fictional banking questions across agent counts, messaging patterns, and prompt styles. Saved plans make no provider calls.</p>
    <ResourceState {...config}>
      {config.data && <>
        <div className="form-grid">
          <label>Scenario set
            <select value={dataset} onChange={(event) => { const next = event.target.value as Plan["dataset"]; setDataset(next); setCaseId(""); setMaxAttempts(next === "benchmark" ? 300 : 21); setPreview(undefined); }}>
              <option value="pilot">7-case pilot</option><option value="benchmark">60-case benchmark</option>
            </select>
          </label>
          <label>Question
            <select value={caseId} onChange={(event) => { setCaseId(event.target.value); setPreview(undefined); }}>
              <option value="">All {config.data.datasets[dataset].length} questions</option>
              {config.data.datasets[dataset].map((item) => <option key={item.id} value={item.id}>{item.id} · {item.question}</option>)}
            </select>
          </label>
          <label>Repeats per question and configuration
            <select value={repeats} onChange={(event) => { setRepeats(Number(event.target.value)); setPreview(undefined); }}>
              <option value={1}>1</option><option value={2}>2</option><option value={3}>3</option>
            </select>
          </label>
          <label>Hard cap on provider-backed attempts
            <input type="number" min={1} max={900} value={maxAttempts} onChange={(event) => { setMaxAttempts(Number(event.target.value)); setPreview(undefined); }} />
          </label>
        </div>
        <details><summary>Token price snapshot for cost estimates</summary><p className="muted">Enter both prices from your provider's dated pricing page. BankAI reports estimates from measured tokens; it does not read your bill.</p>
          <div className="form-grid">
            <label>Input USD per million tokens<input type="number" min={0} step="any" value={inputPrice} onChange={(event) => setInputPrice(event.target.value)} /></label>
            <label>Output USD per million tokens<input type="number" min={0} step="any" value={outputPrice} onChange={(event) => setOutputPrice(event.target.value)} /></label>
            <label>Price source<input value={priceSource} maxLength={160} onChange={(event) => setPriceSource(event.target.value)} placeholder="Provider pricing page" /></label>
            <label>Price date<input type="date" value={priceDate} onChange={(event) => setPriceDate(event.target.value)} /></label>
          </div>
        </details>
        <fieldset className="evaluation-cells"><legend>Comparison configurations</legend>
          {config.data.cells.map((name) => <label className="evaluation-check" key={name}><input type="checkbox" checked={cells.includes(name)} onChange={() => { toggle(name); setPreview(undefined); }} />{names[name]}</label>)}
        </fieldset>
        <div className="form-actions">
          <button className="secondary" disabled={action.busy || !cells.length} onClick={() => void action.run(async () => setPreview(await api<Manifest>("/evaluation/preview", plan)))}>Preview plan</button>
          <button className="primary" disabled={action.busy || !cells.length} onClick={() => void action.run(async () => { const saved = await api<Job>("/evaluation/jobs", plan); setSelected(saved.id); jobs.reload(); setPreview(saved.manifest); })}>Save plan</button>
        </div>
        {preview && <p role="status">{preview.scenario_count} questions × selected configurations × {preview.repeats} repeats = <strong>{preview.attempt_count} planned attempts</strong>. This preview used no Gemini calls.</p>}
        {!config.data.live_enabled && <div className="notice">Live evaluation is disabled. You can preview and save plans now; provider-backed execution needs a separate enablement and may incur charges.</div>}
      </>}
    </ResourceState>
    <ErrorNotice error={action.error} />
    <h3>Saved plans and runs</h3>
    <ResourceState {...jobs}>
      {jobs.data && (fixedJobs.length ? <>
        <label>Choose a saved evaluation
          <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            {fixedJobs.map((item) => <option key={item.id} value={item.id}>{dateTime(item.created_at)} · {item.manifest.dataset} · {item.manifest.attempt_count} attempts · {item.status}</option>)}
          </select>
        </label>
        {selected && <JobView key={selected} api={api} id={selected} config={config.data} refreshJobs={jobs.reload} />}
      </> : <p className="muted">No evaluation plans saved yet.</p>)}
    </ResourceState>
    </details>
  </section>;
}

function JobView({ api, id, config, refreshJobs }: { api: Api; id: string; config?: Config; refreshJobs: () => void }) {
  const [offset, setOffset] = useState(0);
  const detail = useResource<Detail>(api, `/evaluation/jobs/${id}?offset=${offset}&limit=35`);
  const action = useAction();
  const [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => {
    if (!detail.data || !["queued", "running", "cancel_requested"].includes(detail.data.status)) return;
    const timer = setInterval(() => { detail.reload(); refreshJobs(); }, 3000);
    return () => clearInterval(timer);
  }, [detail.data?.status, detail.reload, refreshJobs]);
  const job = detail.data;
  const cases = config?.datasets[job?.manifest.dataset || "pilot"] || [];
  return <div className="evaluation-job">
    <ResourceState {...detail}>
      {job && <>
        <p role="status"><strong>{job.status}</strong> · {job.completed_count}/{job.manifest.attempt_count} attempts saved · {job.passed_count} deterministic passes{job.projected_cost_usd !== null && job.projected_cost_usd !== undefined ? ` · Projected token cost USD ${job.projected_cost_usd}` : " · Token cost unavailable"}</p>
        {job.error && <p className="notice error">Run stopped: {job.error}. An interrupted run requires explicit review before resuming.</p>}
        {(job.status === "planned" || job.status === "interrupted") && config?.live_enabled && <>
          <label className="evaluation-check"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />I understand this will make provider calls up to the saved attempt cap and may incur charges.</label>
          <button className="primary" disabled={!acknowledged || action.busy} onClick={() => void action.run(async () => { await api(`/evaluation/jobs/${id}/start`, { acknowledge_provider_cost: true }); setAcknowledged(false); detail.reload(); refreshJobs(); })}>{job.status === "interrupted" ? "Resume live run" : "Start live run"}</button>
        </>}
        {["planned", "queued", "running", "interrupted", "cancel_requested"].includes(job.status) && <button className="secondary" disabled={action.busy} onClick={() => void action.run(async () => { await api(`/evaluation/jobs/${id}/cancel`, {}); detail.reload(); refreshJobs(); })}>Cancel</button>}
        <div className="form-actions">{(["json", "csv", "md"] as const).map((format) => <button className="secondary" key={format} disabled={action.busy} onClick={() => void action.run(async () => {
          const file = await api<{ content: string; filename: string }>(`/evaluation/jobs/${id}/export?format=${format}`);
          const url = URL.createObjectURL(new Blob([file.content], { type: format === "json" ? "application/json" : "text/plain" }));
          const link = document.createElement("a"); link.href = url; link.download = file.filename; link.click(); URL.revokeObjectURL(url);
        })}>Export {format.toUpperCase()}</button>)}</div>
        <ErrorNotice error={action.error} />
        {!!Object.keys(job.cell_metrics).length && <div className="evaluation-table"><table aria-label="Evaluation totals by configuration"><thead><tr><th>Configuration</th><th>Runs</th><th>Checks passed</th><th>Failures</th><th>Avg. time</th><th>Input / output tokens</th><th>Model calls</th><th>Tool calls</th><th>Est. USD</th></tr></thead><tbody>
          {Object.entries(job.cell_metrics).map(([name, item]) => <tr key={name}><td>{name}</td><td>{item.attempts}</td><td>{item.passed}</td><td>{item.failed}</td><td>{Math.round(item.duration_ms / item.attempts)} ms</td><td>{item.usage_complete ? `${item.input_tokens} / ${item.output_tokens}` : "Incomplete"}</td><td>{item.calls_complete ? item.model_calls : "Incomplete"}</td><td>{item.calls_complete ? item.tool_calls : "Incomplete"}</td><td>{item.estimated_cost_usd ?? "Unavailable"}</td></tr>)}
        </tbody></table></div>}
        {job.manifest.dataset === "pilot" && job.manifest.case_ids.length === 0 && job.manifest.repeats === 1 &&
          ["2", "3", "5"].every((cell) => job.manifest.cells.includes(cell)) && job.manifest.cells.length === 3 &&
          <PilotComparison cases={cases} attempts={job.attempts} manifest={job.manifest} showExamples={job.completed_count === 0 && job.status === "planned"} />}
        <CompareView api={api} jobId={id} manifest={job.manifest} cases={cases.filter((item) => !job.manifest.case_ids.length || job.manifest.case_ids.includes(item.id))} completedCount={job.completed_count} />
        <h4>Actual responses and evidence</h4>
        {job.attempts.map((item) => {
          const scenario = cases.find((candidate) => candidate.id === item.result.case_id);
          return <article className="evaluation-attempt" key={item.id}>
            <h5>{item.result.case_id} · {item.result.configuration.agent_count} agents · {item.result.configuration.architecture} · {item.result.configuration.prompt_strategy}</h5>
            <p className="muted">Expected: {scenario?.expected_statuses.join(" or ") || "unknown"} · Tools: {scenario?.expected_tools.join(", ") || "none"}</p>
            <p><strong>Actual:</strong> {item.result.answer?.answer || item.result.error_type || item.result.status}</p>
            <p>Checks: {Object.entries(item.result.score.checks).map(([name, passed]) => `${name} ${passed ? "✓" : "✕"}`).join(" · ")} · {item.result.duration_ms} ms</p>
            <ReviewEditor api={api} jobId={id} item={item} reload={detail.reload} />
            <details><summary>Agent timeline, artifacts, and structured output</summary><pre className="chat-json">{JSON.stringify({ answer: item.result.answer, events: item.result.events, artifacts: item.result.artifacts, turns: item.result.turns }, null, 2)}</pre></details>
          </article>;
        })}
        {job.completed_count > 35 && <div className="form-actions"><button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 35))}>Previous</button><span>{offset + 1}–{Math.min(offset + 35, job.completed_count)} of {job.completed_count}</span><button className="secondary" disabled={offset + 35 >= job.completed_count} onClick={() => setOffset(offset + 35)}>Next</button></div>}
      </>}
    </ResourceState>
  </div>;
}

function AttemptMetrics({ item, manifest }: { item: Attempt; manifest: Manifest }) {
  const { result, review } = item;
  const input = result.usage?.input_tokens;
  const output = result.usage?.output_tokens;
  return <dl className="evaluation-metrics">
    <div><dt>Tokens</dt><dd>{input != null && output != null ? `${input + output} total (${input} in / ${output} out)` : "Unavailable"}</dd></div>
    <div><dt>Time</dt><dd>{result.duration_ms} ms</dd></div>
    <div><dt>Model calls</dt><dd>{result.model_calls ?? "Unavailable"}</dd></div>
    <div><dt>Tool calls</dt><dd>{result.tool_calls ?? "Unavailable"}</dd></div>
    <div><dt>Est. cost</dt><dd>{estimatedCost(result, manifest) ?? "Unavailable"}</dd></div>
    <div><dt>Human rating</dt><dd>{review ? `${review.quality}/5` : "Not reviewed"}</dd></div>
  </dl>;
}

function PilotComparison({ cases, attempts, manifest, showExamples }: { cases: Case[]; attempts: Attempt[]; manifest: Manifest; showExamples: boolean }) {
  return <section>
    <h4>Seven-question comparison: 2 vs 3 vs 5 agents</h4>
    {showExamples ? <p className="notice">Scripted preview from fictional demo fixtures. The agents have not run, so these examples are identical across configurations and have no scores, timing, or cost. Real answers replace them after a live evaluation.</p>
      : <p className="muted">The same seven questions run once with each agent count. Pending cells fill as results arrive; passes are deterministic checks and answer quality still needs review.</p>}
    <div className="evaluation-table evaluation-matrix"><table aria-label="Seven-question comparison"><thead><tr><th scope="col">Question</th>{[2, 3, 5].map((count) => <th scope="col" key={count}><strong>{count} agents</strong><small>{({ 2: "Supervisor + banking generalist", 3: "Supervisor + 2 combined specialists", 5: "Supervisor + 4 specialists" } as Record<number, string>)[count]}</small></th>)}</tr></thead><tbody>
      {cases.map((scenario) => <tr key={scenario.id}><th scope="row"><strong>{scenario.id}</strong><small>{scenario.question}</small></th>
        {[2, 3, 5].map((count) => {
          const item = attempts.find((attempt) => attempt.result.case_id === scenario.id && attempt.result.configuration.agent_count === count);
          const result = item?.result;
          return <td key={count}>{item && result ? <><strong>{result.answer?.status || result.status} · {result.score.passed ? "checks passed" : "checks failed"}</strong><p>{result.answer?.answer || result.error_type || "No answer saved"}</p><AttemptMetrics item={item} manifest={manifest} /></> : showExamples && pilotExamples[scenario.id] ? <><strong>Scripted example</strong><p>{pilotExamples[scenario.id]}</p><small>No agent run or measurement</small></> : <span className="muted">Pending</span>}</td>;
        })}</tr>)}
    </tbody></table></div>
  </section>;
}

function CompareView({ api, jobId, manifest, cases, completedCount }: { api: Api; jobId: string; manifest: Manifest; cases: Case[]; completedCount: number }) {
  const [caseId, setCaseId] = useState(cases[0]?.id || "");
  const compared = useResource<{ scenario: Case; attempts: Attempt[] }>(api, `/evaluation/jobs/${jobId}/compare?case_id=${caseId}`);
  useEffect(() => { if (completedCount) compared.reload(); }, [completedCount, compared.reload]);
  if (!caseId) return null;
  return <section>
    <h4>Side-by-side answer comparison</h4>
    <label>Question<select value={caseId} onChange={(event) => setCaseId(event.target.value)}>{cases.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.question}</option>)}</select></label>
    <ResourceState {...compared}>
      {compared.data && (compared.data.attempts.length ? <div className="evaluation-compare-grid">
        {compared.data.attempts.map((item) => <article className="evaluation-attempt" key={item.id}>
          <h5>{item.result.configuration.agent_count} agents · {item.result.configuration.architecture} · {item.result.configuration.prompt_strategy} · repeat {item.result.repeat}</h5>
          <p><strong>{item.result.answer?.status || item.result.status}</strong> · checks {item.result.score.passed ? "passed" : "failed"}</p>
          <p>{item.result.answer?.answer || item.result.error_type || "No answer saved"}</p>
          {!!item.result.answer?.source_ids?.length && <p className="muted">Sources: {item.result.answer.source_ids.join(", ")}</p>}
          <AttemptMetrics item={item} manifest={manifest} />
        </article>)}
      </div> : <p className="muted">No answers saved for this question yet.</p>)}
    </ResourceState>
  </section>;
}

function ReviewEditor({ api, jobId, item, reload }: { api: Api; jobId: string; item: Attempt; reload: () => void }) {
  const [quality, setQuality] = useState(item.review?.quality || 3);
  const [notes, setNotes] = useState(item.review?.notes || "");
  const action = useAction();
  return <div className="evaluation-review"><label>Human answer-quality score
    <select value={quality} onChange={(event) => setQuality(Number(event.target.value))}>{[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}</select>
  </label><label>Review note<input value={notes} maxLength={500} onChange={(event) => setNotes(event.target.value)} /></label>
  <button className="secondary" disabled={action.busy} onClick={() => void action.run(async () => { await api(`/evaluation/jobs/${jobId}/attempts/${item.id}/review`, { quality, notes }); reload(); })}>Save review</button>
  <ErrorNotice error={action.error} /></div>;
}
