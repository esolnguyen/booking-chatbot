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
from app.config import settings
from app.approval_store import create_pending

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
    """Execute the full online recommendation pipeline."""

    # Step 1: Request intake (validation already done by Pydantic)
    logger.info(f"Pipeline started for {request.destination}")

    # Step 2: Live fact fetch (mocked)
    flights = get_available_flights(request.origin, request.destination)
    hotels = get_available_hotels(request.destination)

    if not flights and not hotels:
        return _human_review(
            "No flights or hotels found for this destination.", "no_inventory"
        )

    # Step 3: Knowledge retrieval + reranking (timeout-bounded)
    try:
        context, context_text, evidence_texts = await asyncio.wait_for(
            asyncio.to_thread(_retrieve_and_rank, request),
            timeout=settings.retrieval_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Retrieval timed out after %ss", settings.retrieval_timeout)
        return _human_review(
            "Knowledge retrieval timed out — routed to human review.",
            "retrieval_timeout",
        )

    # Step 4a: Recommendation agent (timeout-bounded)
    try:
        rec_result = await asyncio.wait_for(
            run_recommendation_agent(
                context_text=context_text,
                flights=flights,
                hotels=hotels,
                traveler_tier=request.traveler.org_policy_tier,
                trip_purpose=request.trip_purpose,
                preferences=request.preferences,
            ),
            timeout=settings.agent_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Recommendation agent timed out")
        return _human_review(
            "Recommendation agent timed out — routed to human review.",
            "agent_timeout",
        )

    if rec_result.get("no_data") or rec_result.get("error"):
        return _human_review(
            rec_result.get("error", "Agent returned NO_DATA — insufficient context."),
            "no_data_from_agent",
        )

    # Resolve top picks
    top_flight_id = rec_result.get("top_flight_id", "")
    top_hotel_id = rec_result.get("top_hotel_id", "")
    top_flight = next((f for f in flights if f.id == top_flight_id), None)
    top_hotel = next((h for h in hotels if h.id == top_hotel_id), None)

    if not top_flight or not top_hotel:
        return _human_review(
            "Agent recommended options not found in inventory.", "invalid_option_ids"
        )

    # Step 4b: Verification agent (timeout-bounded; failure is non-fatal)
    try:
        ver_result = await asyncio.wait_for(
            run_verification_agent(
                recommendation_output=rec_result,
                context_text=context_text,
                flight=top_flight,
                hotel=top_hotel,
                traveler_tier=request.traveler.org_policy_tier,
            ),
            timeout=settings.verification_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Verification agent timed out — treating as unverified")
        ver_result = {
            "evidence_grounded": False,
            "risk_flags": ["verification_timeout"],
            "issues_found": [],
            "confidence_adjustment": -0.2,
            "verification_notes": "Verification agent timed out.",
        }

    # Trip economics (needed by price check and the booking option)
    num_nights = max((request.return_date - request.departure_date).days, 1)
    total_price = top_flight.price + (top_hotel.price_per_night * num_nights)

    # Step 5: Deterministic validation & routing
    flight_ok, flight_violations = check_flight_policy(
        top_flight,
        request.traveler.org_policy_tier,
    )
    hotel_ok, hotel_violations = check_hotel_policy(
        top_hotel,
        request.traveler.org_policy_tier,
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

    # Validate cited evidence against what was actually retrieved
    grounded_refs, hallucinated_refs = _validate_evidence_refs(
        rec_result.get("evidence_refs", []), context
    )

    # Deterministic risk flags — these drive confidence scoring.
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

    # Soft, advisory notes from the verifier — surfaced but NOT used for scoring.
    advisory_notes = list(ver_result.get("issues_found", []))

    # Build the booking option
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

    # Confidence scoring
    all_docs = [doc for docs in context.values() for doc in docs]
    evidence_ok = 1.0 if ver_result.get("evidence_grounded", False) else 0.5
    freshness_ok = compute_evidence_freshness(all_docs)
    margin = max(0.0, 1.0 - len(risk_flags) * 0.15)
    confidence = compute_confidence(
        top_option,
        evidence_ok,
        freshness_ok,
        margin,
    )
    confidence = max(
        0.0, min(1.0, confidence + ver_result.get("confidence_adjustment", 0.0))
    )

    # Override: if deterministic checks fail hard, force human review
    if not inventory_ok:
        confidence = min(confidence, 0.4)
        risk_flags.append("inventory_unavailable")
    if not policy_compliant:
        confidence = min(confidence, 0.5)
    if not prices_ok:
        confidence = min(confidence, 0.3)
        risk_flags.append("price_mismatch_in_explanation")
    if not claims_ok:
        confidence = min(confidence, 0.4)
        risk_flags.append("fabricated_claims_in_explanation")

    route = determine_route(confidence)

    # Step 6: Human-in-the-loop — hold result if approval is needed
    needs_approval = route in ("human_review", "suggest_with_caution")

    result = RecommendationResult(
        route=route,
        confidence=confidence,
        options=[top_option],
        explanation=rec_result.get("explanation", ""),
        evidence_refs=grounded_refs,
        risk_flags=risk_flags,
        advisory_notes=advisory_notes,
        verification_notes=ver_result.get("verification_notes", ""),
        approval_required=needs_approval,
    )

    if needs_approval:
        create_pending(result)
        logger.info(
            f"Result held for human review (approval_id={result.approval_id}, route={route})"
        )

    return result
