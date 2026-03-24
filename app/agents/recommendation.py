"""Recommendation Agent — ranks options and generates explanations."""

import json
from openai import AzureOpenAI
from langchain.schema import HumanMessage, SystemMessage

from app.config import settings
from app.models.option import FlightOption, HotelOption


SYSTEM_PROMPT = """You are a corporate travel recommendation agent. Your job is to:
1. Rank the provided booking options based on policy compliance, price, convenience, and traveler preferences.
2. Generate a concise, evidence-backed explanation for your top recommendation.

STRICT RULES:
- ONLY use information from the provided context and inventory data.
- If you cannot make a recommendation from the given data, respond with exactly: NO_DATA
- NEVER guess or fabricate prices, availability, ratings, or policy details.
- Cite evidence references (e.g., [POL-001], [DEST-001]) when making claims.
- Keep explanations under 200 words.

Respond in this exact JSON format:
{
    "ranked_option_ids": ["flight_id:hotel_id", ...],
    "top_flight_id": "string",
    "top_hotel_id": "string",
    "explanation": "string",
    "evidence_refs": ["REF-ID", ...],
    "relevance_scores": {"flight_id:hotel_id": 0.0, ...}
}
"""


def _build_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


def _format_inventory(
    flights: list[FlightOption], hotels: list[HotelOption],
) -> str:
    lines = ["=== AVAILABLE FLIGHTS ==="]
    for f in flights:
        lines.append(
            f"[{f.id}] {f.airline} | {f.origin}->{f.destination} | "
            f"${f.price} | {f.cabin_class} | {f.stops} stops | "
            f"{f.available_seats} seats left | "
            f"{f.departure_time} -> {f.arrival_time}"
        )
    lines.append("\n=== AVAILABLE HOTELS ===")
    for h in hotels:
        lines.append(
            f"[{h.id}] {h.name} | ${h.price_per_night}/night | "
            f"Rating: {h.rating} | {h.available_rooms} rooms left | "
            f"Amenities: {', '.join(h.amenities)}"
        )
    return "\n".join(lines)


async def run_recommendation_agent(
    context_text: str,
    flights: list[FlightOption],
    hotels: list[HotelOption],
    traveler_tier: str,
    trip_purpose: str,
    preferences: list[str],
) -> dict:
    """Run the recommendation agent and return structured output."""
    client = _build_client()

    inventory_text = _format_inventory(flights, hotels)
    user_content = (
        f"Traveler tier: {traveler_tier}\n"
        f"Trip purpose: {trip_purpose}\n"
        f"Preferences: {', '.join(preferences) if preferences else 'None'}\n\n"
        f"{context_text}\n\n{inventory_text}\n\n"
        "Rank the best flight+hotel combinations and explain your top pick."
    )

    response = client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()
    if content == "NO_DATA":
        return {"no_data": True}

    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": "Failed to parse recommendation", "raw": content}
