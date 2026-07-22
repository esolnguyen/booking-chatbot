"""Unit tests for the deterministic post-generation fact checker."""

from app.validation.fact_checker import (
    verify_prices_in_explanation,
    verify_no_hallucinated_claims,
)


# --- Price verification ----------------------------------------------------

def test_exact_flight_and_hotel_prices_pass():
    ok, issues = verify_prices_in_explanation(
        "Flight is $3000 and the hotel is $300/night.",
        actual_flight_price=3000.0,
        actual_hotel_price=300.0,
        actual_total_price=4200.0,
    )
    assert ok is True
    assert issues == []


def test_multi_night_total_does_not_false_positive():
    # 4-night trip: 3000 + 4*300 = 4200; citing the total must be accepted.
    ok, issues = verify_prices_in_explanation(
        "Total estimated trip cost is $4200.",
        actual_flight_price=3000.0,
        actual_hotel_price=300.0,
        actual_total_price=4200.0,
    )
    assert ok is True
    assert issues == []


def test_wrong_price_flagged():
    ok, issues = verify_prices_in_explanation(
        "A bargain at $999.",
        actual_flight_price=3000.0,
        actual_hotel_price=300.0,
        actual_total_price=4200.0,
    )
    assert ok is False
    assert len(issues) == 1


def test_no_prices_mentioned_passes():
    ok, issues = verify_prices_in_explanation(
        "A comfortable non-stop option.",
        actual_flight_price=3000.0,
        actual_hotel_price=300.0,
        actual_total_price=4200.0,
    )
    assert ok is True


def test_backward_compatible_single_night_total():
    # Without actual_total_price, flight+hotel (one night) is accepted.
    ok, _ = verify_prices_in_explanation(
        "Bundle comes to $3300.",
        actual_flight_price=3000.0,
        actual_hotel_price=300.0,
    )
    assert ok is True


# --- Claim grounding (previously a no-op) ----------------------------------

def test_correct_rating_and_stops_pass():
    ok, issues = verify_no_hallucinated_claims(
        "A 4.5-star hotel with a non-stop flight.",
        flight_stops=0,
        hotel_rating=4.5,
    )
    assert ok is True
    assert issues == []


def test_fabricated_star_rating_flagged():
    ok, issues = verify_no_hallucinated_claims(
        "This 5-star hotel is excellent.",
        flight_stops=0,
        hotel_rating=3.0,
    )
    assert ok is False
    assert any("star" in i for i in issues)


def test_false_non_stop_claim_flagged():
    ok, issues = verify_no_hallucinated_claims(
        "Enjoy this non-stop flight.",
        flight_stops=2,
        hotel_rating=4.0,
    )
    assert ok is False
    assert any("non-stop" in i or "stop" in i for i in issues)


def test_wrong_stop_count_flagged():
    ok, issues = verify_no_hallucinated_claims(
        "Just 1 stop on the way.",
        flight_stops=2,
        hotel_rating=4.0,
    )
    assert ok is False


def test_no_factual_claims_passes():
    ok, issues = verify_no_hallucinated_claims(
        "A great value option for your trip.",
        flight_stops=1,
        hotel_rating=4.0,
    )
    assert ok is True
    assert issues == []
