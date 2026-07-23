"""LangGraph orchestration for the recommendation pipeline.

The pipeline is modelled as a ``StateGraph`` so the control flow — including the
bounded self-repair loop — is explicit and inspectable rather than buried in
straight-line ``await``s:

    inventory ─▶ retrieve ─▶ recommend ─▶ verify ─▶ score ─┬─(retry)─▶ recommend
                    │            │                          └─(done)──▶ finalize ─▶ END
        (short-circuits to END on: no inventory / timeouts / no-data / bad ids)

The retry loop is the "agent loop" from harness engineering: when the score node
finds a *recoverable* defect (a fabricated citation), it re-asks the
recommendation agent with corrective feedback, up to ``settings.max_agent_iterations``
attempts. It deliberately does NOT retry deterministic hard fails (sold-out
inventory, over-budget, price/claim fabrication) — re-running can't change those
facts, so they escalate immediately.

Nodes call the recommendation/verification agents and ``retrieve_context`` via
the ``pipeline`` module namespace, so the eval harness's ``patch.object`` seams
keep working unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app import telemetry
from app.config import settings
from app.models.request import BookingRequest
from app.models.response import RecommendationResult
from app.orchestrator import pipeline as P

logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    request: BookingRequest
    flights: list[Any]
    hotels: list[Any]
    context: dict[str, list[Any]]
    context_text: str
    rec_result: dict
    top_flight: Any
    top_hotel: Any
    ver_result: dict
    scored: dict
    result: RecommendationResult  # set once terminal — presence means "go to END"
    iteration: int
    retry_feedback: str


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
async def _node_inventory(state: GraphState) -> dict:
    request = state["request"]
    logger.info(f"Pipeline started for {request.destination}")
    with telemetry.span("inventory_fetch"):
        flights = P.get_available_flights(request.origin, request.destination)
        hotels = P.get_available_hotels(request.destination)
    if not flights and not hotels:
        return {
            "flights": flights,
            "hotels": hotels,
            "result": P._human_review(
                "No flights or hotels found for this destination.", "no_inventory"
            ),
        }
    return {"flights": flights, "hotels": hotels}


async def _node_retrieve(state: GraphState) -> dict:
    request = state["request"]
    try:
        async with telemetry.aspan("retrieval"):
            context, context_text, _ = await asyncio.wait_for(
                asyncio.to_thread(P._retrieve_and_rank, request),
                timeout=settings.retrieval_timeout,
            )
    except asyncio.TimeoutError:
        logger.warning("Retrieval timed out after %ss", settings.retrieval_timeout)
        return {
            "result": P._human_review(
                "Knowledge retrieval timed out — routed to human review.",
                "retrieval_timeout",
            )
        }
    return {"context": context, "context_text": context_text}


async def _node_recommend(state: GraphState) -> dict:
    request = state["request"]
    iteration = state.get("iteration", 1)
    context_text = state["context_text"]
    feedback = state.get("retry_feedback")
    # On a retry, prepend corrective feedback so the agent can fix its citations.
    prompt_context = (
        f"{context_text}\n\nCORRECTION (attempt {iteration}): {feedback}"
        if feedback
        else context_text
    )
    try:
        async with telemetry.aspan("recommendation_agent", iteration=iteration):
            rec_result = await asyncio.wait_for(
                P.run_recommendation_agent(
                    context_text=prompt_context,
                    flights=state["flights"],
                    hotels=state["hotels"],
                    traveler_tier=request.traveler.org_policy_tier,
                    trip_purpose=request.trip_purpose,
                    preferences=request.preferences,
                ),
                timeout=settings.agent_timeout,
            )
    except asyncio.TimeoutError:
        logger.warning("Recommendation agent timed out")
        return {
            "result": P._human_review(
                "Recommendation agent timed out — routed to human review.",
                "agent_timeout",
            )
        }

    if rec_result.get("no_data") or rec_result.get("error"):
        return {
            "result": P._human_review(
                rec_result.get("error", "Agent returned NO_DATA — insufficient context."),
                "no_data_from_agent",
            )
        }

    flights, hotels = state["flights"], state["hotels"]
    top_flight = next((f for f in flights if f.id == rec_result.get("top_flight_id")), None)
    top_hotel = next((h for h in hotels if h.id == rec_result.get("top_hotel_id")), None)
    if not top_flight or not top_hotel:
        return {
            "result": P._human_review(
                "Agent recommended options not found in inventory.", "invalid_option_ids"
            )
        }
    return {"rec_result": rec_result, "top_flight": top_flight, "top_hotel": top_hotel}


async def _node_verify(state: GraphState) -> dict:
    request = state["request"]
    try:
        async with telemetry.aspan("verification_agent", iteration=state.get("iteration", 1)):
            ver_result = await asyncio.wait_for(
                P.run_verification_agent(
                    recommendation_output=state["rec_result"],
                    context_text=state["context_text"],
                    flight=state["top_flight"],
                    hotel=state["top_hotel"],
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
    return {"ver_result": ver_result}


async def _node_score(state: GraphState) -> dict:
    with telemetry.span("validation_scoring"):
        scored = P.score_recommendation(
            state["request"],
            state["context"],
            state["rec_result"],
            state["ver_result"],
            state["top_flight"],
            state["top_hotel"],
        )
    return {"scored": scored}


async def _node_prepare_retry(state: GraphState) -> dict:
    scored = state.get("scored", {})
    halluc = scored.get("hallucinated_refs", [])
    feedback = (
        "Your previous recommendation cited evidence refs that were NOT in the "
        f"provided context: {', '.join(halluc)}. Re-answer citing ONLY reference "
        "ids that literally appear in the context blocks above."
    )
    return {
        "iteration": state.get("iteration", 1) + 1,
        "retry_feedback": feedback,
        "result": None,  # clear any partial terminal marker before looping
    }


async def _node_finalize(state: GraphState) -> dict:
    # If an earlier node already produced a terminal result, keep it.
    if state.get("result") is not None:
        return {}
    return {"result": P.build_result(state["scored"])}


# --------------------------------------------------------------------------- #
# Edges
# --------------------------------------------------------------------------- #
def _has_terminal(state: GraphState) -> str:
    return "end" if state.get("result") is not None else "continue"


def _should_retry(state: GraphState) -> bool:
    """Retry only on a recoverable defect, within the iteration budget."""
    if state.get("iteration", 1) >= settings.max_agent_iterations:
        return False
    scored = state.get("scored", {})
    if scored.get("route") == "auto_suggest":
        return False
    # Recoverable = fabricated citation. Hard fails (inventory/policy/price/claim)
    # are objective facts a re-ask can't change, so we don't loop on them.
    return bool(scored.get("hallucinated_refs"))


def _after_score(state: GraphState) -> str:
    return "retry" if _should_retry(state) else "finalize"


def _build_graph():
    g = StateGraph(GraphState)
    g.add_node("inventory", _node_inventory)
    g.add_node("retrieve", _node_retrieve)
    g.add_node("recommend", _node_recommend)
    g.add_node("verify", _node_verify)
    g.add_node("score", _node_score)
    g.add_node("prepare_retry", _node_prepare_retry)
    g.add_node("finalize", _node_finalize)

    g.set_entry_point("inventory")
    g.add_conditional_edges(
        "inventory", _has_terminal, {"end": "finalize", "continue": "retrieve"}
    )
    g.add_conditional_edges(
        "retrieve", _has_terminal, {"end": "finalize", "continue": "recommend"}
    )
    g.add_conditional_edges(
        "recommend", _has_terminal, {"end": "finalize", "continue": "verify"}
    )
    g.add_edge("verify", "score")
    g.add_conditional_edges(
        "score", _after_score, {"retry": "prepare_retry", "finalize": "finalize"}
    )
    g.add_edge("prepare_retry", "recommend")
    g.add_edge("finalize", END)
    return g


# Compile once and reuse.
_COMPILED = _build_graph().compile()


async def run_graph(request: BookingRequest) -> RecommendationResult:
    """Invoke the compiled graph and return the terminal RecommendationResult."""
    final_state = await _COMPILED.ainvoke({"request": request, "iteration": 1})
    result = final_state.get("result")
    if result is None:  # defensive — a well-formed graph always finalizes
        result = P._human_review("Pipeline produced no result.", "no_result")
    return result
