import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeftRight, Bot, ChevronLeft, ChevronRight, CircleHelp, CreditCard, Landmark, LayoutDashboard, LifeBuoy, LogOut, ShieldCheck, Wallet } from "lucide-react";
import { ApiError, type Api, type Customer, request, useResource } from "./api";
import { Button } from "./components/ui/button";
import { ResourceState } from "./components";
import Login, { type Session } from "./Login";
import Chat from "./Chat";
import {
  Accounts,
  Cards,
  Dashboard,
  Loans,
  Support,
  Transactions,
} from "./pages";

// shortcut: tab storage is JavaScript-readable; use HttpOnly cookies before public deployment.
const SESSION_KEY = "bankai-session";
const navigation = [
  ["dashboard", "Dashboard", LayoutDashboard],
  ["accounts", "Accounts", Wallet],
  ["transactions", "Transactions", ArrowLeftRight],
  ["cards", "Cards", CreditCard],
  ["loans", "Loans", Landmark],
  ["support", "Support", LifeBuoy],
  ["chat", "Text assistant", Bot],
  ["about", "About", CircleHelp],
] as const;
type Page = (typeof navigation)[number][0];
const Intro = lazy(() => import("./Intro"));

function savedSession(): Session | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
    if (
      value &&
      typeof value.token === "string" &&
      value.token.length > 0 &&
      value.token.length < 8192 &&
      Number.isFinite(value.expiresAt) &&
      value.expiresAt > Date.now()
    )
      return value;
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* Storage can be unavailable in private browser contexts. */
  }
  return null;
}

function currentPage(): Page {
  const value = window.location.hash.slice(1);
  return navigation.some(([page]) => page === value)
    ? (value as Page)
    : "dashboard";
}

