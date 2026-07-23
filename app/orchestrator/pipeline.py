"""Main orchestration pipeline — bounded step sequence."""

import asyncio
import logging

from langchain.schema import Document

from app.models.request import BookingRequest
from app.models.option import BookingOption
from app.models.response import RecommendationResult
from app.mock.inventory_api import get_available_flights, get_available_hotels
from app.mock.knowledge_base import compute_evidence_freshness
from app.orchestrator.retriever import retrieve_context, format_context_for_prompt
from app.orchestrator.reranker import rerank_documents
from app.orchestrator.router import compute_confidence, determine_route
from app.agents.recommendation import run_recommendation_agent
from app.agents.verification import run_verification_agent
from app.validation.policy_checker import (
    check_flight_policy,
    check_hotel_policy,
    check_inventory,
)
from app.validation.fact_checker import (
    verify_prices_in_explanation,
    verify_no_hallucinated_claims,
)
from app.validation.hard_caps import apply_hard_caps
from app.config import settings
from app.approval_store import create_pending
from app import telemetry

logger = logging.getLogger(__name__)


def _retrieve_and_rank(
    request: BookingRequest,
) -> tuple[dict[str, list[Document]], str, list[str]]:
    """Synchronous retrieval + rerank step (run inside a timeout-bounded thread)."""
    context = retrieve_context(request)

    query_keywords = [
        request.destination,
        request.traveler.org_policy_tier,
        request.trip_purpose,
        str(request.departure_date),
    ]
    for key in context:
        context[key] = rerank_documents(
            context[key],
            query_keywords,
            top_k=settings.rerank_top_k,
        )

    context_text = format_context_for_prompt(context)
    evidence_texts = [
        doc.page_content for docs in context.values() for doc in docs
    ]
    return context, context_text, evidence_texts


def _validate_evidence_refs(
    claimed_refs: list[str],
    context: dict[str, list[Document]],
) -> tuple[list[str], list[str]]:
    """Split agent-cited refs into ones that exist in retrieved context vs. not."""
    valid_ids = {
        str(doc.metadata.get("id"))
        for docs in context.values()
        for doc in docs
        if doc.metadata.get("id") is not None
    }
    grounded = [r for r in claimed_refs if r in valid_ids]
    hallucinated = [r for r in claimed_refs if r not in valid_ids]
    return grounded, hallucinated


def _human_review(explanation: str, *flags: str) -> RecommendationResult:
    """Build a graceful human-review fallback result."""
    return RecommendationResult(
        route="human_review",
        confidence=0.0,
        explanation=explanation,
        risk_flags=list(flags),
    )


async def run_pipeline(request: BookingRequest) -> RecommendationResult:
    """Execute the pipeline with a telemetry run wrapped around it.

    ``run_pipeline`` stays the public entry point (the eval harness patches its
    collaborators — ``retrieve_context`` / ``run_recommendation_agent`` /
    ``run_verification_agent`` on this module — and calls this). The actual
    control flow is a LangGraph ``StateGraph`` (see ``app.orchestrator.graph``),
    which the nodes drive by calling those same module-level names, so the eval
    seams still work. The telemetry run is opened here and always closed, so
    cost/latency are captured on every path — including early returns and retries.
    """
    from app.orchestrator.graph import run_graph  # lazy import breaks the cycle

    telemetry.start_run("pipeline")
    try:
        return await run_graph(request)
    finally:
        telemetry.finish_run()


