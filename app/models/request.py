from pydantic import BaseModel
from datetime import date


class TravelerProfile(BaseModel):
    employee_id: str
    name: str
    department: str
    org_policy_tier: str = "standard"  # standard, executive, vip


class BookingRequest(BaseModel):
    traveler: TravelerProfile
    origin: str
    destination: str
    departure_date: date
    return_date: date
    trip_purpose: str = "business"  # business, conference, training
    preferences: list[str] = []  # e.g. ["window_seat", "non_stop", "hotel_gym"]
    max_budget: float | None = None
