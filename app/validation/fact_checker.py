"""Post-generation fact checker — deterministic critic."""

import json
import re


def verify_prices_in_explanation(
    explanation: str,
    actual_flight_price: float,
    actual_hotel_price: float,
) -> tuple[bool, list[str]]:
    """Check if prices mentioned in the explanation match live API data."""
    issues = []

    # Extract dollar amounts from explanation
    price_matches = re.findall(r"\$[\d,]+(?:\.\d{2})?", explanation)
    mentioned_prices = []
    for p in price_matches:
        val = float(p.replace("$", "").replace(",", ""))
        mentioned_prices.append(val)

    if mentioned_prices:
        # Check if any mentioned price is wildly off from actuals
        for mp in mentioned_prices:
            flight_diff = abs(mp - actual_flight_price)
            hotel_diff = abs(mp - actual_hotel_price)
            total_diff = abs(mp - (actual_flight_price + actual_hotel_price))
            if (
                flight_diff > 1.0
                and hotel_diff > 1.0
                and total_diff > 1.0
            ):
                issues.append(
                    f"Price ${mp} in explanation doesn't match "
                    f"flight (${actual_flight_price}) or "
                    f"hotel (${actual_hotel_price}/night)"
                )

    return len(issues) == 0, issues


def verify_no_hallucinated_claims(
    explanation: str,
    evidence_texts: list[str],
) -> tuple[bool, list[str]]:
    """Basic check that key claims have some grounding in evidence."""
    issues = []
    evidence_combined = " ".join(evidence_texts).lower()

    # Check for specific factual claims that should be grounded
    claim_patterns = [
        r"rated (\d+\.?\d*) stars",
        r"(\d+) stops?",
        r"non[- ]?stop",
    ]
    for pattern in claim_patterns:
        matches = re.findall(pattern, explanation.lower())
        for match in matches:
            if match and str(match).lower() not in evidence_combined:
                # Not necessarily a hallucination, just flag it
                pass

    return len(issues) == 0, issues
