import { useEffect, useState } from 'react';

type ServiceState = 'Checking' | 'Connected' | 'Unavailable';
type Status = { api: ServiceState; database: ServiceState };
const agents = ['Supervisor', 'Account', 'Card', 'Loan', 'Policy / Support'];

export default function App() {
  const [page, setPage] = useState<'overview' | 'roadmap'>('overview');
  const [status, setStatus] = useState<Status>({ api: 'Checking', database: 'Checking' });
  const [checking, setChecking] = useState(false);

  async function refresh() {
    setChecking(true);
    const check = async (path: string): Promise<ServiceState> => {
      try {
        const response = await fetch(path, { signal: AbortSignal.timeout(6000) });
        const data = await response.json();
        return response.ok && ['ok', 'ready'].includes(data.status) ? 'Connected' : 'Unavailable';
      } catch { return 'Unavailable'; }
    };
    const [api, database] = await Promise.all([check('/api/health'), check('/api/ready')]);
    setStatus({ api, database });
    setChecking(false);
  }
  useEffect(() => { void refresh(); }, []);

  return (
    <div className="app-layout">
      <aside>
        <a className="brand" href="/" aria-label="BankAI home"><span className="brand-icon">B</span>BankAI<span className="brand-dot">.</span></a>
        <p className="nav-caption">YOUR WORKSPACE</p>
        <nav aria-label="Main navigation">
          <button className={page === 'overview' ? 'active' : ''} onClick={() => setPage('overview')}>◈ <span>Overview</span></button>
          <button className={page === 'roadmap' ? 'active' : ''} onClick={() => setPage('roadmap')}>☷ <span>Build roadmap</span></button>
        </nav>
        <div className="sidebar-note"><span className="small-label">LOCAL PROTOTYPE</span><p>A banking assistant.<br />A place to test ideas.</p><span className="muted">Fictional data only</span></div>
      </aside>
      <main>
        <header><span>Workspace / <strong>{page === 'overview' ? 'Overview' : 'Build roadmap'}</strong></span><span className="demo-pill"><span className="dot" /> Demo environment</span></header>
        <div className="content">
          <div className="heading"><div><p className="eyebrow">BANKING, WITH A RESEARCH MINDSET</p><h1>{page === 'overview' ? 'Your BankAI workspace' : 'Built one phase at a time'}</h1><p className="subtitle">{page === 'overview' ? 'One place for conversational banking and agent evaluation.' : 'A clear path from a working foundation to a measured comparison.'}</p></div><span className="phase-tag">Phase 01 / Foundation</span></div>
          {page === 'overview' ? <>
            <section className="hero-card"><div><span className="small-label">THE FOUNDATION IS TAKING SHAPE</span><h2>Understand your banking.<br />Explore how agents work.</h2><p>The application shell is ready. Banking workflows and the private evaluation dashboard will arrive in the next phases.</p><button className="primary" onClick={() => setPage('roadmap')}>Explore the build roadmap <span aria-hidden="true">↗</span></button></div><div className="agent-map" aria-label="Planned five-agent architecture"><div className="supervisor">Supervisor<span>Routes each request</span></div><div className="agent-branches">{agents.slice(1).map(agent => <div key={agent}>{agent}</div>)}</div><p>5 total agents · shared banking tools</p></div></section>
            <div className="section-heading"><h2>Two connected experiences</h2><span>Planned capabilities</span></div>
            <div className="experience-grid"><article className="experience"><span className="tile-icon">↔</span><span className="badge">COMING IN PHASES 3–8</span><h3>Conversational banking</h3><p>Accounts, cards, loans and support, brought together through text and voice.</p><div className="chips"><span>5-agent assistant</span><span>BankSim data</span></div></article><article className="experience"><span className="tile-icon violet">▥</span><span className="badge">COMING IN PHASE 9</span><h3>Your evaluation lab</h3><p>Compare the same task across agent configurations. Inspect responses, tool calls and measured results.</p><div className="chips"><span>2 vs 3 vs 5 agents</span><span>Private workspace</span></div></article></div>
          </> : <section className="roadmap" aria-label="Implementation roadmap">{[
            ['00–01', 'Foundation', 'Project structure, health checks, frontend shell and local PostgreSQL.', 'Current checkpoint'],
            ['02–04', 'Banking essentials', 'Database models, fictional seed data, secure login and banking pages.', 'Planned'],
            ['05–07', 'The agent system', 'Text chat, five-agent orchestration, tools and grounded policy answers.', 'Planned'],
            ['08', 'Voice conversations', 'LiveKit audio connected to the same banking workflows.', 'Planned'],
            ['09', 'Evaluation lab', 'Private 2/3/5-agent comparisons, traces, metrics, history and exports.', 'Planned'],
            ['10', 'Final demonstration', 'Fresh-setup checks, comparison report and professor-ready walkthrough.', 'Planned'],
          ].map(([number, title, description, state]) => <article key={number}><span className="phase-number">{number}</span><div><h3>{title}</h3><p>{description}</p></div><span className="badge">{state}</span></article>)}</section>}
          <section className="service-panel" aria-label="Service status"><div><h2>Environment status</h2><p>Live checks from your local backend.</p></div><div className="service-values" aria-live="polite">{Object.entries(status).map(([key, value]) => <div key={key}><span>{key === 'api' ? 'Backend API' : 'PostgreSQL'}</span><strong className={value === 'Connected' ? 'connected' : 'muted'}><span className="dot" />{value}</strong></div>)}</div><button className="secondary" disabled={checking} onClick={() => void refresh()}>{checking ? 'Checking…' : 'Refresh status'}</button></section>
          {status.api === 'Unavailable' && <p role="status" className="notice">Start the FastAPI backend on port 8000 to connect this workspace.</p>}
          {status.api === 'Connected' && status.database === 'Unavailable' && <p role="status" className="notice">The backend is running. Start the PostgreSQL service to complete the local environment.</p>}
          <footer><span>BankAI · Final-year engineering project</span><span>No real accounts. No real transactions.</span></footer>
        </div>
      </main>
    </div>
  );
}
