"""Shared booking activity log — writes to chat_log/bookings.json."""

import json
import os
from datetime import datetime

_CHAT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chat_log")
ACTIVITY_FILE = os.path.join(_CHAT_LOG_DIR, "bookings.json")


def _load_events() -> list:
    if not os.path.exists(ACTIVITY_FILE):
        return []
    try:
        with open(ACTIVITY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_events(events: list) -> None:
    os.makedirs(_CHAT_LOG_DIR, exist_ok=True)
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(events[-100:], f, indent=2)


def log_booking(
    traveler_name: str,
    traveler_id: str,
    destination: str,
    flight_id: str | None = None,
    hotel_id: str | None = None,
) -> None:
    """Append flight and/or hotel booking events to the activity log."""
    from app.mock.seed_data import MOCK_FLIGHTS, MOCK_HOTELS

    events = _load_events()
    timestamp = datetime.now().isoformat()

    if flight_id:
        flight = next((f for f in MOCK_FLIGHTS if f["id"] == flight_id), None)
        if flight:
            events.append(
                {
                    "type": "flight",
                    "timestamp": timestamp,
                    "traveler": traveler_name,
                    "traveler_id": traveler_id,
                    "flight_id": flight_id,
                    "airline": flight["airline"],
                    "route": f"{flight['origin']} → {flight['destination']}",
                    "price": flight["price"],
                    "cabin": flight["cabin_class"],
                    "destination": destination,
                }
            )

    if hotel_id:
        hotel = next((h for h in MOCK_HOTELS if h["id"] == hotel_id), None)
        if hotel:
            events.append(
                {
                    "type": "hotel",
                    "timestamp": timestamp,
                    "traveler": traveler_name,
                    "traveler_id": traveler_id,
                    "hotel_id": hotel_id,
                    "hotel_name": hotel["name"],
                    "city": hotel["city"],
                    "price_per_night": hotel["price_per_night"],
                    "rating": hotel["rating"],
                    "destination": destination,
                }
            )

    _save_events(events)


def get_recent_bookings(limit: int = 30) -> list:
    """Return recent booking events, newest first."""
    events = _load_events()
    return list(reversed(events[-limit:]))
