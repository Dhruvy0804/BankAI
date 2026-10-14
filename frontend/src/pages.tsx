import { useRef, useState, type FormEvent } from "react";
import {
  type Api,
  type Account,
  type Card,
  type EMI,
  type Eligibility,
  type KYC,
  type Loan,
  type Pending,
  type Ticket,
  type TransactionPage,
  dateTime,
  label,
  money,
  useAction,
  useResource,
} from "./api";
import { Confirmation, ErrorNotice, ResourceState } from "./components";

export function AccountCards({ accounts }: { accounts: Account[] }) {
  return (
    <div className="account-grid">
      {accounts.map((account) => (
        <article className="account-card" key={account.id}>
          <div className="card-top">
            <span>{label(account.account_type)} account</span>
            <span className={`status ${account.status}`}>
              {label(account.status)}
            </span>
          </div>
          <p className="account-number">{account.account_number}</p>
          <strong className="balance">
            {money(account.balance, account.currency)}
          </strong>
          <p className="muted">Available demo balance</p>
        </article>
      ))}
    </div>
  );
}

function TransactionTable({
  page,
  accounts = [],
}: {
  page: TransactionPage;
  accounts?: Account[];
}) {
  if (!page.items.length)
    return <p className="empty-state">No transactions match this view.</p>;
  return (
    <div className="table-scroll">
      <table>
        <caption className="sr-only">Demo transaction history</caption>
        <thead>
          <tr>
            <th scope="col">Transaction</th>
            <th scope="col">Account</th>
            <th scope="col">Date</th>
            <th scope="col">Status</th>
            <th scope="col" className="numeric">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {page.items.map((item) => {
            const account = accounts.find(
              (value) => value.id === item.account_id,
            );
            return (
              <tr key={item.id}>
                <td>
                  <strong>{item.description}</strong>
                  <small>{item.merchant || item.reference_code}</small>
                </td>
                <td>{account?.account_number || "Demo account"}</td>
                <td>{dateTime(item.occurred_at)}</td>
                <td>
                  <span className={`status ${item.status}`}>
                    {label(item.status)}
                  </span>
                </td>
                <td
                  className={`numeric ${item.transaction_type === "credit" ? "credit" : ""}`}
                >
                  {item.transaction_type === "credit" ? "+" : "−"}
                  {money(item.amount, account?.currency || "INR")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard({ api }: { api: Api }) {
  const accounts = useResource<Account[]>(api, "/accounts");
  const transactions = useResource<TransactionPage>(
    api,
    "/transactions?limit=5",
  );
  const kyc = useResource<KYC>(api, "/kyc/status");
  return (
    <>
      <div className="section-heading">
        <h2>Your accounts</h2>
        <a href="#accounts">View accounts ↗</a>
      </div>
      <ResourceState
        {...accounts}
        empty={
          accounts.data?.length === 0
            ? "No demo accounts yet. Registered accounts start without funds."
            : undefined
        }
      >
        <AccountCards accounts={accounts.data || []} />
      </ResourceState>
      <div className="dashboard-grid">
        <section className="panel">
          <p className="eyebrow">QUICK ACCESS</p>
          <h2>What would you like to do?</h2>
          <div className="quick-links">
            <a href="#transactions">
              Review transactions <span>↗</span>
            </a>
            <a href="#cards">
              Manage demo cards <span>↗</span>
            </a>
            <a href="#loans">
              Explore demo loans <span>↗</span>
            </a>
            <a href="#support">
              Get support <span>↗</span>
            </a>
          </div>
        </section>
        <section className="panel">
          <p className="eyebrow">ACCOUNT VERIFICATION</p>
          <h2>Demo KYC status</h2>
          <ResourceState {...kyc}>
            <span className={`status ${kyc.data?.status}`}>
              {label(kyc.data?.status || "")}
            </span>
            <p className="muted">{kyc.data?.notes}</p>
            <small>
              Fictional verification record. No identity documents are
              collected.
            </small>
          </ResourceState>
        </section>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Recent activity</h2>
          <a href="#transactions">All transactions ↗</a>
        </div>
        <ResourceState {...transactions}>
          <TransactionTable
            page={transactions.data || { items: [], next_cursor: null }}
            accounts={accounts.data}
          />
        </ResourceState>
      </section>
      <p className="future-note">
        Text assistance, voice conversations and the private agent evaluation
        lab arrive in later phases.
      </p>
    </>
  );
}

function BalanceDetails({ api, account }: { api: Api; account: Account }) {
  const resource = useResource<{ balance: string; currency: string }>(
    api,
    `/accounts/${account.id}/balance`,
  );
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>{account.account_number}</h2>
        <button className="secondary" onClick={resource.reload}>
          Refresh balance
        </button>
      </div>
      <ResourceState {...resource}>
        <p className="balance">
          {resource.data &&
            money(resource.data.balance, resource.data.currency)}
        </p>
        <p>
          {label(account.account_type)} · {label(account.status)}
        </p>
        <a href={`#transactions`}>Review account transactions ↗</a>
      </ResourceState>
    </section>
  );
}

export function Accounts({ api }: { api: Api }) {
  const resource = useResource<Account[]>(api, "/accounts");
  const [selected, setSelected] = useState<Account>();
  return (
    <>
      <ResourceState
        {...resource}
        empty={
          resource.data?.length === 0
            ? "No demo accounts are available for this customer."
            : undefined
        }
      >
        <AccountCards accounts={resource.data || []} />
        <div className="account-select">
          <label>
            Account details
            <select
              aria-label="Account details"
              value={selected?.id || ""}
              onChange={(event) =>
                setSelected(
                  resource.data?.find(
                    (account) => account.id === event.target.value,
                  ),
                )
              }
            >
              <option value="">Choose an account</option>
              {resource.data?.map((account) => (
                <option value={account.id} key={account.id}>
                  {account.account_number} · {label(account.account_type)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </ResourceState>
      {selected && (
        <BalanceDetails key={selected.id} api={api} account={selected} />
      )}
    </>
  );
}

export function Transactions({ api }: { api: Api }) {
  const accounts = useResource<Account[]>(api, "/accounts");
  const [filters, setFilters] = useState("");
  const [cursor, setCursor] = useState(0);
  const [previous, setPrevious] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const resource = useResource<TransactionPage>(
    api,
    `/transactions?limit=10&cursor=${cursor}${filters ? "&" + filters : ""}`,
  );
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    new FormData(event.currentTarget).forEach((value, key) => {
      if (String(value)) params.set(key, String(value));
    });
    setFilters(params.toString());
    setCursor(0);
    setPrevious([]);
  }
  const displayed = resource.data
    ? {
        ...resource.data,
        items: resource.data.items.filter((item) =>
          `${item.description} ${item.merchant || ""} ${item.reference_code}`
            .toLowerCase()
            .includes(search.toLowerCase()),
        ),
      }
    : undefined;
  return (
    <>
      <form className="panel filter-form" onSubmit={apply}>
        <div className="form-grid">
          <label>
            Account
            <select
              name="account_id"
              disabled={accounts.loading || !!accounts.error}
            >
              <option value="">All accounts</option>
              {accounts.data?.map((account) => (
                <option value={account.id} key={account.id}>
                  {account.account_number}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <select name="transaction_type" aria-label="Type">
              <option value="">All types</option>
              <option value="credit">Credit</option>
              <option value="debit">Debit</option>
            </select>
          </label>
          <label>
            Status
            <select name="status">
              <option value="">All statuses</option>
              <option>completed</option>
              <option>pending</option>
              <option>failed</option>
            </select>
          </label>
          <label>
            From date
            <input name="date_from" type="date" />
          </label>
          <label>
            To date
            <input name="date_to" type="date" />
          </label>
          <label>
            Minimum amount
            <input
              name="min_amount"
              type="number"
              min="0"
              max="100000000"
              step="0.01"
            />
          </label>
          <label>
            Maximum amount
            <input
              name="max_amount"
              type="number"
              min="0"
              max="100000000"
              step="0.01"
            />
          </label>
        </div>
        <ErrorNotice error={accounts.error} retry={accounts.reload} />
        <button className="primary" type="submit">
          Apply filters
        </button>
      </form>
      <section className="panel">
        <div className="section-heading">
          <h2>Transaction history</h2>
          <button className="secondary" onClick={resource.reload}>
            Refresh
          </button>
        </div>
        <label className="search-label">
          Search this page
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Description, merchant or reference"
          />
        </label>
        <ResourceState {...resource}>
          <TransactionTable
            page={displayed || { items: [], next_cursor: null }}
            accounts={accounts.data}
          />
        </ResourceState>
        <div className="pagination">
          <button
            className="secondary"
            disabled={
              resource.loading || !!resource.error || previous.length === 0
            }
            onClick={() => {
              setCursor(previous[previous.length - 1]);
              setPrevious(previous.slice(0, -1));
            }}
          >
            Previous
          </button>
          <span>Page {previous.length + 1}</span>
          <button
            className="secondary"
            disabled={
              resource.loading ||
              !!resource.error ||
              resource.data?.next_cursor == null
            }
            onClick={() => {
              setPrevious([...previous, cursor]);
              setCursor(resource.data!.next_cursor!);
            }}
          >
            Next
          </button>
        </div>
      </section>
    </>
  );
}

export function Cards({ api }: { api: Api }) {
  const resource = useResource<Card[]>(api, "/cards");
  const action = useAction();
  const trigger = useRef<HTMLElement | null>(null);
  const [pending, setPending] = useState<{ action: Pending; card: Card }>();
  const [success, setSuccess] = useState("");
  return (
    <>
      <ErrorNotice error={action.error} />
      {success && (
        <p role="status" className="notice success">
          {success}
        </p>
      )}
      <ResourceState
        {...resource}
        empty={
          resource.data?.length === 0
            ? "No demo cards for this customer."
            : undefined
        }
      >
        <div className="card-grid">
          {resource.data?.map((card) => (
            <article className="panel bank-card" key={card.id}>
              <div className="card-top">
                <span>BankAI · {label(card.card_type)}</span>
                <span className={`status ${card.status}`}>
                  {label(card.status)}
                </span>
              </div>
              <div className="card-chip" aria-hidden="true" />
              <h2>{card.masked_card_number}</h2>
              <p className="muted">
                Expires {String(card.expiry_month).padStart(2, "0")}/
                {card.expiry_year}
              </p>
              <button
                className="secondary danger"
                disabled={card.status !== "active" || action.busy || !!pending}
                onClick={(event) => {
                  trigger.current = event.currentTarget;
                  void action.run(async () => {
                    setSuccess("");
                    const result = await api<Pending>(
                      `/cards/${card.id}/block`,
                      {},
                    );
                    setPending({ action: result, card });
                  });
                }}
              >
                {action.busy
                  ? "Preparing…"
                  : card.status === "active"
                    ? "Block demo card"
                    : "Card unavailable"}
              </button>
            </article>
          ))}
        </div>
      </ResourceState>
      {pending && (
        <Confirmation
          pending={pending.action}
          returnFocus={trigger.current}
          title="Block this demo card?"
          close={() => setPending(undefined)}
          confirm={async () => {
            await api<Card>(`/cards/${pending.card.id}/block/confirm`, {
              action_id: pending.action.id,
              confirmation: true,
            });
            setSuccess(
              `${pending.card.masked_card_number} was blocked in BankSim.`,
            );
            setPending(undefined);
            resource.reload();
          }}
        >
          <p>
            You are about to block{" "}
            <strong>{pending.card.masked_card_number}</strong>. No change is
            made until you confirm.
          </p>
        </Confirmation>
      )}
    </>
  );
}

export function Loans({ api }: { api: Api }) {
  const resource = useResource<Loan[]>(api, "/loans");
  const action = useAction();
  const trigger = useRef<HTMLElement | null>(null);
  const [emi, setEmi] = useState<EMI>();
  const [eligibility, setEligibility] = useState<Eligibility>();
  const [pending, setPending] = useState<Pending>();
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState({
    loan_type: "personal",
    requested_amount: "",
    annual_interest_rate: "",
    tenure_months: "",
    monthly_income: "",
    monthly_obligations: "0",
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const intent =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ||
      "emi";
    trigger.current = (event.nativeEvent as SubmitEvent)
      .submitter as HTMLElement | null;
    const data = { ...form, tenure_months: Number(form.tenure_months) };
    void action.run(async () => {
      setSuccess("");
      if (intent === "emi")
        setEmi(
          await api<EMI>("/loans/emi", {
            principal: data.requested_amount,
            annual_interest_rate: data.annual_interest_rate,
            tenure_months: data.tenure_months,
          }),
        );
      else if (intent === "eligibility")
        setEligibility(await api<Eligibility>("/loans/eligibility", data));
      else setPending(await api<Pending>("/loans/applications", data));
    });
  }
  return (
    <>
      <section className="panel">
        <p className="eyebrow">SIMULATED LOAN TOOLS</p>
        <h2>Plan a demo loan</h2>
        <p className="muted">
          Use fictional inputs. Eligibility follows transparent demo rules and
          is not credit approval.
        </p>
        <form onSubmit={submit}>
          <fieldset disabled={action.busy || !!pending}>
            <div className="form-grid">
              {Object.entries(form).map(([key, value]) => (
                <label key={key}>
                  {
                    (
                      {
                        loan_type: "Loan type",
                        requested_amount: "Loan amount (INR)",
                        annual_interest_rate: "Annual interest (%)",
                        tenure_months: "Tenure (months)",
                        monthly_income: "Demo monthly income (INR)",
                        monthly_obligations: "Demo monthly obligations (INR)",
                      } as Record<string, string>
                    )[key]
                  }
                  {key === "loan_type" ? (
                    <select
                      value={value}
                      onChange={(event) => {
                        setForm({ ...form, [key]: event.target.value });
                        setEmi(undefined);
                        setEligibility(undefined);
                      }}
                    >
                      <option value="personal">Personal</option>
                      <option value="education">Education</option>
                      <option value="home">Home</option>
                    </select>
                  ) : (
                    <input
                      type="number"
                      required={key !== "monthly_income"}
                      min={
                        key === "annual_interest_rate" ||
                        key === "monthly_obligations"
                          ? "0"
                          : key === "tenure_months"
                            ? "1"
                            : "0.01"
                      }
                      max={
                        key === "annual_interest_rate"
                          ? "100"
                          : key === "tenure_months"
                            ? "600"
                            : "100000000"
                      }
                      step={
                        key === "tenure_months"
                          ? "1"
                          : key === "annual_interest_rate"
                            ? "0.0001"
                            : "0.01"
                      }
                      value={value}
                      onChange={(event) => {
                        setForm({ ...form, [key]: event.target.value });
                        setEmi(undefined);
                        setEligibility(undefined);
                      }}
                    />
                  )}
                </label>
              ))}
            </div>
            <div className="form-actions">
              <button
                className="primary"
                type="submit"
                name="intent"
                value="emi"
              >
                Calculate EMI
              </button>
              <button
                className="secondary"
                type="submit"
                name="intent"
                value="eligibility"
                disabled={!form.monthly_income}
              >
                Check eligibility
              </button>
              <button
                className="secondary"
                type="submit"
                name="intent"
                value="apply"
                disabled={!form.monthly_income}
              >
                Request application
              </button>
            </div>
          </fieldset>
        </form>
        <ErrorNotice error={action.error} />
        {emi && (
          <div className="result-grid" role="status">
            <div>
              <span>Monthly EMI</span>
              <strong>{money(emi.monthly_payment)}</strong>
            </div>
            <div>
              <span>Total payment</span>
              <strong>{money(emi.total_payment)}</strong>
            </div>
            <div>
              <span>Total interest</span>
              <strong>{money(emi.total_interest)}</strong>
            </div>
          </div>
        )}
        {eligibility && (
          <div
            className={`notice ${eligibility.eligible ? "success" : ""}`}
            role="status"
          >
            <strong>
              {eligibility.eligible
                ? "Eligible under demo rules"
                : "Not eligible under demo rules"}
            </strong>
            <p>{eligibility.rule}</p>
            {eligibility.reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
          </div>
        )}
      </section>
      {success && (
        <p role="status" className="notice success">
          {success}
        </p>
      )}
      <section className="panel">
        <h2>Your demo loans</h2>
        <ResourceState
          {...resource}
          empty={
            resource.data?.length === 0
              ? "No simulated loan records yet."
              : undefined
          }
        >
          <div className="record-list">
            {resource.data?.map((loan) => (
              <article key={loan.id}>
                <div>
                  <h3>
                    {label(loan.loan_type)} loan ·{" "}
                    {money(loan.requested_amount)}
                  </h3>
                  <p>
                    {loan.tenure_months} months · {loan.annual_interest_rate}%
                    annual interest
                  </p>
                  <small>{dateTime(loan.created_at)}</small>
                </div>
                <span className={`status ${loan.status}`}>
                  {label(loan.status)}
                </span>
              </article>
            ))}
          </div>
        </ResourceState>
      </section>
      {pending && (
        <Confirmation
          pending={pending}
          returnFocus={trigger.current}
          title="Submit this demo loan application?"
          close={() => setPending(undefined)}
          confirm={async () => {
            await api<Loan>(`/loans/applications/${pending.id}/confirm`, {
              confirmation: true,
            });
            setPending(undefined);
            setSuccess(
              "Your simulated loan application was submitted. This is not credit approval.",
            );
            resource.reload();
          }}
        >
          <p>
            {label(String(pending.payload.loan_type))} loan ·{" "}
            <strong>{money(String(pending.payload.requested_amount))}</strong>
          </p>
          <p>
            {String(pending.payload.tenure_months)} months at{" "}
            {String(pending.payload.annual_interest_rate)}% annual interest.
          </p>
          <p>
            Demo income {money(String(pending.payload.monthly_income))};
            obligations {money(String(pending.payload.monthly_obligations))}.
          </p>
        </Confirmation>
      )}
    </>
  );
}

export function Support({ api }: { api: Api }) {
  const resource = useResource<Ticket[]>(api, "/support/tickets");
  const action = useAction();
  const [success, setSuccess] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    void action.run(async () => {
      setSuccess("");
      await api<Ticket>("/support/tickets", data);
      form.reset();
      setSuccess("Your demo support ticket was created.");
      resource.reload();
    });
  }
  return (
    <>
      <section className="panel">
        <h2>How can we help?</h2>
        <p className="muted">
          Describe a fictional issue. Do not include real card, account or
          identity information.
        </p>
        <form onSubmit={submit}>
          <fieldset disabled={action.busy}>
            <div className="form-grid">
              <label>
                Category
                <select name="category">
                  <option value="account">Account</option>
                  <option value="card">Card</option>
                  <option value="loan">Loan</option>
                  <option value="dispute">Dispute</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label>
                Priority
                <select name="priority">
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
              <label className="full-width">
                Subject
                <input name="subject" required minLength={3} maxLength={200} />
              </label>
              <label className="full-width">
                Description
                <textarea
                  name="description"
                  required
                  minLength={5}
                  maxLength={2000}
                  rows={4}
                />
              </label>
            </div>
            <button className="primary" type="submit">
              {action.busy ? "Creating ticket…" : "Create demo ticket"}
            </button>
          </fieldset>
        </form>
        <ErrorNotice error={action.error} />
        {success && (
          <p role="status" className="notice success">
            {success}
          </p>
        )}
      </section>
      <section className="panel">
        <h2>Support history</h2>
        <ResourceState
          {...resource}
          empty={
            resource.data?.length === 0 ? "No support tickets yet." : undefined
          }
        >
          <div className="record-list">
            {resource.data?.map((ticket) => (
              <article key={ticket.id}>
                <div>
                  <h3>{ticket.subject}</h3>
                  <p>
                    {label(ticket.category)} · {label(ticket.priority)} priority
                  </p>
                  <details>
                    <summary>View ticket details</summary>
                    <p>{ticket.description}</p>
                    <small>Created {dateTime(ticket.created_at)}</small>
                  </details>
                </div>
                <span className={`status ${ticket.status}`}>
                  {label(ticket.status)}
                </span>
              </article>
            ))}
          </div>
        </ResourceState>
      </section>
    </>
  );
}
