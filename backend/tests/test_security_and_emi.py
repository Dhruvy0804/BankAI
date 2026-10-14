from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_db
from app.core.config import Settings
from app.core.errors import APIError
from app.core.security import decode_token, issue_token
from app.main import create_app
from app.schemas import EMIInput
from app.services.banking import calculate_emi

TEST_SECRET = "test-only-signing-key-never-for-deployment-123456"


def settings():
    return Settings(_env_file=None, app_env="test", app_secret_key=TEST_SECRET)


def test_access_token_roundtrip():
    identifier = uuid4()
    assert decode_token(issue_token(identifier, settings()), settings()) == identifier


@pytest.mark.parametrize(
    "change", ["expired", "audience", "issuer", "missing_exp", "type", "subject"]
)
def test_invalid_token_claims(change):
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=1),
        "iss": "bankai",
        "aud": "bankai-api",
        "token_type": "access",
    }
    if change == "expired":
        claims["exp"] = now - timedelta(minutes=1)
    elif change == "audience":
        claims["aud"] = "other"
    elif change == "issuer":
        claims["iss"] = "other"
    elif change == "missing_exp":
        del claims["exp"]
    elif change == "type":
        claims["token_type"] = "refresh"
    else:
        claims["sub"] = "not-a-uuid"
    with pytest.raises(APIError) as error:
        decode_token(jwt.encode(claims, TEST_SECRET, algorithm="HS256"), settings())
    assert error.value.status == 401


def test_wrong_signature_rejected():
    token = issue_token(uuid4(), settings())
    with pytest.raises(APIError):
        decode_token(
            token,
            Settings(_env_file=None, app_secret_key="another-test-signing-key-long-enough-123456"),
        )


def test_database_error_cannot_be_reported_as_success():
    def failed_database():
        raise SQLAlchemyError("hidden-database-secret")

    application = create_app(settings())
    application.dependency_overrides[get_db] = failed_database
    with TestClient(application) as client:
        response = client.get("/api/v1/accounts")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "hidden-database-secret" not in response.text


def test_missing_secret_disables_login_without_echoing_password():
    with TestClient(create_app(Settings(_env_file=None))) as api:
        response = api.post(
            "/api/v1/auth/login", json={"email": "demo.asha@bankai.example", "password": "secret"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
        assert "secret" not in response.text


@pytest.mark.parametrize("rate,expected", [(0, "1000.00"), (12, "1066.19")])
def test_emi_known_values(rate, expected):
    result = calculate_emi(EMIInput(principal="12000", annual_interest_rate=rate, tenure_months=12))
    assert result.monthly_payment == Decimal(expected)
    if rate == 0:
        assert result.total_interest == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"principal": "-1"},
        {"principal": "NaN"},
        {"annual_interest_rate": "Infinity"},
        {"tenure_months": 0},
    ],
)
def test_invalid_emi_inputs(changes):
    values = {"principal": "1000", "annual_interest_rate": "10", "tenure_months": 12}
    with pytest.raises(ValidationError):
        EMIInput.model_validate(values | changes)
