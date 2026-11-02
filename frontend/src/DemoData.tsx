import { useState } from "react";
import { type Account, type Api, type Card, type Loan, type TransactionPage, label, money, useResource } from "./api";
import { ResourceState } from "./components";
import { TransactionTable } from "./pages";

export default function DemoData({ api }: { api: Api }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>View my demo banking records</summary>
    {open && <DemoRecords api={api} />}
  </details>;
}

function DemoRecords({ api }: { api: Api }) {
  const accounts = useResource<Account[]>(api, "/accounts");
  const transactions = useResource<TransactionPage>(api, "/transactions?limit=100");
  const cards = useResource<Card[]>(api, "/cards");
  const loans = useResource<Loan[]>(api, "/loans");
  return <div className="demo-records">
    <p className="muted">Current fictional records for this signed-in customer. Confirmed demo actions can change them.</p>
    <button type="button" className="secondary" onClick={() => {
      accounts.reload(); transactions.reload(); cards.reload(); loans.reload();
    }}>Refresh demo records</button>
    <section aria-label="Demo accounts"><h4>Accounts</h4>
      <ResourceState {...accounts}>
        {accounts.data?.length ? <div className="table-scroll"><table><thead><tr><th>Account</th><th>Type</th><th>Balance</th><th>Status</th></tr></thead><tbody>
          {accounts.data.map((item) => <tr key={item.id}><td>{item.account_number}</td><td>{label(item.account_type)}</td><td>{money(item.balance, item.currency)}</td><td>{label(item.status)}</td></tr>)}
        </tbody></table></div> : <p>No demo accounts.</p>}
      </ResourceState>
    </section>
    <section aria-label="Demo transactions"><h4>Transactions</h4>
      <ResourceState {...transactions}>
        {transactions.data && <TransactionTable page={transactions.data} accounts={accounts.data} />}
        {transactions.data?.next_cursor != null && <p className="muted">Showing the first 100 transactions. Open Transactions for more.</p>}
      </ResourceState>
    </section>
    <section aria-label="Demo cards"><h4>Cards</h4>
      <ResourceState {...cards}>
        {cards.data?.length ? <div className="table-scroll"><table><thead><tr><th>Card</th><th>Type</th><th>Linked account</th><th>Status</th></tr></thead><tbody>
          {cards.data.map((item) => <tr key={item.id}><td>{item.masked_card_number}</td><td>{label(item.card_type)}</td><td>{accounts.data?.find((account) => account.id === item.account_id)?.account_number || "None"}</td><td>{label(item.status)}</td></tr>)}
        </tbody></table></div> : <p>No demo cards.</p>}
      </ResourceState>
    </section>
    <section aria-label="Demo loans"><h4>Loans</h4>
      <ResourceState {...loans}>
        {loans.data?.length ? <div className="table-scroll"><table><thead><tr><th>Type</th><th>Requested</th><th>Annual rate</th><th>Term</th><th>Status</th></tr></thead><tbody>
          {loans.data.map((item) => <tr key={item.id}><td>{label(item.loan_type)}</td><td>{money(item.requested_amount)}</td><td>{Number(item.annual_interest_rate)}%</td><td>{item.tenure_months} months</td><td>{label(item.status)}</td></tr>)}
        </tbody></table></div> : <p>No demo loans.</p>}
      </ResourceState>
    </section>
  </div>;
}
