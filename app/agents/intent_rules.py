"""Rule-based intent parser — no LLM required for common queries.

Handles:
- IATA codes directly ("SGN", "SYD")
- City names and aliases ("Saigon", "Ho Chi Minh City")
- Fuzzy city matching via difflib
- Relative and absolute dates via dateparser
- Search type from keywords
- Price, stops, time window filters via regex

Returns None when confidence is too low, signalling the caller to fall back to LLM.
"""

import re
from datetime import date
from difflib import get_close_matches
from typing import Optional

import dateparser

from app.mock.seed_data import AIRPORT_TO_CITY, CITY_ALIASES, CITY_TO_AIRPORTS

# ── Lookup helpers ────────────────────────────────────────────────

_ALL_CITY_NAMES = list(CITY_TO_AIRPORTS.keys())  # canonical city names

def _city_to_code(city: str) -> Optional[str]:
    """Return the primary airport code for a city name (canonical or alias)."""
    canonical = CITY_ALIASES.get(city.lower())
    if canonical:
        codes = CITY_TO_AIRPORTS.get(canonical, [])
        return codes[0] if codes else None
    codes = CITY_TO_AIRPORTS.get(city.title(), []) or CITY_TO_AIRPORTS.get(city, [])
    return codes[0] if codes else None


def _resolve_location(text: str) -> tuple[Optional[str], Optional[str]]:
    """Return (iata_code, city_name) for a location string, or (None, None)."""
    upper = text.strip().upper()

    # Direct IATA code
    if upper in AIRPORT_TO_CITY:
        city = AIRPORT_TO_CITY[upper]
        return upper, city

    # Exact city / alias match
    code = _city_to_code(text.strip())
    if code:
        city = AIRPORT_TO_CITY.get(code, text.strip().title())
        return code, city

    # Fuzzy match against canonical city names (cutoff=0.7 to avoid false positives)
    matches = get_close_matches(text.strip().title(), _ALL_CITY_NAMES, n=1, cutoff=0.7)
    if matches:
        codes = CITY_TO_AIRPORTS.get(matches[0], [])
        return (codes[0], matches[0]) if codes else (None, None)

    return None, None


# ── Date helpers ──────────────────────────────────────────────────

_DATEPARSER_SETTINGS = {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False}

def _parse_date(text: str) -> Optional[str]:
    """Parse a date expression and return YYYY-MM-DD or None."""
    parsed = dateparser.parse(text, settings=_DATEPARSER_SETTINGS)
    return parsed.date().isoformat() if parsed else None


# ── Regex patterns ────────────────────────────────────────────────

# Matches: "from X to Y", "X to Y", "X -> Y"
_ROUTE_RE = re.compile(
    r"(?:from\s+)?([A-Za-z\s]+?)\s+(?:to|-+>)\s+([A-Za-z\s]+?)(?:\s|$|,|\.)",
    re.IGNORECASE,
)

# Price: "under $200", "cheaper than 300", "max $150", "budget 500"
_PRICE_RE = re.compile(r"(?:under|cheaper than|max|budget|less than)\s*\$?\s*(\d+)", re.IGNORECASE)

# Stops: "non-stop", "direct", "0 stops", "1 stop"
_STOPS_RE = re.compile(r"(\d+)\s*stop|non.?stop|direct", re.IGNORECASE)

# Time windows: "before 10am", "after 14:00", "arrive by 9"
_ARR_MAX_RE = re.compile(r"arriv(?:e|al).*?(?:before|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", re.IGNORECASE)
_ARR_MIN_RE = re.compile(r"arriv(?:e|al).*?after\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", re.IGNORECASE)
_DEP_MAX_RE = re.compile(r"depart.*?(?:before|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", re.IGNORECASE)
_DEP_MIN_RE = re.compile(r"depart.*?after\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", re.IGNORECASE)

# Date hints in the message (e.g. "on April 10", "next Monday", "tomorrow", "2026-04-15")
_DATE_HINTS = re.compile(
    r"(?:on\s+)?("
    r"\d{4}-\d{2}-\d{2}"                          # ISO date
    r"|(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|tomorrow|today"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"|next\s+week"
    r")",
    re.IGNORECASE,
)

_HOTEL_KW = re.compile(r"\b(?:hotel|stay|room|accommodation|hostel|resort)\b", re.IGNORECASE)
_FLIGHT_KW = re.compile(r"\b(?:flight|fly|airline|ticket|depart)\b", re.IGNORECASE)
# Matches: "hotel in Tokyo", "stay in Ho Chi Minh City", "room in Sydney"
_HOTEL_LOCATION_RE = re.compile(
    r"\b(?:hotel|stay|room|accommodation|hostel|resort)\s+(?:in|at|near)\s+(.+?)(?:\s+(?:for|on|from|between|check)|$|,|\.)",
    re.IGNORECASE,
)
_GENERAL_KW = re.compile(r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay|great|sure|yes|no)\b", re.IGNORECASE)


