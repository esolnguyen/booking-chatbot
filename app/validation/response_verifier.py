"""Post-generation response verifier for chat messages."""

import re
from openai import AzureOpenAI
from app.config import settings


VERIFIER_PROMPT = """You are a factual accuracy auditor for a corporate travel assistant.
You will receive:
1. The AI assistant's response to a user
2. The grounding context (policies, inventory, destination info) the assistant was given

Your job is to check if the response contains any:
- Fabricated prices, availability, or ratings not in the context
- Policy claims not supported by the provided policies
- Invented hotel/flight options not in the inventory
- Contradictions with the provided evidence
- Speculative claims presented as facts

Respond in this exact JSON format (no markdown, no code blocks):
{"grounded": true/false, "confidence": 0.0-1.0, "issues": ["string", ...], "safe_to_show": true/false}

Rules:
- "grounded": true if ALL factual claims are supported by the context
- "confidence": how confident you are in the response accuracy (0.0 = no confidence, 1.0 = fully verified)
- "issues": list of specific problems found (empty list if none)
- "safe_to_show": false if there are serious factual errors that could mislead the user
- General advice, opinions, or hedged language ("you might want to...") are OK and should not be flagged
- Only flag concrete factual claims (prices, availability, policy rules, dates) that contradict the context
"""


def verify_response(
    ai_response: str,
    system_context: str,
    user_question: str,
) -> dict:
    """Verify an AI chat response against the grounding context."""
    client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )

    user_content = (
        f"=== USER QUESTION ===\n{user_question}\n\n"
        f"=== AI RESPONSE TO VERIFY ===\n{ai_response}\n\n"
        f"=== GROUNDING CONTEXT ===\n{system_context[:6000]}\n\n"
        "Check the AI response for factual accuracy against the grounding context."
    )

    try:
        response = client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": VERIFIER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        import json
        return json.loads(content)
    except Exception as e:
        return {
            "grounded": False,
            "confidence": 0.0,
            "issues": [f"Verification failed: {str(e)}"],
            "safe_to_show": False,
        }
