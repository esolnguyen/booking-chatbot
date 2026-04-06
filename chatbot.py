from app.validation.response_verifier import verify_response
from app.crawler.scraper import get_hotel_search_urls, get_flight_search_urls
from app.mock.inventory_api import (
    get_available_flights,
    get_available_hotels,
    get_available_routes,
    get_available_cities,
)
from app.config import settings
from app.agents.intent import extract_intent
from app.agents.llm import sync_chat
from dotenv import load_dotenv
from datetime import datetime
import logging
import streamlit as st
import os
os.environ["ANONYMIZED_TELEMETRY"] = "false"


load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
# Keep noisy libraries at INFO, except httpx — DEBUG shows retry status codes
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("google_genai").setLevel(logging.DEBUG)

# -- Logging --
LOG_DIR = os.path.join(os.path.dirname(__file__), "chat_log")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d") + ".txt")


def _log(question: str, answer: str, verification: dict | None = None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"[{ts}]", f"USER: {question}", f"AGENT: {answer}"]
    if verification:
        lines.append(f"CONFIDENCE: {verification.get('confidence', 'N/A')}")
        lines.append(
            f"DETERMINISTIC: {verification.get('deterministic_score', 'N/A')}")
        lines.append(f"LLM_SCORE: {verification.get('llm_score', 'N/A')}")
        issues = verification.get("issues", [])
        lines.append(f"ISSUES: {', '.join(issues) if issues else 'None'}")
        lines.append(
            f"SAFE_TO_SHOW: {verification.get('safe_to_show', 'N/A')}")
        lines.append(f"GROUNDED: {verification.get('grounded', 'N/A')}")
    lines.append("-" * 80)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -- Streamlit layout --
st.set_page_config(page_title="Booking Recommendation", layout="wide")
st.title("Booking Recommendation")

with st.sidebar:
    st.header("Settings")
    provider = st.selectbox(
        "LLM Provider",
        ["azure", "google"],
        index=0 if settings.llm_provider == "azure" else 1,
        help="azure = Azure OpenAI  |  google = Gemini 2.0 Flash",
    )
    verify_enabled = st.toggle("Enable response verification", value=True)

    st.divider()
    st.subheader("Crawled Data Status")
    routes = get_available_routes()
    cities = get_available_cities()
    if routes:
        route_set = sorted(
            {f"{r['origin']}->{r['destination']}" for r in routes})
        st.text(f"Flight routes: {len(route_set)}")
        for r in route_set:
            st.text(f"  {r}")
    else:
        st.text("No flight data. Run the crawler first.")
    if cities:
        st.text(f"Hotel cities: {', '.join(cities)}")
    else:
        st.text("No hotel data.")


# -- Chat state --
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_intent" not in st.session_state:
    st.session_state.last_intent = None

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "verification" in msg:
            v = msg["verification"]
            conf = v.get("confidence", 0)
            if conf >= 0.85:
                color = "green"
            elif conf >= 0.60:
                color = "orange"
            else:
                color = "red"
            det = v.get("deterministic_score", 0)
            llm = v.get("llm_score", 0)
            st.markdown(
                f"---\n**Confidence:** :{color}[{conf:.0%}]"
                f" &nbsp;(facts: {det:.0%} | LLM: {llm:.0%})"
            )
            if v.get("issues"):
                st.warning("Issues: " + ", ".join(v["issues"]))


# -- Helpers --

def _format_flights(flights) -> str:
    if not flights:
        return "No flights found."
    lines = ["=== FLIGHTS ==="]
    for f in flights:
        lines.append(
            f"[{f.id}] {f.airline} | {f.origin}->{f.destination} | "
            f"${f.price} | {f.cabin_class} | {f.stops} stops | "
            f"{f.available_seats} seats | "
            f"Departs: {f.departure_time} | Arrives: {f.arrival_time} | "
            f"BookURL: {f.booking_url}"
        )
    return "\n".join(lines)


def _format_hotels(hotels) -> str:
    if not hotels:
        return "No hotels found."
    lines = ["=== HOTELS ==="]
    for h in hotels:
        lines.append(
            f"[{h.id}] {h.name} | ${h.price_per_night}/night | "
            f"Rating: {h.rating} | {h.available_rooms} rooms | "
            f"Amenities: {', '.join(h.amenities) if h.amenities else 'N/A'} | "
            f"BookURL: {h.booking_url}"
        )
    return "\n".join(lines)