def score_recommendation(
    request: BookingRequest,
    context: dict[str, list[Document]],
    rec_result: dict,
    ver_result: dict,
    top_flight,
    top_hotel,
) -> dict:
    """Deterministic validation, confidence scoring, hard caps, and routing.

    Pure over its inputs (no I/O). Extracted so the graph's ``score`` node and
    unit tests share one implementation. Returns the computed fields plus the
    hallucinated refs and route the retry loop needs to make its decision.
    """
    num_nights = max((request.return_date - request.departure_date).days, 1)
    total_price = top_flight.price + (top_hotel.price_per_night * num_nights)

    flight_ok, flight_violations = check_flight_policy(
        top_flight, request.traveler.org_policy_tier
    )
    hotel_ok, hotel_violations = check_hotel_policy(
        top_hotel, request.traveler.org_policy_tier
    )
    inventory_ok = check_inventory(top_flight, top_hotel)

    prices_ok, price_issues = verify_prices_in_explanation(
        rec_result.get("explanation", ""),
        top_flight.price,
        top_hotel.price_per_night,
        actual_total_price=total_price,
    )
    claims_ok, claim_issues = verify_no_hallucinated_claims(
        rec_result.get("explanation", ""),
        top_flight.stops,
        top_hotel.rating,
    )

    grounded_refs, hallucinated_refs = _validate_evidence_refs(
        rec_result.get("evidence_refs", []), context
    )

    risk_flags = (
        flight_violations
        + hotel_violations
        + price_issues
        + claim_issues
        + ver_result.get("risk_flags", [])
    )
    if hallucinated_refs:
        risk_flags.append(
            f"hallucinated_evidence_refs: {', '.join(hallucinated_refs)}"
        )

    advisory_notes = list(ver_result.get("issues_found", []))

    policy_compliant = flight_ok and hotel_ok
    relevance = rec_result.get("relevance_scores", {})
    combo_key = f"{top_flight.id}:{top_hotel.id}"
    relevance_score = relevance.get(combo_key, 0.5)

    top_option = BookingOption(
        flight=top_flight,
        hotel=top_hotel,
        total_price=total_price,
        policy_compliant=policy_compliant,
        inventory_available=inventory_ok,
        relevance_score=relevance_score,
    )

    all_docs = [doc for docs in context.values() for doc in docs]
    evidence_ok = 1.0 if ver_result.get("evidence_grounded", False) else 0.5
    freshness_ok = compute_evidence_freshness(all_docs)
    margin = max(0.0, 1.0 - len(risk_flags) * 0.15)
    confidence = compute_confidence(top_option, evidence_ok, freshness_ok, margin)
    confidence = max(
        0.0, min(1.0, confidence + ver_result.get("confidence_adjustment", 0.0))
    )

    # Deterministic hard caps — architectural constraints the LLM can't bypass.
    cap_signals = {
        "inventory_unavailable": not inventory_ok,
        "policy_violation": not policy_compliant,
        "price_mismatch": not prices_ok,
        "fabricated_claims": not claims_ok,
        "hallucinated_evidence": bool(hallucinated_refs),
        # Grounding guardrail: recommended something with no retrieved evidence.
        "no_evidence_retrieved": not all_docs,
    }
    confidence, cap_flags = apply_hard_caps(confidence, cap_signals)
    risk_flags.extend(cap_flags)

    route = determine_route(confidence)

    return {
        "confidence": confidence,
        "route": route,
        "risk_flags": risk_flags,
        "grounded_refs": grounded_refs,
        "hallucinated_refs": hallucinated_refs,
        "advisory_notes": advisory_notes,
        "verification_notes": ver_result.get("verification_notes", ""),
        "explanation": rec_result.get("explanation", ""),
        "top_option": top_option,
    }


def build_result(scored: dict) -> RecommendationResult:
    """Assemble the terminal RecommendationResult and enqueue HITL if needed."""
    route = scored["route"]
    needs_approval = route in ("human_review", "suggest_with_caution")
    result = RecommendationResult(
        route=route,
        confidence=scored["confidence"],
        options=[scored["top_option"]],
        explanation=scored["explanation"],
        evidence_refs=scored["grounded_refs"],
        risk_flags=scored["risk_flags"],
        advisory_notes=scored["advisory_notes"],
        verification_notes=scored["verification_notes"],
        approval_required=needs_approval,
    )
    if needs_approval:
        create_pending(result)
        logger.info(
            f"Result held for human review (approval_id={result.approval_id}, route={route})"
        )
    return result