def _parse_time(raw: str) -> Optional[str]:
    """Convert a time expression to HH:MM (24h)."""
    raw = raw.strip().lower()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
    if not m:
        return None
    h, mins, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if meridiem == "pm" and h != 12:
        h += 12
    elif meridiem == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


# ── Main entry point ──────────────────────────────────────────────

def parse_intent(user_message: str, conversation_history: list[dict]) -> Optional[dict]:
    """
    Attempt to parse intent from the user message using rules only.
    Returns a dict (same shape as the LLM intent) or None if confidence is too low.
    """
    text = user_message.strip()

    # General chit-chat — no search needed
    if _GENERAL_KW.match(text):
        return {"search_type": "general"}

    has_flight = bool(_FLIGHT_KW.search(text))
    has_hotel  = bool(_HOTEL_KW.search(text))

    if has_flight and has_hotel:
        search_type = "both"
    elif has_hotel:
        search_type = "hotel"
    elif has_flight:
        search_type = "flight"
    else:
        # Neither keyword — can't confidently classify, let LLM handle it
        return None

    # Extract route
    origin_code = origin_city = destination_code = destination_city = None
    route_match = _ROUTE_RE.search(text)
    if route_match:
        orig_raw, dest_raw = route_match.group(1).strip(), route_match.group(2).strip()
        origin_code, origin_city       = _resolve_location(orig_raw)
        destination_code, destination_city = _resolve_location(dest_raw)

    # For hotel queries without a "from X to Y" route, try "hotel in City"
    if not destination_code and search_type in ("hotel", "both"):
        hotel_loc_match = _HOTEL_LOCATION_RE.search(text)
        if hotel_loc_match:
            destination_code, destination_city = _resolve_location(hotel_loc_match.group(1).strip())

    # Extract date
    departure_date = None
    date_match = _DATE_HINTS.search(text)
    if date_match:
        departure_date = _parse_date(date_match.group(1))

    # Try to inherit missing fields from conversation history
    if not origin_code or not destination_code or not departure_date:
        for msg in reversed(conversation_history[-6:]):
            if msg.get("role") != "user":
                continue
            prev = msg["content"]
            if not origin_code:
                m = _ROUTE_RE.search(prev)
                if m:
                    origin_code, _ = _resolve_location(m.group(1).strip())
            if not destination_code:
                m = _ROUTE_RE.search(prev)
                if m:
                    destination_code, destination_city = _resolve_location(m.group(2).strip())
            if not departure_date:
                m = _DATE_HINTS.search(prev)
                if m:
                    departure_date = _parse_date(m.group(1))

    # Low-confidence: we have keywords but no usable location or date — let LLM handle it
    if search_type in ("hotel",) and not destination_code and not departure_date:
        return None
    elif search_type not in ("hotel",) and not origin_code and not destination_code and not departure_date:
        return None

    # If the route regex matched but we couldn't resolve one of the locations
    # (e.g. multi-word city like "Ho Chi Minh City" was truncated to "Ho"),
    # fall back to the LLM which handles these cases correctly.
    if route_match and (not origin_code or not destination_code):
        return None

    # Filters
    max_price = None
    price_m = _PRICE_RE.search(text)
    if price_m:
        max_price = float(price_m.group(1))

    stops = None
    stops_m = _STOPS_RE.search(text)
    if stops_m:
        stops = 0 if re.search(r"non.?stop|direct", stops_m.group(0), re.I) else int(stops_m.group(1))

    arr_max = _parse_time(m.group(1)) if (m := _ARR_MAX_RE.search(text)) else None
    arr_min = _parse_time(m.group(1)) if (m := _ARR_MIN_RE.search(text)) else None
    dep_max = _parse_time(m.group(1)) if (m := _DEP_MAX_RE.search(text)) else None
    dep_min = _parse_time(m.group(1)) if (m := _DEP_MIN_RE.search(text)) else None

    return {
        "search_type": search_type,
        "origin": origin_code,
        "destination": destination_code,
        "destination_city": destination_city,
        "departure_date": departure_date,
        "return_date": None,
        "arrival_time_min": arr_min,
        "arrival_time_max": arr_max,
        "departure_time_min": dep_min,
        "departure_time_max": dep_max,
        "max_price": max_price,
        "stops": stops,
        "preferences": [],
    }