def _build_alternatives_text() -> str:
    """Build a summary of what data IS available for 'similar recommendations'."""
    routes = get_available_routes()
    cities = get_available_cities()
    lines = ["=== AVAILABLE DATA ==="]
    if routes:
        route_dates: dict[str, list[str]] = {}
        for r in routes:
            key = f"{r['origin']}->{r['destination']}"
            route_dates.setdefault(key, []).append(r["date"])
        for route, dates in sorted(route_dates.items()):
            lines.append(f"Flights {route}: dates {', '.join(sorted(dates))}")
    if cities:
        lines.append(f"Hotels available in: {', '.join(cities)}")
    if not routes and not cities:
        lines.append(
            "No crawled data available. The crawler may not have run yet.")
    return "\n".join(lines)


def _filter_flights_by_time(flights, intent: dict):
    """Filter flights by arrival/departure time preferences from intent."""
    filtered = list(flights)
    arr_min = intent.get("arrival_time_min")
    arr_max = intent.get("arrival_time_max")
    dep_min = intent.get("departure_time_min")
    dep_max = intent.get("departure_time_max")

    def _extract_time(time_str: str) -> str | None:
        if not time_str:
            return None
        # Handle ISO datetime (2026-04-10T08:30) or plain time (08:30)
        if "T" in time_str:
            time_str = time_str.split("T")[1]
        # Take just HH:MM
        return time_str[:5] if len(time_str) >= 5 else None

    if arr_min or arr_max:
        result = []
        for f in filtered:
            t = _extract_time(f.arrival_time)
            if t is None:
                result.append(f)  # keep flights without time data
                continue
            if arr_min and t < arr_min:
                continue
            if arr_max and t > arr_max:
                continue
            result.append(f)
        filtered = result

    if dep_min or dep_max:
        result = []
        for f in filtered:
            t = _extract_time(f.departure_time)
            if t is None:
                result.append(f)
                continue
            if dep_min and t < dep_min:
                continue
            if dep_max and t > dep_max:
                continue
            result.append(f)
        filtered = result

    return filtered


SYSTEM_PROMPT = """You are a Booking Recommendation. You help users find flights and hotels \
based on real crawled data from Booking.com and Traveloka.

STRICT RULES:
- ONLY use the flight/hotel data provided below. NEVER invent prices, airlines, times, or hotels.
- If data is provided, present the matching results clearly with prices and booking links.
- For each hotel include a booking link: [Book on Booking.com](BookURL)
- For each flight include a search link: [Search on Booking.com](BookURL)
- If NO data matches the user's request, say:
  "We cannot find any information related to your request."
  Then suggest similar options from the AVAILABLE DATA section below.
- Be concise and helpful. Use tables or bullet points for clarity.
- When suggesting alternatives, explain what data IS available (routes, cities, dates).
"""


def _build_ota_links(intent: dict) -> str:
    """Build OTA search links based on intent for when we have no data."""
    lines = []
    origin = intent.get("origin")
    dest = intent.get("destination")
    dest_city = intent.get("destination_city", "")
    dep = intent.get("departure_date")
    ret = intent.get("return_date")

    from datetime import date, timedelta

    try:
        dep_date = date.fromisoformat(dep) if dep else None
        ret_date = date.fromisoformat(ret) if ret else (
            dep_date + timedelta(days=4) if dep_date else None)
    except ValueError:
        dep_date = ret_date = None

    if dest_city and dep_date and ret_date:
        hotel_urls = get_hotel_search_urls(dest_city, dep_date, ret_date)
        if hotel_urls:
            links = " | ".join(f"[{s}]({u})" for s, u in hotel_urls.items())
            lines.append(f"Hotel search links: {links}")

    if origin and dest and dep_date and ret_date:
        flight_urls = get_flight_search_urls(origin, dest, dep_date, ret_date)
        if flight_urls:
            links = " | ".join(f"[{s}]({u})" for s, u in flight_urls.items())
            lines.append(f"Flight search links: {links}")

    return "\n".join(lines)


# -- Main chat loop --

