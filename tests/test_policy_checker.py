"""Unit tests for deterministic policy compliance checks."""

from app.models.option import FlightOption, HotelOption
from app.validation.policy_checker import (
    check_flight_policy,
    check_hotel_policy,
    check_inventory,
)


def _flight(**kw) -> FlightOption:
    base = dict(
        id="FL1",
        airline="Delta",
        origin="SFO",
        destination="NRT",
        departure_time="08:00",
        arrival_time="14:00",
        price=3000.0,
        stops=0,
        available_seats=5,
        cabin_class="economy",
    )
    base.update(kw)
    return FlightOption(**base)


def _hotel(**kw) -> HotelOption:
    base = dict(
        id="HT1",
        name="Hilton Tokyo",
        city="Tokyo",
        price_per_night=300.0,
        rating=4.5,
        available_rooms=3,
        amenities=["gym"],
    )
    base.update(kw)
    return HotelOption(**base)


# --- Flight policy ---------------------------------------------------------

def test_preferred_economy_within_budget_passes():
    ok, violations = check_flight_policy(_flight(), "standard")
    assert ok is True
    assert violations == []


def test_international_economy_over_budget_flagged():
    ok, violations = check_flight_policy(_flight(price=5000.0), "standard")
    assert ok is False
    assert any("exceeds" in v for v in violations)


def test_non_preferred_airline_flagged():
    ok, violations = check_flight_policy(_flight(airline="SpiritAir"), "standard")
    assert ok is False
    assert any("not a preferred vendor" in v for v in violations)


def test_domestic_route_uses_domestic_limit():
    # SFO->JFK is domestic; $2500 exceeds standard domestic economy limit ($2000)
    ok, violations = check_flight_policy(
        _flight(destination="JFK", price=2500.0), "standard"
    )
    assert ok is False
    assert any("exceeds" in v for v in violations)


def test_business_cabin_uses_business_limit():
    # International business at $7000 is within executive business limit ($8000)
    ok, violations = check_flight_policy(
        _flight(cabin_class="business", price=7000.0), "executive"
    )
    assert ok is True


def test_unknown_tier_falls_back_to_standard():
    ok, _ = check_flight_policy(_flight(price=5000.0), "platinum-unknown")
    # standard international economy limit is $4000 -> over budget
    assert ok is False


# --- Hotel policy ----------------------------------------------------------

def test_preferred_hotel_within_budget_passes():
    ok, violations = check_hotel_policy(_hotel(), "standard")
    assert ok is True
    assert violations == []


def test_hotel_over_nightly_budget_flagged():
    ok, violations = check_hotel_policy(_hotel(price_per_night=900.0), "standard")
    assert ok is False
    assert any("exceeds" in v for v in violations)


def test_non_preferred_hotel_flagged():
    ok, violations = check_hotel_policy(_hotel(name="Joe's Motel"), "standard")
    assert ok is False
    assert any("not a preferred vendor" in v for v in violations)


def test_vip_tier_allows_higher_hotel_rate():
    ok, _ = check_hotel_policy(_hotel(price_per_night=1200.0), "vip")
    assert ok is True


# --- Inventory -------------------------------------------------------------

def test_inventory_available():
    assert check_inventory(_flight(available_seats=1), _hotel(available_rooms=1))


def test_inventory_unavailable_when_no_seats():
    assert not check_inventory(_flight(available_seats=0), _hotel(available_rooms=2))


def test_inventory_unavailable_when_no_rooms():
    assert not check_inventory(_flight(available_seats=2), _hotel(available_rooms=0))
