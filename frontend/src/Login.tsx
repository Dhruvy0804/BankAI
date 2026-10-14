import { useState, type FormEvent } from "react";
import { request, useAction } from "./api";
import { ErrorNotice } from "./components";

export type Session = { token: string; expiresAt: number };

export default function Login({
  signedIn,
  message,
}: {
  signedIn: (session: Session) => void;
  message: string;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();
  function submit(event: FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      const result = await request<{
        access_token: string;
        expires_in: number;
      }>("/auth/login", undefined, { email: email.trim(), password });
      setPassword("");
      signedIn({
        token: result.access_token,
        expiresAt: Date.now() + result.expires_in * 1000,
      });
    });
  }
  return (
    <div className="login-layout">
      <section className="login-story">
        <a className="brand" href="/">
          <span className="brand-icon">B</span>BankAI
          <span className="brand-dot">.</span>
        </a>
        <div>
          <p className="eyebrow">YOUR BANKING WORKSPACE</p>
          <h1>
            A clearer view
            <br />
            of your banking.
          </h1>
          <p>Explore accounts, cards and loans in one simple demo workspace.</p>
          <div className="story-lines">
            <span>Account insights</span>
            <span>Confirmed card controls</span>
            <span>Demo loans & support</span>
          </div>
        </div>
        <small>Educational prototype · Fictional data only</small>
      </section>
      <main className="login-form">
        <form onSubmit={submit}>
          <span className="demo-pill">Demo environment</span>
          <h2>Welcome back</h2>
          <p className="muted">Sign in with your fictional BankAI account.</p>
          {message && (
            <p className="notice" role="status">
              {message}
            </p>
          )}
          <ErrorNotice error={action.error} />
          <fieldset disabled={action.busy}>
            <label>
              Email address
              <input
                type="email"
                autoComplete="username"
                required
                maxLength={254}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="demo.asha@bankai.example"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button className="primary" type="submit">
              {action.busy ? "Signing in…" : "Sign in"}
              <span aria-hidden="true">→</span>
            </button>
          </fieldset>
          <details className="demo-access">
            <summary>Local demo credentials</summary>
            <p>
              Email: demo.asha@bankai.example
              <br />
              Password: BankAI-demo-only-2026!
            </p>
            <p>
              You can also sign in as demo.ravi@bankai.example or
              demo.mira@bankai.example using the same demo password.
            </p>
          </details>
          <p className="login-note">
            Use fictional demo credentials only. Never enter real bank
            passwords, PINs or OTPs.
          </p>
        </form>
      </main>
    </div>
  );
}
