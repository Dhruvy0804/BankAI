from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import LoginLimiter
from app.models import AuditLog, Card, Customer, KYCRecord, Loan, PendingAction
from app.seed.demo_data import DEMO_PASSWORD, demo_id
from app.services.banking import BankingService

pytestmark = pytest.mark.integration
KEY = "integration-test-only-signing-secret-at-least-32-bytes"
LOAN = {
    "loan_type": "personal",
    "requested_amount": "12000.00",
    "annual_interest_rate": "12",
    "tenure_months": 12,
    "monthly_income": "50000.00",
    "monthly_obligations": "5000.00",
}


def login(client, name="asha"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"demo.{name}@bankai.example", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_registration_and_own_accounts(api):
    client, _ = api
    auth = login(client)
    me = client.get("/api/v1/auth/me", headers=auth)
    assert me.json()["email"] == "demo.asha@bankai.example"
    assert "password" not in me.text
    accounts = client.get("/api/v1/accounts", headers=auth).json()
    assert len(accounts) == 2
    balance = client.get(f"/api/v1/accounts/{accounts[0]['id']}/balance", headers=auth)
    assert balance.json()["balance"] == accounts[0]["balance"]
    assert client.get("/api/v1/kyc/status", headers=auth).json()["status"] == "verified"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Demo New",
            "email": "new@bankai.example",
            "password": "Synthetic-password-123!",
        },
    )
    assert reg.status_code == 201, reg.text
    assert "password" not in reg.text
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "NEW@bankai.example", "password": "Synthetic-password-123!"},
    ).json()["access_token"]
    assert client.get("/api/v1/accounts", headers={"Authorization": f"Bearer {token}"}).json() == []
    assert (
        client.get("/api/v1/kyc/status", headers={"Authorization": f"Bearer {token}"}).json()[
            "status"
        ]
        == "pending"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/accounts/{}",
        "/accounts/{}/balance",
        "/accounts/{}/transactions",
        "/cards/{}",
        "/transactions/{}",
        "/support/tickets/{}",
    ],
)
def test_cross_customer_access_is_non_disclosing(api, path):
    client, connection = api
    auth = login(client)
    key = (
        "account-3"
        if "accounts" in path
        else "card-3"
        if "cards" in path
        else "transaction-3-0"
        if "transactions" in path
        else "ticket-2"
    )
    denied = client.get("/api/v1" + path.format(demo_id(key)), headers=auth)
    missing = client.get("/api/v1" + path.format(uuid4()), headers=auth)
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["error"]["message"] == missing.json()["error"]["message"]
    with Session(connection) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.outcome == "NOT_FOUND")
            )
            == 2
        )


def test_transaction_filters_and_pagination(api):
    client, _ = api
    auth = login(client)
    page = client.get("/api/v1/transactions?limit=2&transaction_type=debit", headers=auth).json()
    second = client.get(
        f"/api/v1/transactions?limit=2&transaction_type=debit&cursor={page['next_cursor']}",
        headers=auth,
    ).json()
    assert len(page["items"]) == len(second["items"]) == 2
    assert not ({i["id"] for i in page["items"]} & {i["id"] for i in second["items"]})
    assert {i["transaction_type"] for i in page["items"]} == {"debit"}
    response = client.get(
        "/api/v1/transactions?date_from=2026-10-02&date_to=2026-10-02&min_amount=100&max_amount=200",
        headers=auth,
    )
    assert len(response.json()["items"]) == 2
    assert (
        client.get(
            f"/api/v1/transactions?account_id={demo_id('account-3')}", headers=auth
        ).status_code
        == 404
    )
    assert client.get("/api/v1/transactions?limit=101", headers=auth).status_code == 422
    assert (
        client.get("/api/v1/transactions?customer_id=someone-else", headers=auth).status_code == 422
    )


