import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { motion } from "motion/react";
import { Activity, Bot, CreditCard, Landmark, LifeBuoy, RotateCcw, Search, Wallet } from "lucide-react";
import { type Api, dateTime, label, useResource } from "./api";
import { ErrorNotice } from "./components";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./components/ui/sheet";
import { eventCategory, eventLabel, roleDescription, roleState, type WorkflowEvent, type WorkflowTrace } from "./presentation/workflow";

type Source = { citation_id: string; title: string; section: string };
const icons = { supervisor: Bot, account: Wallet, card: CreditCard, loan: Landmark, support: LifeBuoy };
const usefulEvents = new Set(["run_start", "run_end", "run_error", "agent_start", "agent_end", "agent_error", "a2a_send", "a2a_result", "state_consume", "message_consume", "state_publish", "tool_start", "tool_result", "tool_error", "retrieval_result", "output_validated", "guardrail_rejected", "validation_error"]);

export default function AgentWorkflow({ api, runId, processing, sources = [] }: { api: Api; runId?: string; processing: boolean; sources?: Source[] }) {
  if (processing) return <Card className="workflow-card"><CardHeader><CardTitle>Agent workflow</CardTitle><CardDescription>BankAI is processing your request. Individual agent events become visible after the response is saved.</CardDescription></CardHeader><CardContent><WorkflowCanvas roles={defaultRoles} states={{}} observed={new Set()} select={() => {}} /><p className="workflow-caption" role="status">Processing request · agent selection is not observable yet</p></CardContent></Card>;
  if (!runId) return <Card className="workflow-card"><CardHeader><CardTitle>Agent workflow</CardTitle><CardDescription>Ask a banking question to inspect the recorded agent path.</CardDescription></CardHeader><CardContent><WorkflowCanvas roles={defaultRoles} states={{}} observed={new Set()} select={() => {}} /><p className="workflow-caption">Configured topology · no run selected</p></CardContent></Card>;
  return <SavedWorkflow key={runId} api={api} runId={runId} sources={sources} />;
}

const defaultRoles = { supervisor: "Google ADK", account: "CrewAI", card: "CrewAI", loan: "CrewAI", support: "CrewAI" };

