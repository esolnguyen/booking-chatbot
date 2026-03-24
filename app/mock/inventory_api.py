"""Mock live inventory and pricing service."""

from app.mock.seed_data import (
    MOCK_FLIGHTS, MOCK_HOTELS, AIRPORT_TO_CITY, CITY_TO_AIRPORTS,
)
from app.models.option import FlightOption, HotelOption


def _resolve_destination(destination: str) -> tuple[list[str], str]:
    """Resolve destination to airport codes and city name."""
    dest_upper = destination.upper()
    if dest_upper in AIRPORT_TO_CITY:
        city = AIRPORT_TO_CITY[dest_upper]
        return CITY_TO_AIRPORTS.get(city, [dest_upper]), city
    # Try city name match
    for city, codes in CITY_TO_AIRPORTS.items():
        if city.lower() == destination.lower():
            return codes, city
    return [dest_upper], destination


def get_available_flights(
    origin: str, destination: str,
) -> list[FlightOption]:
    """Fetch available flights from mock inventory."""
    dest_codes, _ = _resolve_destination(destination)
    results = []
    for f in MOCK_FLIGHTS:
        if (
            f["origin"].upper() == origin.upper()
            and f["destination"].upper() in [c.upper() for c in dest_codes]
        ):
            results.append(FlightOption(**f))
    return results


def get_available_hotels(destination: str) -> list[HotelOption]:
    """Fetch available hotels from mock inventory."""
    _, city = _resolve_destination(destination)
    results = []
    for h in MOCK_HOTELS:
        if h["city"].lower() == city.lower():
            results.append(HotelOption(**h))
    return results
