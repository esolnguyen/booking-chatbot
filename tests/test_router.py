"""Unit tests for confidence scoring and routing thresholds."""

from app.models.option import FlightOption, HotelOption, BookingOption
from app.orchestrator.router import compute_confidence, determine_route
from app.config import settings


def _option(policy_compliant: bool, inventory_available: bool) -> BookingOption:
    flight = FlightOption(
        id="FL1", airline="Delta", origin="SFO", destination="NRT",
        departure_time="08:00", arrival_time="14:00", price=3000.0,
        stops=0, available_seats=5,
    )
    hotel = HotelOption(
        id="HT1", name="Hilton", city="Tokyo", price_per_night=300.0,
        rating=4.5, available_rooms=3,
    )
    return BookingOption(
        flight=flight, hotel=hotel, total_price=3300.0,
        policy_compliant=policy_compliant, inventory_available=inventory_available,
    )


def test_perfect_inputs_score_one():
    score = compute_confidence(_option(True, True), 1.0, 1.0, 1.0)
    assert score == 1.0


def test_all_zero_inputs_score_zero():
    score = compute_confidence(_option(False, False), 0.0, 0.0, 0.0)
    assert score == 0.0


def test_weights_sum_correctly():
    # Only policy (0.35) + inventory (0.25) contribute -> 0.60
    score = compute_confidence(_option(True, True), 0.0, 0.0, 0.0)
    assert score == 0.6


def test_route_auto_suggest_at_threshold():
    assert determine_route(settings.auto_suggest_threshold) == "auto_suggest"
    assert determine_route(0.95) == "auto_suggest"


def test_route_human_review_below_low_threshold():
    assert determine_route(settings.human_review_threshold - 0.01) == "human_review"
    assert determine_route(0.0) == "human_review"


def test_route_caution_in_middle_band():
    assert determine_route(settings.human_review_threshold) == "suggest_with_caution"
    assert determine_route(0.70) == "suggest_with_caution"
    assert determine_route(settings.auto_suggest_threshold - 0.01) == "suggest_with_caution"
