"""Deterministic policy compliance checker."""

from app.models.option import BookingOption, FlightOption, HotelOption
from app.models.request import BookingRequest


# Budget limits by tier
BUDGET_LIMITS = {
    "standard": {
        "hotel_per_night": 500.0,
        "flight_domestic_economy": 2000.0,
        "flight_international_economy": 4000.0,
        "flight_international_business": 6000.0,
    },
    "executive": {
        "hotel_per_night": 800.0,
        "flight_domestic_economy": 3000.0,
        "flight_international_economy": 6000.0,
        "flight_international_business": 8000.0,
    },
    "vip": {
        "hotel_per_night": 1500.0,
        "flight_domestic_economy": 5000.0,
        "flight_international_economy": 8000.0,
        "flight_international_business": 12000.0,
    },
}

PREFERRED_AIRLINES = {"delta", "united", "singapore airlines"}
PREFERRED_HOTELS = {"marriott", "hilton", "hyatt"}

DOMESTIC_DESTINATIONS = {"JFK", "LGA", "EWR", "LAX", "ORD", "SFO", "OAK"}



def check_flight_policy(
    flight: FlightOption, tier: str,
) -> tuple[bool, list[str]]:
    """Check if a flight complies with travel policy."""
    limits = BUDGET_LIMITS.get(tier, BUDGET_LIMITS["standard"])
    violations = []

    is_domestic = flight.destination.upper() in DOMESTIC_DESTINATIONS
    if is_domestic:
        max_price = limits["flight_domestic_economy"]
    elif flight.cabin_class == "business":
        max_price = limits["flight_international_business"]
    else:
        max_price = limits["flight_international_economy"]

    if flight.price > max_price:
        violations.append(
            f"Flight price ${flight.price} exceeds {tier} limit ${max_price}"
        )

    is_preferred = flight.airline.lower() in PREFERRED_AIRLINES
    if not is_preferred:
        violations.append(
            f"Airline '{flight.airline}' is not a preferred vendor "
            f"(requires manager approval)"
        )

    return len(violations) == 0, violations


def check_hotel_policy(
    hotel: HotelOption, tier: str,
) -> tuple[bool, list[str]]:
    """Check if a hotel complies with travel policy."""
    limits = BUDGET_LIMITS.get(tier, BUDGET_LIMITS["standard"])
    violations = []

    if hotel.price_per_night > limits["hotel_per_night"]:
        violations.append(
            f"Hotel rate ${hotel.price_per_night}/night exceeds "
            f"{tier} limit ${limits['hotel_per_night']}/night"
        )

    is_preferred = any(
        brand in hotel.name.lower() for brand in PREFERRED_HOTELS
    )
    if not is_preferred:
        violations.append(
            f"Hotel '{hotel.name}' is not a preferred vendor "
            f"(requires manager approval)"
        )

    return len(violations) == 0, violations


def check_inventory(flight: FlightOption, hotel: HotelOption) -> bool:
    """Check if both flight and hotel have available inventory."""
    return flight.available_seats > 0 and hotel.available_rooms > 0
