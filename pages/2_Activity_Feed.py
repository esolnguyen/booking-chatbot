"""Live Booking Activity Feed — shows recent bookings logged by the chatbot."""

import streamlit as st
from datetime import datetime
from app.booking_activity import get_recent_bookings

st.set_page_config(page_title="Booking Activity Feed", page_icon="bell", layout="wide")
st.title("Live Booking Activity Feed")
st.caption("Real-time feed of bookings recommended by the AI Travel Assistant.")

col_left, col_right = st.columns([3, 1])
with col_right:
    auto_refresh = st.toggle("Auto-refresh (5s)", value=True)
    if st.button("Refresh Now"):
        st.rerun()


@st.fragment(run_every=5 if True else None)
def _render_feed():
    events = get_recent_bookings(limit=30)

    if not events:
        st.info("No bookings yet. Use the Travel Booking Assistant to get recommendations.")
        return

    st.markdown(f"**{len(events)} recent event(s)**")

    for event in events:
        ts = event.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            time_str = dt.strftime("%b %d, %Y  %H:%M:%S")
        except Exception:
            time_str = ts

        traveler = event.get("traveler", "Unknown")
        traveler_id = event.get("traveler_id", "")

        if event["type"] == "flight":
            airline = event.get("airline", "")
            route = event.get("route", "")
            price = event.get("price", 0)
            cabin = event.get("cabin", "").title()
            fid = event.get("flight_id", "")
            with st.container(border=True):
                st.markdown(
                    f"[FLIGHT] &nbsp; **{traveler}** (`{traveler_id}`) just booked a flight\n\n"
                    f"&nbsp;&nbsp;&nbsp;&nbsp;**{airline}** &nbsp;|&nbsp; {route} &nbsp;|&nbsp; "
                    f"{cabin} &nbsp;|&nbsp; **${price:,.0f}** &nbsp;|&nbsp; `{fid}`"
                )
                st.caption(time_str)

        elif event["type"] == "hotel":
            name = event.get("hotel_name", "")
            city = event.get("city", "")
            price = event.get("price_per_night", 0)
            rating = event.get("rating", 0)
            hid = event.get("hotel_id", "")
            with st.container(border=True):
                st.markdown(
                    f"[HOTEL] &nbsp; **{traveler}** (`{traveler_id}`) just booked a hotel\n\n"
                    f"&nbsp;&nbsp;&nbsp;&nbsp;**{name}** &nbsp;|&nbsp; {city} &nbsp;|&nbsp; "
                    f"${price:,.0f}/night &nbsp;|&nbsp; {rating} stars &nbsp;|&nbsp; `{hid}`"
                )
                st.caption(time_str)


_render_feed()

if auto_refresh:
    import time
    time.sleep(5)
    st.rerun()