function SavedWorkflow({ api, runId, sources }: { api: Api; runId: string; sources: Source[] }) {
  const trace = useResource<WorkflowTrace>(api, `/chat/runs/${runId}`);
  const [selected, setSelected] = useState<string>();
  const [cursor, setCursor] = useState<number>();
  const [replaying, setReplaying] = useState(false);
  useEffect(() => {
    if (!replaying || !trace.data) return;
    const timer = setInterval(() => setCursor((value) => {
      const next = Math.min((value ?? 0) + 1, trace.data!.events.length);
      if (next === trace.data!.events.length) setReplaying(false);
      return next;
    }), 450);
    return () => clearInterval(timer);
  }, [replaying, trace.data]);
  if (trace.loading) return <Card className="workflow-card"><CardHeader><CardTitle>Agent workflow</CardTitle><CardDescription>Loading saved execution trace…</CardDescription></CardHeader><CardContent><div className="workflow-loading" role="status" /></CardContent></Card>;
  if (trace.error || !trace.data) return <ErrorNotice error={trace.error || new Error("Execution trace is unavailable.")} retry={trace.reload} />;
  const data = trace.data;
  const visible = data.events.slice(0, cursor ?? data.events.length);
  const current = replaying ? visible.at(-1) : undefined;
  const states = Object.fromEntries(Object.keys(data.configured_roles).map((role) => [role, roleState(data, role, visible)]));
  const observed = new Set(visible.filter((event) => event.kind === "a2a_send" && typeof event.metadata.target === "string").map((event) => String(event.metadata.target)));
  const artifact = data.artifacts.find((item) => item.role === selected);
  const roleEvents = visible.filter((event) => event.role === selected && usefulEvents.has(event.kind));
  const events = visible.filter((event) => usefulEvents.has(event.kind));
  const toolEvents = visible.filter((event) => ["tool_result", "tool_error"].includes(event.kind));
  const retrieval = visible.filter((event) => event.kind === "retrieval_result");
  return <Card className="workflow-card">
    <CardHeader className="workflow-header"><div><CardTitle>Agent workflow</CardTitle><CardDescription>Recorded {data.configuration.agent_count}-agent run · {label(data.configuration.architecture)} context · {label(data.configuration.prompt_strategy)} prompts</CardDescription></div><div className="workflow-header-actions"><Badge variant="outline" className={`workflow-badge workflow-badge-${data.status}`}>{data.status}</Badge><Button type="button" variant="outline" size="sm" disabled={replaying || !data.events.length} onClick={() => { setCursor(0); setReplaying(true); }}><RotateCcw size={14} /> Replay trace</Button></div></CardHeader>
    <CardContent>
      <div className="workflow-metrics"><span>{data.model_calls} model calls</span><span>{data.tool_calls} tool calls</span><span>{data.total_tokens ?? "—"} tokens</span><span>{data.artifacts.length} shared results</span></div>
      <WorkflowCanvas roles={data.configured_roles} states={states} observed={observed} current={current} select={setSelected} />
      <p className="workflow-caption">{replaying ? "Replay of saved events · not live execution" : "Select a node to inspect observed activity. Drag or zoom the canvas to explore."}</p>
      <div className="workflow-lower">
        <section className="workflow-timeline" aria-label="Execution timeline"><h3><Activity size={17} /> Execution timeline</h3>{events.length ? <ol>{events.map((event) => <motion.li key={event.id} initial={replaying ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: .2 }} className={`timeline-${eventCategory(event)}`}><span className="timeline-dot" /><div><strong>{eventLabel(event)}</strong><small>{label(event.role)} · {dateTime(event.at)}</small></div></motion.li>)}</ol> : <p className="muted">No execution events recorded.</p>}</section>
        <div className="workflow-side"><section aria-label="Tool activity"><h3>Tool activity</h3>{toolEvents.length ? <div className="tool-activity">{toolEvents.map((event) => <div key={event.id} className={`tool-activity-card ${event.kind === "tool_error" ? "tool-error" : ""}`}><span>{event.kind === "tool_error" ? "Failed" : "Completed"}</span><strong>{typeof event.metadata.tool === "string" ? label(event.metadata.tool) : "Banking tool"}</strong><small>{label(event.role)}{typeof event.metadata.duration_ms === "number" ? ` · ${event.metadata.duration_ms} ms` : ""}</small></div>)}</div> : <p className="muted">No banking tool result in this run.</p>}</section>
          <section aria-label="Policy retrieval"><h3><Search size={16} /> Policy retrieval</h3>{retrieval.length ? <><p className="muted">{retrieval.map((event) => Array.isArray(event.metadata.source_ids) ? event.metadata.source_ids.length : 0).reduce((a, b) => a + b, 0)} source references returned by search.</p>{sources.map((source) => <div className="source-preview" key={source.citation_id}><strong>{source.title}</strong><small>{source.section} · {source.citation_id}</small></div>)}</> : <p className="muted">No policy retrieval observed.</p>}</section></div>
      </div>
    </CardContent>
    <Sheet open={!!selected} onOpenChange={(open) => { if (!open) setSelected(undefined); }}><SheetContent className="workflow-inspector" side="right"><SheetHeader><SheetTitle>{selected ? label(selected) : "Agent"} agent</SheetTitle><SheetDescription>{selected ? roleDescription[selected] || "Configured specialist" : "Recorded agent activity"}</SheetDescription></SheetHeader>{selected && <div className="inspector-body"><Badge variant="outline" className={`workflow-badge workflow-badge-${states[selected] || "idle"}`}>{states[selected] || "idle"}</Badge><p className="muted">{data.configured_roles[selected]} · {artifact ? `Artifact revision ${artifact.revision}` : "No verified artifact for this role"}</p>{artifact && <><h3>Verified result</h3><p className="chat-text">{artifact.summary.answer}</p><p className="muted">Tools: {artifact.facts.length ? [...new Set(artifact.facts.map((fact) => label(fact.tool)))].join(", ") : "None"}</p>{!!artifact.consumed.length && <p className="muted">Used shared context from {artifact.consumed.map((id) => data.artifacts.find((item) => item.id === id)?.role || "prior agent").map(label).join(", ")}.</p>}</> }<h3>Observed activity</h3>{roleEvents.length ? <ol>{roleEvents.map((event) => <li key={event.id}><strong>{eventLabel(event)}</strong><small>{dateTime(event.at)}</small></li>)}</ol> : <p className="muted">No activity recorded for this role.</p>}</div>}</SheetContent></Sheet>
  </Card>;
}

function WorkflowCanvas({ roles, states, observed, current, select }: { roles: Record<string, string>; states: Record<string, string>; observed: Set<string>; current?: WorkflowEvent; select: (role: string) => void }) {
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 760px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const changed = () => setCompact(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  const specialists = Object.keys(roles).filter((role) => role !== "supervisor");
  const nodes: Node[] = useMemo(() => Object.keys(roles).map((role, index) => {
    const Icon = icons[role as keyof typeof icons] || Bot;
    const state = states[role] || "idle";
    return { id: role, type: "default", position: compact ? { x: 0, y: index * 114 } : role === "supervisor" ? { x: 368, y: 18 } : { x: (index - 1) * 246, y: 222 }, data: { label: <div className={`workflow-node-content node-${state}`}><span className="workflow-node-icon"><Icon size={18} /></span><span><strong>{label(role)}</strong><small>{roles[role]} · {state === "idle" ? "Not called" : state}</small></span></div> }, style: { width: 220 }, draggable: false };
  }), [roles, states, compact]);
  const edges: Edge[] = useMemo(() => specialists.map((role) => ({ id: `supervisor-${role}`, source: "supervisor", target: role, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed, color: observed.has(role) ? "#818cf8" : "#464653" }, animated: current?.kind === "a2a_send" && current.metadata.target === role, style: { stroke: observed.has(role) ? "#818cf8" : "#464653", strokeWidth: observed.has(role) ? 2 : 1.2 } })), [specialists, observed, current]);
  return <div className="workflow-canvas" aria-label="Agent network diagram"><ReactFlow key={compact ? "compact" : "wide"} nodes={nodes} edges={edges} colorMode="dark" fitView fitViewOptions={{ padding: .25 }} minZoom={.45} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => select(node.id)}><Background color="#2b2b36" gap={22} size={1} /><Controls showInteractive={false} /></ReactFlow></div>;
}
