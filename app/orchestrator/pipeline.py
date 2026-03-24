"""Main orchestration pipeline — bounded step sequence."""

import asyncio
import logging

from app.models.request import BookingRequest
from app.models.option import BookingOption, FlightOption, HotelOption
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


def _find_option_by_id(
    option_id: str,
    flights: list[FlightOption],
    hotels: list[HotelOption],
) -> tuple[FlightOption | None, HotelOption | None]:
    flight = next((f for f in flights if f.id == option_id), None)
    hotel = next((h for h in hotels if h.id == option_id), None)
    return flight, hotel


async def run_pipeline(request: BookingRequest) -> RecommendationResult:
    """Execute the full online recommendation pipeline."""

    # Step 1: Request intake (validation already done by Pydantic)
    logger.info(f"Pipeline started for {request.destination}")

    # Step 2: Live fact fetch (mocked)
    flights = get_available_flights(request.origin, request.destination)
    hotels = get_available_hotels(request.destination)

    if not flights and not hotels:
        return RecommendationResult(
            route="human_review",
            confidence=0.0,
            explanation="No flights or hotels found for this destination.",
            risk_flags=["no_inventory"],
        )

    # Step 3: Knowledge retrieval + reranking
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
    evidence_texts = [doc.page_content for docs in context.values() for doc in docs]

    # Step 4a: Recommendation agent
    rec_result = await run_recommendation_agent(
        context_text=context_text,
        flights=flights,
        hotels=hotels,
        traveler_tier=request.traveler.org_policy_tier,
        trip_purpose=request.trip_purpose,
        preferences=request.preferences,
    )

    if rec_result.get("no_data") or rec_result.get("error"):
        return RecommendationResult(
            route="human_review",
            confidence=0.0,
            explanation=rec_result.get(
                "error", "Agent returned NO_DATA — insufficient context."
            ),
            risk_flags=["no_data_from_agent"],
        )

    # Resolve top picks
    top_flight_id = rec_result.get("top_flight_id", "")
    top_hotel_id = rec_result.get("top_hotel_id", "")
    top_flight = next((f for f in flights if f.id == top_flight_id), None)
    top_hotel = next((h for h in hotels if h.id == top_hotel_id), None)

    if not top_flight or not top_hotel:
        return RecommendationResult(
            route="human_review",
            confidence=0.0,
            explanation="Agent recommended options not found in inventory.",
            risk_flags=["invalid_option_ids"],
        )

    # Step 4b: Verification agent
    ver_result = await run_verification_agent(
        recommendation_output=rec_result,
        context_text=context_text,
        flight=top_flight,
        hotel=top_hotel,
        traveler_tier=request.traveler.org_policy_tier,
    )

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
    )
    claims_ok, claim_issues = verify_no_hallucinated_claims(
        rec_result.get("explanation", ""),
        evidence_texts,
    )

    # Collect all risk flags
    risk_flags = (
        flight_violations
        + hotel_violations
        + price_issues
        + claim_issues
        + ver_result.get("risk_flags", [])
        + ver_result.get("issues_found", [])
    )

    # Build the booking option
    policy_compliant = flight_ok and hotel_ok
    relevance = rec_result.get("relevance_scores", {})
    combo_key = f"{top_flight.id}:{top_hotel.id}"
    relevance_score = relevance.get(combo_key, 0.5)

    num_nights = (request.return_date - request.departure_date).days
    total_price = top_flight.price + (top_hotel.price_per_night * max(num_nights, 1))

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

    route = determine_route(confidence)

    # Step 6: Human-in-the-loop — hold result if approval is needed
    needs_approval = route in ("human_review", "suggest_with_caution")

    result = RecommendationResult(
        route=route,
        confidence=confidence,
        options=[top_option],
        explanation=rec_result.get("explanation", ""),
        evidence_refs=rec_result.get("evidence_refs", []),
        risk_flags=risk_flags,
        verification_notes=ver_result.get("verification_notes", ""),
        approval_required=needs_approval,
    )

    if needs_approval:
        create_pending(result)
        logger.info(
            f"Result held for human review (approval_id={result.approval_id}, route={route})"
        )

    return result
