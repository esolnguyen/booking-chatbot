"""Mock seed data for the knowledge base and inventory APIs."""

TRAVEL_POLICIES = [
    {
        "id": "POL-001",
        "title": "Standard Travel Budget Policy",
        "content": (
            "Standard-tier employees may spend up to $500 per night on hotels "
            "and up to $2000 on round-trip economy flights for domestic travel. "
            "International flights allow up to $4000 economy or $6000 business "
            "class with VP approval. All bookings must use preferred vendors "
            "when available. Reimbursement requires receipts within 30 days."
        ),
        "policy_type": "budget",
        "tier": "standard",
        "region": "all",
        "year": 2025,
    },
    {
        "id": "POL-002",
        "title": "Executive Travel Budget Policy",
        "content": (
            "Executive-tier employees may spend up to $800 per night on hotels "
            "and up to $6000 on business-class flights for any travel. "
            "First-class is permitted for flights over 8 hours with director "
            "approval. Preferred vendors are recommended but not mandatory."
        ),
        "policy_type": "budget",
        "tier": "executive",
        "region": "all",
        "year": 2026,
    },

    {
        "id": "POL-003",
        "title": "Preferred Vendor Policy",
        "content": (
            "Preferred airline vendors: Delta, United, Singapore Airlines. "
            "Preferred hotel vendors: Marriott, Hilton, Hyatt. Booking with "
            "non-preferred vendors requires manager approval and written "
            "justification. Preferred vendors offer negotiated corporate rates "
            "and priority support."
        ),
        "policy_type": "vendor",
        "tier": "all",
        "region": "all",
        "year": 2024,
    },
    {
        "id": "POL-004",
        "title": "International Travel Safety Policy",
        "content": (
            "Travel to Level 3 or Level 4 risk destinations requires security "
            "team approval and travel insurance. Employees must register with "
            "the corporate travel safety portal before departure. Emergency "
            "contacts must be updated. Travel to active conflict zones is "
            "prohibited without CEO exception."
        ),
        "policy_type": "safety",
        "tier": "all",
        "region": "international",
        "year": 2023,
    },
]

DESTINATION_GUIDES = [
    {
        "id": "DEST-001",
        "city": "Tokyo",
        "country": "Japan",
        "content": (
            "Tokyo is a major business hub with excellent public transit. "
            "Peak travel seasons are cherry blossom (late March-April) and "
            "autumn foliage (November). Hotels in Shinjuku and Marunouchi "
            "are convenient for business travelers. Tipping is not customary."
        ),
        "risk_level": 1,
        "year": 2025,
    },

    {
        "id": "DEST-002",
        "city": "London",
        "country": "UK",
        "content": (
            "London is a global financial center. The City and Canary Wharf "
            "are primary business districts. Hotels near Liverpool Street or "
            "Bank station are ideal. Weather is unpredictable; pack layers. "
            "Oyster card or contactless payment for transit."
        ),
        "risk_level": 1,
        "year": 2022,
    },
    {
        "id": "DEST-003",
        "city": "Singapore",
        "country": "Singapore",
        "content": (
            "Singapore is a key APAC business hub. Marina Bay and Raffles "
            "Place are central business areas. The city is safe and clean "
            "with strict local laws. Changi Airport is a major transit hub. "
            "Hot and humid year-round."
        ),
        "risk_level": 1,
        "year": 2024,
    },
    {
        "id": "DEST-004",
        "city": "Sydney",
        "country": "Australia",
        "content": (
            "Sydney is Australia's largest city and a key business hub in the Asia-Pacific region. "
            "The CBD and North Sydney are the primary business districts. Hotels near Circular Quay "
            "or Darling Harbour are convenient for business travelers. Sydney hosts major finance, "
            "tech, and mining industry headquarters. Weather is mild year-round. "
            "Opal card recommended for public transit."
        ),
        "risk_level": 1,
        "year": 2025,
    },
    {
        "id": "DEST-005",
        "city": "Bangkok",
        "country": "Thailand",
        "content": (
            "Bangkok is a growing business destination in Southeast Asia. "
            "Sukhumvit and Silom are key business areas. Traffic congestion "
            "is severe; use BTS Skytrain. Songkran festival (mid-April) "
            "causes major disruptions and hotel price spikes of 200-300%."
        ),
        "risk_level": 2,
        "year": 2020,
    },
]

