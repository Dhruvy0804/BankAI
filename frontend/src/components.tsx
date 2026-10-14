import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, type Pending, dateTime, useAction } from "./api";

export function ErrorNotice({
  error,
  retry,
}: {
  error?: Error;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="notice error" role="alert">
      <p>{error.message}</p>
      {error instanceof ApiError && error.requestId && (
        <small>Request reference: {error.requestId}</small>
      )}
      {retry && (
        <button className="secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function ResourceState({
  loading,
  error,
  empty,
  reload,
  children,
}: {
  loading: boolean;
  error?: Error;
  empty?: string;
  reload: () => void;
  children: ReactNode;
}) {
  if (loading)
    return (
      <p className="empty-state" role="status">
        Loading your demo records…
      </p>
    );
  if (error) return <ErrorNotice error={error} retry={reload} />;
  if (empty) return <p className="empty-state">{empty}</p>;
  return <>{children}</>;
}

export function Confirmation({
  pending,
  title,
  children,
  confirm,
  close,
  returnFocus,
}: {
  pending: Pending;
  title: string;
  children: ReactNode;
  confirm: () => Promise<void>;
  close: () => void;
  returnFocus?: HTMLElement | null;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const action = useAction();
  const [now, setNow] = useState(Date.now());
  const expired = now >= new Date(pending.expires_at).getTime();
  useEffect(() => {
    const element = dialog.current!;
    const previous = document.activeElement as HTMLElement | null;
    if (element.showModal) element.showModal();
    else element.setAttribute("open", "");
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(timer);
      if (element.close) element.close();
      (returnFocus || previous)?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-labelledby="confirmation-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!action.busy) close();
      }}
    >
      <p className="eyebrow">CONFIRM SIMULATED ACTION</p>
      <h2 id="confirmation-title">{title}</h2>
      {children}
      <p className="muted">
        Expires {dateTime(pending.expires_at)}. This affects fictional demo data
        only.
      </p>
      {expired && (
        <p role="alert">
          This request expired. Close this dialog and start a new request.
        </p>
      )}
      <ErrorNotice error={action.error} />
      <div className="form-actions">
        <button
          autoFocus
          className="secondary"
          disabled={action.busy}
          onClick={close}
        >
          Cancel
        </button>
        <button
          className="primary"
          disabled={action.busy || expired}
          onClick={() => void action.run(confirm)}
        >
          {action.busy ? "Confirming…" : "Confirm action"}
        </button>
      </div>
    </dialog>
  );
}
