"""RAG retrieval from mock knowledge base."""

from langchain.schema import Document
from app.mock.knowledge_base import search_knowledge_base
from app.models.request import BookingRequest
from app.config import settings


def retrieve_context(request: BookingRequest) -> dict[str, list[Document]]:
    """Retrieve policy, destination, and event context for a booking request."""
    query = (
        f"Travel from {request.origin} to {request.destination} "
        f"for {request.trip_purpose} trip. "
        f"Traveler tier: {request.traveler.org_policy_tier}. "
        f"Dates: {request.departure_date} to {request.return_date}."
    )

    # Retrieve policies relevant to the traveler tier
    policies = search_knowledge_base(
        query=query,
        top_k=settings.retrieval_top_k,
        filter_metadata={"source_type": "policy"},
    )

    # Retrieve destination guidance
    destinations = search_knowledge_base(
        query=f"destination guide {request.destination}",
        top_k=3,
        filter_metadata={"source_type": "destination"},
    )

    # Retrieve event/festival info
    events = search_knowledge_base(
        query=f"events festivals {request.destination} {request.departure_date}",
        top_k=3,
        filter_metadata={"source_type": "event"},
    )

    return {
        "policies": policies,
        "destinations": destinations,
        "events": events,
    }


def format_context_for_prompt(context: dict[str, list[Document]]) -> str:
    """Format retrieved context into a string for LLM prompts."""
    sections = []

    if context["policies"]:
        sections.append("=== TRAVEL POLICIES ===")
        for doc in context["policies"]:
            sections.append(
                f"[{doc.metadata['id']}] {doc.metadata.get('title', '')}\n"
                f"{doc.page_content}"
            )

    if context["destinations"]:
        sections.append("\n=== DESTINATION GUIDANCE ===")
        for doc in context["destinations"]:
            sections.append(
                f"[{doc.metadata['id']}] {doc.metadata.get('city', '')}, "
                f"{doc.metadata.get('country', '')}\n{doc.page_content}"
            )

    if context["events"]:
        sections.append("\n=== EVENTS & FESTIVALS ===")
        for doc in context["events"]:
            sections.append(
                f"[{doc.metadata['id']}] {doc.metadata.get('event', '')} "
                f"({doc.metadata.get('dates', '')})\n{doc.page_content}"
            )

    return "\n\n".join(sections) if sections else "NO_DATA: No relevant context found."