EVENT_DATA = [
    {
        "id": "EVT-001",
        "city": "Tokyo",
        "event": "Cherry Blossom Season",
        "dates": "2026-03-25 to 2026-04-15",
        "content": (
            "Cherry blossom season in Tokyo causes hotel demand spikes of "
            "150-200%. Book at least 6 weeks in advance. Prices for hotels "
            "in Shinjuku area increase by $100-200/night during peak bloom."
        ),
        "impact": "high_demand",
        "year": 2026,
    },

    {
        "id": "EVT-002",
        "city": "Bangkok",
        "event": "Songkran Festival",
        "dates": "2026-04-13 to 2026-04-15",
        "content": (
            "Songkran (Thai New Year) causes massive disruptions in Bangkok. "
            "Many businesses close. Hotel prices spike 200-300%. Streets are "
            "blocked for water fights. Avoid scheduling business meetings "
            "during this period."
        ),
        "impact": "high_demand",
        "year": 2026,
    },
    {
        "id": "EVT-003",
        "city": "London",
        "event": "Wimbledon Championships",
        "dates": "2026-06-29 to 2026-07-12",
        "content": (
            "Wimbledon causes moderate hotel demand increase in southwest "
            "London. Central London hotels are less affected. Transport to "
            "Wimbledon area is congested during the tournament."
        ),
        "impact": "moderate_demand",
        "year": 2026,
    },
    {
        "id": "EVT-004",
        "city": "Sydney",
        "event": "Vivid Sydney Festival",
        "dates": "2026-05-22 to 2026-06-13",
        "content": (
            "Vivid Sydney is one of the world's largest festivals of light, music, and ideas, "
            "attracting over 3 million visitors. Hotels in Circular Quay and the CBD see "
            "30-60% price increases. Book at least 4 weeks in advance. "
            "The central business district remains fully operational during the festival."
        ),
        "impact": "moderate_demand",
        "year": 2026,
    },
]

MOCK_FLIGHTS = [
    {
        "id": "FL-001", "airline": "Delta", "origin": "SFO",
        "destination": "NRT", "departure_time": "2026-04-01T10:00",
        "arrival_time": "2026-04-02T14:00", "price": 1800.0,
        "stops": 0, "available_seats": 45, "cabin_class": "economy",
    },

    {
        "id": "FL-002", "airline": "United", "origin": "SFO",
        "destination": "NRT", "departure_time": "2026-04-01T23:00",
        "arrival_time": "2026-04-03T05:00", "price": 1650.0,
        "stops": 1, "available_seats": 12, "cabin_class": "economy",
    },
    {
        "id": "FL-003", "airline": "Singapore Airlines", "origin": "SFO",
        "destination": "NRT", "departure_time": "2026-04-01T01:00",
        "arrival_time": "2026-04-02T06:00", "price": 3200.0,
        "stops": 1, "available_seats": 8, "cabin_class": "business",
    },
    {
        "id": "FL-004", "airline": "Delta", "origin": "SFO",
        "destination": "LHR", "departure_time": "2026-04-01T17:00",
        "arrival_time": "2026-04-02T11:00", "price": 2100.0,
        "stops": 0, "available_seats": 30, "cabin_class": "economy",
    },
    {
        "id": "FL-005", "airline": "United", "origin": "SFO",
        "destination": "LHR", "departure_time": "2026-04-01T20:00",
        "arrival_time": "2026-04-02T14:30", "price": 1950.0,
        "stops": 1, "available_seats": 22, "cabin_class": "economy",
    },
    {
        "id": "FL-006", "airline": "Delta", "origin": "SFO",
        "destination": "SIN", "departure_time": "2026-04-01T11:00",
        "arrival_time": "2026-04-02T19:00", "price": 2400.0,
        "stops": 1, "available_seats": 18, "cabin_class": "economy",
    },
    {
        "id": "FL-007", "airline": "Singapore Airlines", "origin": "SFO",
        "destination": "SIN", "departure_time": "2026-04-01T00:30",
        "arrival_time": "2026-04-02T07:00", "price": 4500.0,
        "stops": 0, "available_seats": 6, "cabin_class": "business",
    },
    {
        "id": "FL-008", "airline": "Delta", "origin": "SFO",
        "destination": "SYD", "departure_time": "2026-04-01T22:00",
        "arrival_time": "2026-04-03T07:30", "price": 1500.0,
        "stops": 0, "available_seats": 30, "cabin_class": "economy",
    },
    {
        "id": "FL-009", "airline": "United", "origin": "SFO",
        "destination": "SYD", "departure_time": "2026-04-01T18:00",
        "arrival_time": "2026-04-03T05:45", "price": 1350.0,
        "stops": 1, "available_seats": 25, "cabin_class": "economy",
    },
    {
        "id": "FL-010", "airline": "BudgetAir", "origin": "SFO",
        "destination": "SYD", "departure_time": "2026-04-01T10:00",
        "arrival_time": "2026-04-03T02:00", "price": 750.0,
        "stops": 2, "available_seats": 5, "cabin_class": "economy",
    },
    {
        "id": "FL-011", "airline": "Delta", "origin": "SFO",
        "destination": "BKK", "departure_time": "2026-04-13T10:00",
        "arrival_time": "2026-04-14T18:00", "price": 2200.0,
        "stops": 1, "available_seats": 0, "cabin_class": "economy",
    },
    {
        "id": "FL-012", "airline": "United", "origin": "SFO",
        "destination": "BKK", "departure_time": "2026-04-13T22:00",
        "arrival_time": "2026-04-15T08:00", "price": 2050.0,
        "stops": 1, "available_seats": 5, "cabin_class": "economy",
    },
]

