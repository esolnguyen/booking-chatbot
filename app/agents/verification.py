"""Verification Agent — challenges and validates recommendations."""

import json
from openai import AzureOpenAI

from app.config import settings
from app.models.option import FlightOption, HotelOption


SYSTEM_PROMPT = """You are a corporate travel verification agent. Your role is to CHALLENGE
and VALIDATE a recommendation made by another agent. You are NOT generating a new
recommendation — you are auditing the existing one.

CHECK THE FOLLOWING:
1. Policy compliance: Does the recommended option respect the traveler's tier budget limits?
2. Factual accuracy: Do the prices and details match the provided inventory data?
3. Evidence grounding: Is the explanation supported by the retrieved policy/destination context?
4. Risk flags: Are there any events, safety concerns, or availability risks?
5. Contradictions: Does the explanation contradict any policy or destination guidance?

Respond in this exact JSON format:
{
    "policy_compliant": true/false,
    "facts_verified": true/false,
    "evidence_grounded": true/false,
    "risk_flags": ["string", ...],
    "issues_found": ["string", ...],
    "confidence_adjustment": 0.0,
    "verification_notes": "string"
}

confidence_adjustment should be between -0.3 and 0.1:
- Positive if recommendation is exceptionally well-grounded
- Negative if issues are found
- 0.0 if recommendation passes all checks
"""


def _build_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


async def run_verification_agent(
    recommendation_output: dict,
    context_text: str,
    flight: FlightOption,
    hotel: HotelOption,
    traveler_tier: str,
) -> dict:
    """Run the verification agent against a recommendation."""
    client = _build_client()

    user_content = (
        f"=== RECOMMENDATION TO VERIFY ===\n"
        f"Top flight: [{flight.id}] {flight.airline} ${flight.price} "
        f"{flight.cabin_class} {flight.stops} stops, "
        f"{flight.available_seats} seats left\n"
        f"Top hotel: [{hotel.id}] {hotel.name} ${hotel.price_per_night}/night "
        f"{hotel.rating} rating, {hotel.available_rooms} rooms left\n"
        f"Explanation: {recommendation_output.get('explanation', 'N/A')}\n"
        f"Evidence refs: {recommendation_output.get('evidence_refs', [])}\n\n"
        f"Traveler tier: {traveler_tier}\n\n"
        f"{context_text}\n\n"
        "Verify this recommendation against policies and facts."
    )

    response = client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "policy_compliant": False,
            "facts_verified": False,
            "evidence_grounded": False,
            "risk_flags": ["verification_parse_error"],
            "issues_found": ["Failed to parse verification output"],
            "confidence_adjustment": -0.2,
            "verification_notes": content,
        }