def test_confirmed_card_block_and_replay(api):
    client, connection = api
    auth = login(client)
    path = f"/api/v1/cards/{demo_id('card-1')}/block"
    pending = client.post(path, headers=auth)
    assert pending.status_code == 202
    action = pending.json()["id"]
    assert (
        client.get(f"/api/v1/cards/{demo_id('card-1')}", headers=auth).json()["status"] == "active"
    )
    assert (
        client.post(path + "/confirm", headers=auth, json={"action_id": action}).status_code == 422
    )
    assert (
        client.post(
            path + "/confirm", headers=auth, json={"action_id": action, "confirmation": "yes"}
        ).status_code
        == 422
    )
    confirmed = client.post(
        path + "/confirm", headers=auth, json={"action_id": action, "confirmation": True}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "blocked"
    assert (
        client.post(
            path + "/confirm", headers=auth, json={"action_id": action, "confirmation": True}
        ).status_code
        == 409
    )
    with Session(connection) as db:
        assert db.get(PendingAction, UUID(action)).status == "executed"
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "confirm_block_card")
            )
            == 1
        )


def test_expired_wrong_user_and_wrong_card_confirmations(api):
    client, connection = api
    auth = login(client)
    other = login(client, "ravi")
    path = f"/api/v1/cards/{demo_id('card-1')}/block"
    action = client.post(path, headers=auth).json()["id"]
    assert (
        client.post(
            path + "/confirm", headers=other, json={"action_id": action, "confirmation": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/cards/{demo_id('card-2')}/block/confirm",
            headers=auth,
            json={"action_id": action, "confirmation": True},
        ).status_code
        == 409
    )
    with Session(connection) as db, db.begin():
        pending = db.get(PendingAction, UUID(action))
        pending.created_at = datetime.now(UTC) - timedelta(minutes=10)
        pending.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    response = client.post(
        path + "/confirm", headers=auth, json={"action_id": action, "confirmation": True}
    )
    assert response.json()["error"]["code"] == "ACTION_EXPIRED"
    assert (
        client.get(f"/api/v1/cards/{demo_id('card-1')}", headers=auth).json()["status"] == "active"
    )


def test_card_state_revalidated(api):
    client, connection = api
    auth = login(client)
    path = f"/api/v1/cards/{demo_id('card-1')}/block"
    action = client.post(path, headers=auth).json()["id"]
    with Session(connection) as db, db.begin():
        db.get(Card, demo_id("card-1")).status = "expired"
    assert (
        client.post(
            path + "/confirm", headers=auth, json={"action_id": action, "confirmation": True}
        ).status_code
        == 409
    )


def test_loan_is_bound_to_confirmed_payload_and_not_duplicated(api):
    client, connection = api
    auth = login(client)
    assert (
        client.post("/api/v1/loans/eligibility", headers=auth, json=LOAN).json()["eligible"] is True
    )
    pending = client.post("/api/v1/loans/applications", headers=auth, json=LOAN)
    assert pending.status_code == 202, pending.text
    path = f"/api/v1/loans/applications/{pending.json()['id']}/confirm"
    assert len(client.get("/api/v1/loans", headers=auth).json()) == 1
    assert (
        client.post(
            path, headers=auth, json={"confirmation": True, "requested_amount": "999"}
        ).status_code
        == 422
    )
    result = client.post(path, headers=auth, json={"confirmation": True})
    assert result.status_code == 201, result.text
    assert result.json()["requested_amount"] == "12000.00"
    assert result.json()["status"] == "submitted"
    assert client.post(path, headers=auth, json={"confirmation": True}).status_code == 409
    with Session(connection) as db:
        assert db.scalar(select(func.count()).select_from(Loan)) == 4


def test_loan_eligibility_revalidated(api):
    client, connection = api
    auth = login(client)
    pending = client.post("/api/v1/loans/applications", headers=auth, json=LOAN).json()
    with Session(connection) as db, db.begin():
        db.get(KYCRecord, demo_id("kyc-1")).status = "rejected"
    result = client.post(
        f"/api/v1/loans/applications/{pending['id']}/confirm",
        headers=auth,
        json={"confirmation": True},
    )
    assert result.status_code == 409
    assert len(client.get("/api/v1/loans", headers=auth).json()) == 1


def test_ticket_creation_and_identity_cannot_be_overridden(api):
    client, _ = api
    auth = login(client)
    data = {
        "category": "dispute",
        "subject": "Demo dispute",
        "description": "Please review this fictional charge.",
    }
    assert (
        client.post(
            "/api/v1/support/tickets",
            headers=auth,
            json=data | {"customer_id": str(demo_id("customer-2"))},
        ).status_code
        == 422
    )
    result = client.post("/api/v1/support/tickets", headers=auth, json=data)
    assert result.status_code == 201
    assert (
        client.get(f"/api/v1/support/tickets/{result.json()['id']}", headers=auth).json()["subject"]
        == data["subject"]
    )


def test_bad_login_inactive_customer_and_throttling(api):
    client, connection = api
    bad = client.post(
        "/api/v1/auth/login", json={"email": "demo.asha@bankai.example", "password": "wrong"}
    )
    assert bad.status_code == 401
    auth = login(client)
    with Session(connection) as db, db.begin():
        db.get(Customer, demo_id("customer-1")).is_active = False
    assert client.get("/api/v1/accounts", headers=auth).status_code == 401
    assert client.get("/api/v1/accounts").status_code == 401
    assert (
        client.get("/api/v1/accounts", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    client.app.state.login_limiter = LoginLimiter(attempts=1)
    data = {"email": "demo.asha@bankai.example", "password": "wrong"}
    assert client.post("/api/v1/auth/login", json=data).status_code == 401
    assert client.post("/api/v1/auth/login", json=data).status_code == 429


def test_sensitive_input_not_echoed_in_errors_or_audit(api):
    client, connection = api
    response = client.post(
        "/api/v1/auth/login", json={"email": "invalid", "password": "never-echo-this-value"}
    )
    assert response.status_code == 422
    assert "never-echo" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    auth = login(client)
    client.get("/api/v1/accounts", headers=auth)
    with Session(connection) as db:
        logs = db.scalars(select(AuditLog)).all()
        assert all(
            DEMO_PASSWORD not in str(row.__dict__)
            and auth["Authorization"] not in str(row.__dict__)
            for row in logs
        )


def test_action_kind_and_cross_user_loan_confirmation(api):
    client, _ = api
    auth = login(client)
    other = login(client, "ravi")
    pending_card = client.post(f"/api/v1/cards/{demo_id('card-1')}/block", headers=auth).json()
    assert (
        client.post(
            f"/api/v1/loans/applications/{pending_card['id']}/confirm",
            headers=auth,
            json={"confirmation": True},
        ).status_code
        == 409
    )
    loan = client.post("/api/v1/loans/applications", headers=auth, json=LOAN).json()
    assert (
        client.post(
            f"/api/v1/loans/applications/{loan['id']}/confirm",
            headers=other,
            json={"confirmation": True},
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/cards/{demo_id('card-3')}/block", headers=auth).status_code == 404
    response = client.post("/api/v1/loans/eligibility", headers=other, json=LOAN)
    assert response.json()["eligible"] is False


def test_authenticated_browser_preflight(api):
    client, _ = api
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_failed_sensitive_write_rolls_back_action_and_card(api, monkeypatch):
    client, connection = api
    auth = login(client)
    path = f"/api/v1/cards/{demo_id('card-1')}/block"
    action = client.post(path, headers=auth).json()["id"]
    original = BankingService.audit

    def fail_commit_audit(self, operation, resource_type, resource_id=None):
        if operation == "confirm_block_card":
            raise SQLAlchemyError("synthetic audit storage failure")
        return original(self, operation, resource_type, resource_id)

    monkeypatch.setattr(BankingService, "audit", fail_commit_audit)
    result = client.post(
        path + "/confirm", headers=auth, json={"action_id": action, "confirmation": True}
    )
    assert result.status_code == 503
    with Session(connection) as db:
        assert db.get(Card, demo_id("card-1")).status == "active"
        assert db.get(PendingAction, UUID(action)).status == "pending"
