from uuid import uuid4

from app.agents.configuration import AgentConfiguration
from app.agents.contracts import Artifact, SpecialistSummary, SupervisorAnswer, ToolFact
from app.evaluation import load_pilot, schedule, score


def test_pilot_manifest_has_all_categories_and_five_controlled_cells():
    cases, checksum = load_pilot()
    assert len(cases) == 7 and len(checksum) == 64
    assert len({case.category for case in cases}) == 7
    first = schedule(cases, seed=42)
    assert first == schedule(cases, seed=42)
    assert len(first) == 35
    assert len({(case.id, config.agent_count, config.architecture, config.prompt_strategy)
                for case, config, _ in first}) == 35


def test_score_uses_verified_receipts_and_reports_missing_evidence():
    case = next(case for case in load_pilot()[0] if case.id == "loan-emi-fixed")
    config = AgentConfiguration(agent_count=2)
    artifact = Artifact(
        id=uuid4(), run_id=uuid4(), role="generalist", revision=1,
        summary=SpecialistSummary(status="answered", answer="EMI ready"),
        facts=[ToolFact(call_id=uuid4(), tool="calculate_emi", data={"monthly_payment": "1066.19"})],
    )
    answer = SupervisorAnswer(status="answered", answer="The EMI is INR 1066.19")
    assert score(case, answer, [artifact], config)["passed"]
    bad = score(case, answer, [], config)
    assert not bad["passed"] and not bad["checks"]["tools"] and not bad["checks"]["facts"]


def test_policy_scoring_requires_sources_when_answered():
    case = next(case for case in load_pilot()[0] if case.category == "policy")
    config = AgentConfiguration()
    fact = ToolFact(call_id=uuid4(), tool="search_policies", data={"status": "found"})
    artifact = Artifact(
        id=uuid4(), run_id=uuid4(), role="support", revision=1,
        summary=SpecialistSummary(status="answered", answer="Policy"), facts=[fact],
    )
    assert not score(case, SupervisorAnswer(status="answered", answer="Policy"), [artifact], config)["passed"]
    assert score(case, SupervisorAnswer(status="answered", answer="Policy", source_ids=["P-DEMO"]), [artifact], config)["passed"]
