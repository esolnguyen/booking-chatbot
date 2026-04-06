"""Post-generation response verifier -- hybrid deterministic + LLM scoring.

Confidence = 0.6 * deterministic_score + 0.4 * llm_score

The deterministic checker validates prices, airline names, hotel names, and
times against the actual inventory data. The LLM checker catches subtler
issues like contradictions and speculative claims presented as facts.
"""

import json

from app.agents.llm import sync_chat
from app.models.option import FlightOption, HotelOption
from app.validation.fact_checker import run_deterministic_checks

VERIFIER_PROMPT = """You are a factual accuracy auditor for a Booking Recommendation.
You will receive:
1. The AI assistant's response to a user
2. The grounding data (flight/hotel inventory from real crawled sources) the assistant was given

Your job is to check if the response contains any:
- Fabricated prices, availability, or ratings not in the provided data
- Invented flight/hotel options not in the inventory
- Incorrect times, airlines, or hotel names
- Speculative claims presented as facts

Respond in this exact JSON format (no markdown, no code blocks):
{"grounded": true/false, "confidence": 0.0-1.0, "issues": ["string", ...], "safe_to_show": true/false}

Rules:
- "grounded": true if ALL factual claims are supported by the provided data
- "confidence": how confident you are in the response accuracy (0.0 = no confidence, 1.0 = fully verified)
- "issues": list of specific problems found (empty list if none)
- "safe_to_show": false if there are serious factual errors that could mislead the user
- General advice, opinions, or hedged language ("you might want to...") are OK and should not be flagged
- Only flag concrete factual claims (prices, times, availability, names) that contradict the data
- If the assistant says "no data found" and there truly is no data, that is correct and grounded
"""


def _llm_verify(
    ai_response: str,
    grounding_context: str,
    user_question: str,
    provider: str | None = None,
) -> dict:
    """Run LLM-based verification."""
    user_content = (
        f"=== USER QUESTION ===\n{user_question}\n\n"
        f"=== AI RESPONSE TO VERIFY ===\n{ai_response}\n\n"
        f"=== GROUNDING DATA ===\n{grounding_context}\n\n"
        "Check the AI response for factual accuracy against the grounding data."
    )

    try:
        content = sync_chat(
            messages=[
                {"role": "system", "content": VERIFIER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            provider=provider,
            max_tokens=200,
            thinking_budget=0,
            timeout_ms=10_000,
            label="verify",
        ).strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        return {
            "grounded": False,
            "confidence": 0.0,
            "issues": [f"LLM verification failed: {str(e)}"],
            "safe_to_show": False,
        }


def verify_response(
    ai_response: str,
    grounding_context: str,
    user_question: str,
    flights: list[FlightOption] | None = None,
    hotels: list[HotelOption] | None = None,
    provider: str | None = None,
) -> dict:
    """Verify a response using hybrid deterministic + LLM scoring.

    Returns:
        {
            "confidence": float,       # 0.6 * deterministic + 0.4 * llm
            "deterministic_score": float,
            "llm_score": float,
            "issues": [...],
            "safe_to_show": bool,
            "grounded": bool,
        }
    """
    from app.config import settings

    flights = flights or []
    hotels = hotels or []

    # Step 1: Deterministic checks against actual inventory
    det_score, det_issues = run_deterministic_checks(ai_response, flights, hotels)

    # Step 2: LLM verification (optional)
    llm_grounded = False
    llm_safe = True
    llm_issues: list[str] = []
    llm_score = 0.0

    if settings.verification_llm_enabled:
        llm_result = _llm_verify(ai_response, grounding_context, user_question, provider)
        llm_score = llm_result.get("confidence", 0.0)
        llm_issues = llm_result.get("issues", [])
        llm_grounded = llm_result.get("grounded", False)
        llm_safe = llm_result.get("safe_to_show", True)

    # Step 3: Combine scores
    combined = round(0.6 * det_score + 0.4 * llm_score, 3) if settings.verification_llm_enabled else det_score

    # If deterministic checks found hard failures, override safety
    safe_to_show = llm_safe
    if det_score < 0.5:
        safe_to_show = False

    # Merge issues, dedup
    all_issues = det_issues + llm_issues
    seen = set()
    unique_issues = []
    for issue in all_issues:
        if issue not in seen:
            seen.add(issue)
            unique_issues.append(issue)

    return {
        "confidence": combined,
        "deterministic_score": det_score,
        "llm_score": llm_score,
        "issues": unique_issues,
        "safe_to_show": safe_to_show,
        "grounded": (llm_grounded if settings.verification_llm_enabled else True) and det_score >= 0.7,
    }
