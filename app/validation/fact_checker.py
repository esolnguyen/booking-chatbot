"""Post-generation fact checker — deterministic critic."""

import re


def verify_prices_in_explanation(
    explanation: str,
    actual_flight_price: float,
    actual_hotel_price: float,
    actual_total_price: float | None = None,
) -> tuple[bool, list[str]]:
    """Check if prices mentioned in the explanation match live API data.

    A mentioned price is considered valid if it matches the flight price, the
    hotel per-night rate, or the computed trip total (flight + hotel * nights).
    Passing ``actual_total_price`` avoids false positives on multi-night trips
    where the explanation legitimately cites the full trip cost.
    """
    issues = []

    # Acceptable reference values the explanation may cite.
    valid_prices = [actual_flight_price, actual_hotel_price]
    if actual_total_price is not None:
        valid_prices.append(actual_total_price)
    else:
        # Backwards-compatible default: single-night total.
        valid_prices.append(actual_flight_price + actual_hotel_price)

    # Extract dollar amounts from explanation
    price_matches = re.findall(r"\$[\d,]+(?:\.\d{2})?", explanation)
    mentioned_prices = []
    for p in price_matches:
        val = float(p.replace("$", "").replace(",", ""))
        mentioned_prices.append(val)

    for mp in mentioned_prices:
        if all(abs(mp - vp) > 1.0 for vp in valid_prices):
            issues.append(
                f"Price ${mp} in explanation doesn't match flight "
                f"(${actual_flight_price}), hotel (${actual_hotel_price}/night), "
                f"or trip total (${valid_prices[-1]})"
            )

    return len(issues) == 0, issues


def verify_no_hallucinated_claims(
    explanation: str,
    flight_stops: int,
    hotel_rating: float,
) -> tuple[bool, list[str]]:
    """Verify factual claims in the explanation against ground-truth option data.

    Checks the two claim types the agent is most likely to fabricate: hotel star
    ratings and flight stop counts. Claims are compared against the actual
    inventory values rather than free-text evidence, since those facts originate
    from the inventory API.
    """
    issues = []
    text = explanation.lower()

    # --- Hotel star/rating claims, e.g. "rated 4.5 stars", "4-star hotel" ---
    rating_claims = re.findall(r"(\d+(?:\.\d+)?)[\s-]*star", text)
    rating_claims += re.findall(r"rated\s+(\d+(?:\.\d+)?)", text)
    for raw in rating_claims:
        claimed = float(raw)
        if abs(claimed - hotel_rating) > 0.1:
            issues.append(
                f"Explanation claims {claimed}-star hotel but actual rating "
                f"is {hotel_rating}"
            )

    # --- Flight stop claims ---
    if re.search(r"non[\s-]?stop|direct flight", text):
        if flight_stops != 0:
            issues.append(
                f"Explanation claims a non-stop/direct flight but actual flight "
                f"has {flight_stops} stop(s)"
            )
    for raw in re.findall(r"(\d+)\s+stop", text):
        claimed_stops = int(raw)
        if claimed_stops != flight_stops:
            issues.append(
                f"Explanation claims {claimed_stops} stop(s) but actual flight "
                f"has {flight_stops}"
            )

    return len(issues) == 0, issues
