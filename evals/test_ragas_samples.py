"""Unit tests for the RAGAS sample builder (evals/ragas_eval.py).

Pure — no ragas, no network. Exercises the data pipeline that feeds RAGAS: how
scenarios + pipeline outcomes become {question, answer, contexts, ground_truth}
records. The live ``ragas.evaluate`` call itself is out of scope here (it needs
Azure creds + the heavy ragas install).
"""

from app.models.response import RecommendationResult
from evals.harness import ScenarioOutcome
from evals.ragas_eval import build_ragas_samples


def _outcome(scenario_id: str, explanation: str | None) -> ScenarioOutcome:
    result = None
    if explanation is not None:
        result = RecommendationResult(
            route="auto_suggest", confidence=0.9, explanation=explanation
        )
    return ScenarioOutcome(
        id=scenario_id, title=scenario_id, expected={}, result=result
    )


_SCENARIOS = [
    {
        "id": "s1",
        "request": {
            "origin": "SFO",
            "destination": "Sydney",
            "departure_date": "2026-04-01",
            "return_date": "2026-04-04",
            "tier": "standard",
            "trip_purpose": "business",
        },
        "expected": {},
    },
    {
        "id": "s2",
        "request": {
            "origin": "SFO",
            "destination": "Tokyo",
            "departure_date": "2026-04-01",
            "return_date": "2026-04-05",
            "tier": "executive",
            "trip_purpose": "conference",
        },
        "expected": {"reference_answer": "Delta FL-001 with Marriott Shinjuku."},
    },
]


def _fake_provider(req: dict) -> list[str]:
    return [f"ctx for {req['destination']}"]


def test_builds_one_sample_per_answered_scenario():
    outcomes = [_outcome("s1", "Recommend FL-008."), _outcome("s2", "Recommend FL-001.")]
    samples = build_ragas_samples(_SCENARIOS, outcomes, context_provider=_fake_provider)
    assert len(samples) == 2
    assert {s["question"].split("from ")[1].split(" ")[0] for s in samples} == {"SFO"}
    assert samples[0]["answer"] == "Recommend FL-008."
    assert samples[0]["contexts"] == ["ctx for Sydney"]


def test_question_reflects_request_fields():
    samples = build_ragas_samples(
        _SCENARIOS[:1], [_outcome("s1", "x")], context_provider=_fake_provider
    )
    q = samples[0]["question"]
    assert "standard" in q and "business" in q and "Sydney" in q


def test_ground_truth_included_only_when_reference_answer_present():
    outcomes = [_outcome("s1", "a"), _outcome("s2", "b")]
    samples = build_ragas_samples(_SCENARIOS, outcomes, context_provider=_fake_provider)
    by_dest = {s["question"]: s for s in samples}
    s1 = next(s for s in samples if "Sydney" in s["question"])
    s2 = next(s for s in samples if "Tokyo" in s["question"])
    assert "ground_truth" not in s1
    assert s2["ground_truth"] == "Delta FL-001 with Marriott Shinjuku."


def test_escalations_without_an_answer_are_skipped():
    # s2 escalated to human_review with no explanation -> not a RAG sample.
    outcomes = [_outcome("s1", "Recommend FL-008."), _outcome("s2", None)]
    samples = build_ragas_samples(_SCENARIOS, outcomes, context_provider=_fake_provider)
    assert len(samples) == 1
    assert samples[0]["answer"] == "Recommend FL-008."


def test_empty_explanation_is_skipped():
    outcomes = [_outcome("s1", "   ")]  # whitespace-only answer
    samples = build_ragas_samples(_SCENARIOS[:1], outcomes, context_provider=_fake_provider)
    assert samples == []
