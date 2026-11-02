from uuid import uuid4

from app.agents.contracts import Artifact, SpecialistSummary, SupervisorAnswer, ToolFact
from app.agents.supervisor import clarify_unverified_affordability


def test_balance_cannot_be_a_monthly_emi_affordability_verdict():
    account = ToolFact(
        call_id=uuid4(), tool="account_snapshot",
        data={
            "accounts": [{
                "id": str(uuid4()), "account_number": "DEMO-ACCT-0001",
                "account_type": "savings", "currency": "INR", "balance": "11825.25",
                "status": "active",
            }],
            "kyc": {"status": "verified", "notes": None, "last_updated": "2026-10-01T09:00:00Z"},
        },
    )
    artifact = Artifact(
        id=uuid4(), run_id=uuid4(), role="account", revision=1,
        summary=SpecialistSummary(status="answered", answer="Balance verified"),
        facts=[account],
    )
    claimed = SupervisorAnswer(status="answered", answer="You can afford the EMI.")
    question = "See my balance and tell me can I handle the EMI of 2000 per month"

    corrected = clarify_unverified_affordability(question, claimed, [artifact])
    assert corrected.status == "clarification"
    assert "DEMO-ACCT-0001: INR 11,825.25" in corrected.answer
    assert "monthly income and existing monthly obligations" in corrected.answer
    assert "You can afford" not in corrected.answer
    assert clarify_unverified_affordability("What is my balance?", claimed, [artifact]) == claimed

    verified = Artifact(
        id=uuid4(), run_id=uuid4(), role="loan", revision=2,
        summary=SpecialistSummary(status="answered", answer="Eligibility checked"),
        facts=[ToolFact(call_id=uuid4(), tool="loan_eligibility", data={"eligible": True})],
    )
    assert clarify_unverified_affordability(question, claimed, [artifact, verified]) == claimed