function BankingWorkspace({ api, signOut }: { api: Api; signOut: () => void }) {
  const customer = useResource<Customer>(api, "/auth/me");
  const [page, setPage] = useState<Page>(currentPage);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const changed = () => setPage(currentPage());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  const title = navigation.find(([value]) => value === page)![1];
  return (
    <div className={`app-layout${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside aria-label="Workspace sidebar">
        <a className="brand" href="#dashboard">
          <span className="brand-icon"><Landmark size={20} strokeWidth={1.8} /></span>
          <span className="brand-word">BankAI<span className="brand-dot">.</span><small>AGENT WORKSPACE</small></span>
        </a>
        <div className="sidebar-section-heading"><p className="nav-caption">WORKSPACE</p>
          <Button variant="ghost" size="icon" className="sidebar-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCollapsed(!collapsed)}>{collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}</Button>
        </div>
        <nav aria-label="Main navigation">
          {navigation.map(([value, text, Icon]) => (
            <a
              key={value}
              className={page === value ? "active" : ""}
              aria-current={page === value ? "page" : undefined}
              href={`#${value}`}
              title={collapsed ? text : undefined}
              aria-label={collapsed ? text : undefined}
              onClick={() => setPage(value)}
            >
              {page === value && <motion.span layoutId="active-nav" className="nav-active-indicator" transition={{ type: "spring", stiffness: 380, damping: 35 }} />}
              <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
              <span className="nav-text">{text}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="small-label">CURRENT SESSION</span>
          <p>{customer.data?.full_name || "Demo customer"}<br /><small>Fictional banking data</small></p>
          <Button variant="outline" size="sm" onClick={signOut}><LogOut size={15} /><span className="nav-text">Sign out</span></Button>
        </div>
      </aside>
      <main>
        <header>
          <span className="header-crumb">BankAI <ChevronRight size={14} aria-hidden="true" /> <strong>{title}</strong></span>
          <div className="header-user">
            <span className="connection-indicator"><span className="dot" />{customer.data ? "Connected" : "Connecting"}</span>
            <span className="demo-pill">
              <ShieldCheck size={13} aria-hidden="true" /> Synthetic data
            </span>
            <button className="secondary mobile-signout" onClick={signOut}>
              Sign out
            </button>
          </div>
        </header>
        <div className="content">
          <div className="heading">
            <div>
              <p className="eyebrow">YOUR BANKAI WORKSPACE</p>
              <h1>
                {page === "dashboard"
                  ? `Welcome${customer.data ? ", " + customer.data.full_name : ""}`
                  : title}
              </h1>
              <p className="subtitle">
                {page === "dashboard"
                  ? "Your accounts and latest activity, in one place."
                  : "Manage your fictional banking records."}
              </p>
            </div>
            <span className="phase-tag">Demo banking</span>
          </div>
          <ResourceState {...customer}>
            {customer.data && (
              <div key={page}>
                {page === "dashboard" && <Dashboard api={api} />}
                {page === "accounts" && <Accounts api={api} />}
                {page === "transactions" && <Transactions api={api} />}
                {page === "cards" && <Cards api={api} />}
                {page === "loans" && <Loans api={api} />}
                {page === "support" && <Support api={api} />}
                {page === "chat" && <Chat api={api} />}
                {page === "about" && <About />}
              </div>
            )}
          </ResourceState>
          <footer>
            <span>BankAI · Educational banking prototype</span>
            <span>All balances and actions are simulated.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

function About() {
  const [showIntro, setShowIntro] = useState(false);
  return (
    <section className="panel">
      <h2>A banking assistant with a research goal</h2>
      <button className="secondary" type="button" onClick={() => setShowIntro((value) => !value)}>{showIntro ? "Hide introduction" : "Play illustrated introduction"}</button>
      {showIntro && <><p className="muted">Illustrative network animation · not a live agent run</p><Suspense fallback={<p role="status">Loading introduction…</p>}><Intro /></Suspense></>}
      <p>
        BankAI is a final-year engineering project using fictional customers,
        accounts and policies. No real bank accounts are connected.
      </p>
      <h3>Available now</h3>
      <p>
        Secure demo login, account and transaction views, confirmed card
        blocking, EMI calculation, simulated loan applications and support
        tickets, five-agent text conversations with policy sources, and browser
        voice when the required providers are configured. The owner can also
        configure a Twilio phone test for a selected fictional customer.
      </p>
      <h3>Coming next</h3>
      <p>
        A verified live telephone demonstration and cloud deployment.
        A private evaluation lab will compare the same tasks across 2, 3 and 5
        total agents, including the supervisor.
      </p>
      <p className="muted">
        This local prototype uses React, TypeScript, FastAPI and PostgreSQL.
        Never enter real banking credentials or identity documents.
      </p>
    </section>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(savedSession);
  const [message, setMessage] = useState("");
  const activeToken = useRef(session?.token);
  activeToken.current = session?.token;
  const signOut = useCallback((notice = "") => {
    activeToken.current = undefined;
    setSession(null);
    setMessage(notice);
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* In-memory sign-out still works. */
    }
  }, []);
  function signedIn(value: Session) {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } catch {
      /* Sign-in still works until refresh. */
    }
    setSession(value);
    setMessage("");
    window.location.hash = "dashboard";
  }
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(
      () => signOut("Your session expired. Sign in again."),
      Math.max(0, Math.min(session.expiresAt - Date.now(), 2147483647)),
    );
    return () => clearTimeout(timer);
  }, [session, signOut]);
  const api = useMemo<Api>(
    () =>
      async <T,>(path: string, body?: unknown, signal?: AbortSignal) => {
        try {
          return await request<T>(path, session?.token, body, signal);
        } catch (error) {
          if (
            error instanceof ApiError &&
            error.status === 401 &&
            activeToken.current === session?.token
          )
            signOut("Your session ended. Sign in again.");
          throw error;
        }
      },
    [session, signOut],
  );
  return session ? (
    <BankingWorkspace
      key={session.token}
      api={api}
      signOut={() => signOut("You have signed out.")}
    />
  ) : (
    <Login signedIn={signedIn} message={message} />
  );
}
