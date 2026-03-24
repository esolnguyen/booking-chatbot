from pydantic import BaseModel


class FlightOption(BaseModel):
    id: str
    airline: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    price: float
    stops: int = 0
    available_seats: int = 0
    cabin_class: str = "economy"


class HotelOption(BaseModel):
    id: str
    name: str
    city: str
    price_per_night: float
    rating: float
    available_rooms: int = 0
    amenities: list[str] = []


class BookingOption(BaseModel):
    flight: FlightOption
    hotel: HotelOption
    total_price: float
    policy_compliant: bool = False
    inventory_available: bool = False
    relevance_score: float = 0.0