if prompt := st.chat_input("Ask about flights or hotels..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Step 1: Extract intent
        with st.spinner("Thinking..."):
            intent = extract_intent(
                prompt,
                # history without current message
                st.session_state.messages[:-1],
                provider=provider,
                last_intent=st.session_state.last_intent,
            )

        # Step 2: Query inventory based on intent
        flights = []
        hotels = []
        grounding_context = ""

        search_type = intent.get("search_type", "general")

        # Persist intent so follow-up queries can inherit parameters
        # even after they scroll out of the conversation history window
        if search_type != "general":
            st.session_state.last_intent = intent

        if search_type in ("flight", "both"):
            origin = intent.get("origin")
            destination = intent.get("destination")
            dep_date_str = intent.get("departure_date")

            if origin and destination and dep_date_str:
                try:
                    from datetime import date
                    dep_date = date.fromisoformat(dep_date_str)
                    flights = get_available_flights(
                        origin, destination, dep_date)
                    flights = _filter_flights_by_time(flights, intent)
                except ValueError:
                    pass

        if search_type in ("hotel", "both"):
            dest_city = intent.get(
                "destination_city") or intent.get("destination")
            checkin_str = intent.get("departure_date")

            if dest_city and checkin_str:
                try:
                    from datetime import date
                    checkin = date.fromisoformat(checkin_str)
                    hotels = get_available_hotels(dest_city, checkin)

                    # Filter by max price if specified
                    max_price = intent.get("max_price")
                    if max_price and hotels:
                        hotels = [
                            h for h in hotels if h.price_per_night <= max_price]
                except ValueError:
                    pass

        # Step 3: Build grounding context
        has_data = bool(flights or hotels)
        context_parts = []

        if flights:
            context_parts.append(_format_flights(flights))
        elif search_type in ("flight", "both"):
            context_parts.append("No flights found for this route/date.")

        if hotels:
            context_parts.append(_format_hotels(hotels))
        elif search_type in ("hotel", "both"):
            context_parts.append("No hotels found for this city/date.")

        if not has_data and search_type != "general":
            context_parts.append(_build_alternatives_text())
            ota_links = _build_ota_links(intent)
            if ota_links:
                context_parts.append(
                    f"\n=== OTA SEARCH LINKS ===\n{ota_links}")

        grounding_context = "\n\n".join(context_parts)

        # Step 4: Generate response
        system_content = SYSTEM_PROMPT + "\n\n" + \
            grounding_context if grounding_context else SYSTEM_PROMPT
        chat_history = [{"role": "system", "content": system_content}]
        for m in st.session_state.messages[-10:]:
            chat_history.append({"role": m["role"], "content": m["content"]})

        try:
            with st.spinner("Thinking..."):
                reply = sync_chat(
                    chat_history, temperature=0.2, provider=provider, label="response")
        except Exception as exc:
            st.error(f"LLM error: {exc}")
            st.stop()

        # Step 5: Verify response (hybrid deterministic + LLM)
        verification_info = {}
        if verify_enabled and grounding_context:
            try:
                with st.spinner("Verifying..."):
                    vr = verify_response(
                        reply, grounding_context, prompt,
                        flights=flights, hotels=hotels,
                        provider=provider,
                    )
                    verification_info = {
                        "confidence": vr.get("confidence", 0.0),
                        "deterministic_score": vr.get("deterministic_score", 0.0),
                        "llm_score": vr.get("llm_score", 0.0),
                        "issues": vr.get("issues", []),
                        "safe_to_show": vr.get("safe_to_show", True),
                        "grounded": vr.get("grounded", False),
                    }

                if not verification_info["safe_to_show"] and verification_info["confidence"] < settings.verification_confidence_threshold:
                    st.error(
                        "This response may contain inaccurate information. "
                        "Please verify before acting on it."
                    )
            except Exception as exc:
                st.warning(f"Verification failed: {exc}")

        st.markdown(reply)

        # if verification_info:
        #     conf = verification_info["confidence"]
        #     det = verification_info["deterministic_score"]
        #     llm = verification_info["llm_score"]
        #     if conf >= 0.85:
        #         color = "green"
        #     elif conf >= 0.60:
        #         color = "orange"
        #     else:
        #         color = "red"
        #     st.markdown(
        #         f"---\n**Confidence:** :{color}[{conf:.0%}]"
        #         f" &nbsp;(facts: {det:.0%} | LLM: {llm:.0%})"
        #     )
        #     # if verification_info.get("issues"):
        #     st.warning("Issues: " + ", ".join(verification_info["issues"]))

        # Save message
        msg_data = {"role": "assistant", "content": reply}
        # if verification_info:
        #     msg_data["verification"] = verification_info
        st.session_state.messages.append(msg_data)

        _log(prompt, reply, verification_info or None)