MOCK_HOTELS = [
    {
        "id": "HT-001", "name": "Marriott Shinjuku", "city": "Tokyo",
        "price_per_night": 350.0, "rating": 4.5,
        "available_rooms": 3, "amenities": ["wifi", "gym", "restaurant"],
    },
    {
        "id": "HT-002", "name": "Hilton Tokyo Bay", "city": "Tokyo",
        "price_per_night": 420.0, "rating": 4.3,
        "available_rooms": 0, "amenities": ["wifi", "pool", "spa"],
    },
    {
        "id": "HT-003", "name": "Budget Inn Tokyo", "city": "Tokyo",
        "price_per_night": 120.0, "rating": 3.2,
        "available_rooms": 15, "amenities": ["wifi"],
    },
    {
        "id": "HT-004", "name": "Hilton London City", "city": "London",
        "price_per_night": 380.0, "rating": 4.4,
        "available_rooms": 8, "amenities": ["wifi", "gym", "restaurant"],
    },
    {
        "id": "HT-005", "name": "Marriott Canary Wharf", "city": "London",
        "price_per_night": 450.0, "rating": 4.6,
        "available_rooms": 5, "amenities": ["wifi", "gym", "pool", "spa"],
    },

    {
        "id": "HT-006", "name": "Marina Bay Sands", "city": "Singapore",
        "price_per_night": 550.0, "rating": 4.8,
        "available_rooms": 2, "amenities": ["wifi", "pool", "spa", "gym", "restaurant"],
    },
    {
        "id": "HT-007", "name": "Hyatt Singapore", "city": "Singapore",
        "price_per_night": 320.0, "rating": 4.3,
        "available_rooms": 10, "amenities": ["wifi", "gym", "restaurant"],
    },
    {
        "id": "HT-008", "name": "Marriott Sydney CBD", "city": "Sydney",
        "price_per_night": 420.0, "rating": 4.4,
        "available_rooms": 8, "amenities": ["wifi", "gym", "restaurant"],
    },
    {
        "id": "HT-009", "name": "Hilton Sydney", "city": "Sydney",
        "price_per_night": 480.0, "rating": 4.5,
        "available_rooms": 5, "amenities": ["wifi", "gym", "pool"],
    },
    {
        "id": "HT-010", "name": "Budget Inn Sydney", "city": "Sydney",
        "price_per_night": 160.0, "rating": 3.1,
        "available_rooms": 18, "amenities": ["wifi"],
    },
    {
        "id": "HT-011", "name": "Marriott Sukhumvit Bangkok", "city": "Bangkok",
        "price_per_night": 200.0, "rating": 4.3,
        "available_rooms": 0, "amenities": ["wifi", "pool", "gym"],
    },
    {
        "id": "HT-012", "name": "Hyatt Regency Bangkok", "city": "Bangkok",
        "price_per_night": 250.0, "rating": 4.5,
        "available_rooms": 2, "amenities": ["wifi", "pool", "spa", "gym"],
    },
]

# Airport code to city mapping
AIRPORT_TO_CITY = {
    "NRT": "Tokyo", "HND": "Tokyo",
    "LHR": "London", "LGW": "London",
    "SIN": "Singapore",
    "SYD": "Sydney", "MEL": "Melbourne",
    "BKK": "Bangkok",
    "SFO": "San Francisco", "OAK": "San Francisco",
}

CITY_TO_AIRPORTS = {}
for code, city in AIRPORT_TO_CITY.items():
    CITY_TO_AIRPORTS.setdefault(city, []).append(code)
