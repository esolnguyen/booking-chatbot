"""Intent extraction -- parses natural language into structured search parameters."""

import json
import logging
from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.agents.llm import sync_chat
from app.agents.intent_rules import parse_intent as rule_parse_intent
from app.config import settings
from app.mock.seed_data import AIRPORT_TO_CITY

logger = logging.getLogger(__name__)


# ── Response schema ───────────────────────────────────────────────
# Passed to Gemini so it returns structured JSON directly —
# no JSON template needed in the prompt.

class IntentResult(BaseModel):
    search_type: str          # "flight" | "hotel" | "both" | "general"
    origin: Optional[str] = None   # IATA code
    destination: Optional[str] = None  # IATA code
    destination_city: Optional[str] = None
    departure_date: Optional[str] = None   # YYYY-MM-DD
    return_date: Optional[str] = None   # YYYY-MM-DD
    arrival_time_min: Optional[str] = None   # HH:MM
    arrival_time_max: Optional[str] = None
    departure_time_min: Optional[str] = None
    departure_time_max: Optional[str] = None
    max_price: Optional[float] = None
    stops: Optional[int] = None
    preferences: list[str] = []


# ── Airport list — only routes we actually crawl ──────────────────

def _build_airport_list() -> str:
    """Only include airports that appear in the configured crawl routes."""
    codes: set[str] = set()
    for route in settings.crawl_route_list:
        parts = route.strip().split("-")
        if len(parts) == 2:
            codes.update(parts)
    lines = []
    for code in sorted(codes):
        city = AIRPORT_TO_CITY.get(code, code)
        lines.append(f"  {code} = {city}")
    print(lines)
    return "\n".join(lines)


# ── Prompt ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a parameter extractor for a travel search app. Today is {today}.

Your ONLY job is to read what the user wrote and pull out search parameters.
Do NOT search for flights or hotels. Do NOT answer questions. Just extract.

Supported airports:
{airport_list}

Rules:
- Map city names / aliases to IATA codes (e.g. "Saigon" -> "SGN", "Tokyo" -> "NRT")
- Convert relative dates to absolute: "tomorrow" -> {today_example}, "next Friday" -> actual date
- Use conversation history AND the last known search context to fill in missing fields from follow-up messages (e.g. "anything cheaper?" inherits the same route, "find me a hotel" inherits destination/dates from a previous flight search)
- search_type: "flight" if asking about flights, "hotel" if hotels, "both" if both, "general" for anything else
- Leave fields as null if not mentioned
- For hotel searches: use "departure_date" for check-in date (NOT "check_in"), and always set "destination_city" to the city name

Return EXACTLY these JSON fields:
{{"search_type": "flight"|"hotel"|"both"|"general", "origin": "IATA"|null, "destination": "IATA"|null, "destination_city": "city name"|null, "departure_date": "YYYY-MM-DD"|null, "return_date": "YYYY-MM-DD"|null, "arrival_time_min": "HH:MM"|null, "arrival_time_max": "HH:MM"|null, "departure_time_min": "HH:MM"|null, "departure_time_max": "HH:MM"|null, "max_price": number|null, "stops": number|null, "preferences": []}}

{last_intent_context}"""


def extract_intent(
    user_message: str,
    conversation_history: list[dict],
    provider: str | None = None,
    last_intent: dict | None = None,
) -> dict:
    """Extract structured search intent from a user message."""
    if settings.intent_rule_based:
        result = rule_parse_intent(user_message, conversation_history)
        if result is not None:
            logger.info("[intent] rule-based parser succeeded")
            return result
        logger.info(
            "[intent] rule-based parser low-confidence, falling back to LLM")

    p = provider or settings.llm_provider

    # Build context from last successful intent so the LLM can inherit
    # parameters (destination, dates, etc.) even if they've scrolled out
    # of the conversation history window.
    if last_intent and last_intent.get("search_type") != "general":
        ctx_parts = [f"Last known search context: {json.dumps({k: v for k, v in last_intent.items() if v is not None})}",
                     "Use these values to fill in any missing fields if the user's new message is a follow-up."]
        last_intent_context = "\n".join(ctx_parts)
    else:
        last_intent_context = ""

    system = SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        today_example=date.today().isoformat(),
        airport_list=_build_airport_list(),
        last_intent_context=last_intent_context,
    )

    messages = [{"role": "system", "content": system}]
    for m in conversation_history[-6:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    schema = IntentResult if p == "google" else None

    try:
        content = sync_chat(
            messages,
            temperature=0.0,
            provider=provider,
            max_tokens=300,
            thinking_budget=0,
            response_schema=schema,
            timeout_ms=10_000,
            label="intent",
        ).strip()

        # Azure / fallback: strip markdown code fences if present
        if schema is None:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

        raw = json.loads(content)
        return _normalize_intent(raw)
    except Exception:
        return {"search_type": "general"}


def _normalize_intent(raw: dict) -> dict:
    """Map common LLM key variants to the canonical field names."""
    # check_in / checkin → departure_date
    if "departure_date" not in raw or raw["departure_date"] is None:
        raw["departure_date"] = raw.pop("check_in", None) or raw.pop("checkin", None)
    # check_out / checkout → return_date
    if "return_date" not in raw or raw["return_date"] is None:
        raw["return_date"] = raw.pop("check_out", None) or raw.pop("checkout", None)
    # Ensure destination_city is set for hotel queries
    if not raw.get("destination_city") and raw.get("destination"):
        code = raw["destination"].upper()
        raw["destination_city"] = AIRPORT_TO_CITY.get(code, raw["destination"])
    return raw
