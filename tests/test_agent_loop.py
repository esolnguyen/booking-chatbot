"""Integration tests for the LangGraph agent loop (app/orchestrator/graph.py).

Offline — the two agents and the retriever are faked (same seams the eval harness
uses). These prove the bounded self-repair loop: a recoverable defect (fabricated
citation) triggers a re-ask, and the loop is capped by ``max_agent_iterations``.
"""

import asyncio
from datetime import date
from unittest.mock import patch

from app import telemetry
from app.config import settings
from app.orchestrator import pipeline
from evals.fakes import make_fake_verification_agent, offline_retrieve_context
from evals.harness import _build_request


def _sydney_request():
    return _build_request(
        {
            "origin": "SFO",
            "destination": "Sydney",
            "departure_date": date(2026, 4, 1),
            "return_date": date(2026, 4, 4),
            "tier": "standard",
            "trip_purpose": "business",
            "preferences": [],
        }
    )


def _rec_payload(ref: str) -> dict:
    return {
        "ranked_option_ids": ["FL-008:HT-008"],
        "top_flight_id": "FL-008",
        "top_hotel_id": "HT-008",
        "explanation": (
            "Delta FL-008 at $1500 non-stop and Marriott Sydney CBD at $420/night, "
            f"total $2760 for 3 nights, fully compliant [{ref}]."
        ),
        "evidence_refs": [ref],
        "relevance_scores": {"FL-008:HT-008": 0.8},
    }


def _run(rec_agent):
    ver = make_fake_verification_agent(None)
    req = _sydney_request()
    telemetry._current_run.set(None)
    with patch.object(pipeline, "retrieve_context", offline_retrieve_context), patch.object(
        pipeline, "run_recommendation_agent", rec_agent
    ), patch.object(pipeline, "run_verification_agent", ver):
        return asyncio.run(pipeline.run_pipeline(req))


def test_agent_loop_self_repairs_a_hallucinated_citation():
    """Bad ref on attempt 1, valid ref on attempt 2 -> route recovers to auto_suggest."""
    calls = {"n": 0}

    async def _self_repairing(**_kwargs):
        calls["n"] += 1
        ref = "POL-999" if calls["n"] == 1 else "POL-001"  # fabricated, then valid
        return _rec_payload(ref)

    result = _run(_self_repairing)

    assert calls["n"] == 2, "agent should have been re-asked exactly once"
    assert result.route == "auto_suggest"
    assert result.evidence_refs == ["POL-001"]
    assert not any("hallucinated_evidence_refs" in f for f in result.risk_flags)


def test_agent_loop_respects_iteration_budget():
    """A permanently-fabricating agent stops after max_agent_iterations and escalates."""

    async def _always_bad(**_kwargs):
        return _rec_payload("POL-999")

    result = _run(_always_bad)

    run = telemetry.get_last_run()
    rec_spans = [s for s in run.spans if s.name == "recommendation_agent"]
    assert len(rec_spans) == settings.max_agent_iterations  # capped (default 2)
    assert result.route == "suggest_with_caution"  # hallucinated_evidence cap = 0.70
    assert any("hallucinated_evidence_refs" in f for f in result.risk_flags)


def test_clean_recommendation_does_not_loop():
    """A first-try grounded answer must not trigger any retry."""
    calls = {"n": 0}

    async def _clean(**_kwargs):
        calls["n"] += 1
        return _rec_payload("POL-001")

    result = _run(_clean)

    assert calls["n"] == 1, "no retry expected for a clean answer"
    assert result.route == "auto_suggest"
