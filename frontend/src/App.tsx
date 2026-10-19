import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, type Api, type Customer, request, useResource } from "./api";
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
  ["dashboard", "Dashboard", "◈"],
  ["accounts", "Accounts", "▣"],
  ["transactions", "Transactions", "↔"],
  ["cards", "Cards", "▤"],
  ["loans", "Loans", "▥"],
  ["support", "Support", "◎"],
  ["chat", "Text assistant", "◌"],
  ["about", "About", "ⓘ"],
] as const;
type Page = (typeof navigation)[number][0];

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
  useEffect(() => {
    const changed = () => setPage(currentPage());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  const title = navigation.find(([value]) => value === page)![1];
  return (
    <div className="app-layout">
      <aside>
        <a className="brand" href="#dashboard">
          <span className="brand-icon">B</span>BankAI
          <span className="brand-dot">.</span>
        </a>
        <p className="nav-caption">YOUR BANKING</p>
        <nav aria-label="Main navigation">
          {navigation.map(([value, text, icon]) => (
            <a
              key={value}
              className={page === value ? "active" : ""}
              aria-current={page === value ? "page" : undefined}
              href={`#${value}`}
              onClick={() => setPage(value)}
            >
              <span aria-hidden="true">{icon}</span>
              {text}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="small-label">DEMO WORKSPACE</span>
          <p>
            Fictional accounts.
            <br />
            Real learning.
          </p>
          <button className="secondary" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>
      <main>
        <header>
          <span>
            Banking / <strong>{title}</strong>
          </span>
          <div className="header-user">
            <span className="demo-pill">
              <span className="dot" /> Synthetic data
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
  return (
    <section className="panel">
      <h2>A banking assistant with a research goal</h2>
      <p>
        BankAI is a final-year engineering project using fictional customers,
        accounts and policies. No real bank accounts are connected.
      </p>
      <h3>Available now</h3>
      <p>
        Secure demo login, account and transaction views, confirmed card
        blocking, EMI calculation, simulated loan applications and support
        tickets, and saved text conversations when a model provider is configured.
      </p>
      <h3>Coming next</h3>
      <p>
        A five-agent system, grounded policy answers and voice.
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
