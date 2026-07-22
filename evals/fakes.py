"""Deterministic stand-ins for the LLM agents and vector store (offline mode).

These let the eval harness exercise the *real* pipeline — router, policy and
fact checkers, hard caps, freshness — without any network calls or Azure spend.
Only three names in ``app.orchestrator.pipeline`` are patched:

    retrieve_context, run_recommendation_agent, run_verification_agent

Everything else (inventory lookup, reranking, confidence scoring, routing,
approval store) runs exactly as in production.
"""

from __future__ import annotations

from langchain.schema import Document

from app.mock.inventory_api import _resolve_destination
from app.mock.knowledge_base import _build_documents

# Build the document corpus once (pure, no embeddings / no network).
_ALL_DOCS: list[Document] = _build_documents()


def offline_retrieve_context(request) -> dict[str, list[Document]]:
    """Deterministic replacement for ``retriever.retrieve_context``.

    Returns the same shape the real retriever does (policies / destinations /
    events), built straight from seed data so the set of available evidence is
    fixed and inspectable. The real per-category reranker still runs downstream
    in the pipeline, so freshness and grounded-ref validation match production
    behaviour for this candidate set.
    """
    _, city = _resolve_destination(request.destination)
    city_l = city.lower()

    policies = [d for d in _ALL_DOCS if d.metadata["source_type"] == "policy"]
    destinations = [
        d
        for d in _ALL_DOCS
        if d.metadata["source_type"] == "destination"
        and d.metadata.get("city", "").lower() == city_l
    ]
    events = [
        d
        for d in _ALL_DOCS
        if d.metadata["source_type"] == "event"
        and d.metadata.get("city", "").lower() == city_l
    ]
    return {"policies": policies, "destinations": destinations, "events": events}


def make_fake_recommendation_agent(agent_pick: dict):
    """Return an async fn matching ``run_recommendation_agent``'s contract.

    ``agent_pick`` mirrors the structured output the real agent would emit. A
    ``relevance_scores`` map is synthesised for the chosen combo if absent.
    """
    flight_id = agent_pick.get("top_flight_id", "")
    hotel_id = agent_pick.get("top_hotel_id", "")
    combo = f"{flight_id}:{hotel_id}"
    result = {
        "ranked_option_ids": agent_pick.get("ranked_option_ids", [combo]),
        "top_flight_id": flight_id,
        "top_hotel_id": hotel_id,
        "explanation": agent_pick.get("explanation", ""),
        "evidence_refs": agent_pick.get("evidence_refs", []),
        "relevance_scores": agent_pick.get("relevance_scores", {combo: 0.8}),
    }

    async def _fake(**_kwargs) -> dict:
        return dict(result)

    return _fake


# A verifier that passes everything cleanly — the default when a scenario does
# not specify its own ``verifier`` block.
_CLEAN_VERIFIER = {
    "policy_compliant": True,
    "facts_verified": True,
    "evidence_grounded": True,
    "risk_flags": [],
    "issues_found": [],
    "confidence_adjustment": 0.0,
    "verification_notes": "Clean pass (offline fake).",
}


def make_fake_verification_agent(verifier: dict | None):
    """Return an async fn matching ``run_verification_agent``'s contract."""
    payload = {**_CLEAN_VERIFIER, **(verifier or {})}

    async def _fake(**_kwargs) -> dict:
        return dict(payload)

    return _fake
