"""Inventory Dashboard — shows all available flights and hotels from seed data."""

import streamlit as st
import pandas as pd
from app.mock.seed_data import MOCK_FLIGHTS, MOCK_HOTELS, AIRPORT_TO_CITY

st.set_page_config(page_title="Inventory Dashboard", page_icon="package", layout="wide")
st.title("Inventory Dashboard")
st.caption("Live view of available flights and hotels from the mock inventory.")

# ── Flights ──────────────────────────────────────────────────────────────────
st.header("Flights")

flight_rows = []
for f in MOCK_FLIGHTS:
    dest_city = AIRPORT_TO_CITY.get(f["destination"], f["destination"])
    flight_rows.append(
        {
            "ID": f["id"],
            "Airline": f["airline"],
            "Route": f"{f['origin']} → {f['destination']}",
            "Destination City": dest_city,
            "Departure": f["departure_time"],
            "Arrival": f["arrival_time"],
            "Cabin": f["cabin_class"].title(),
            "Stops": f["stops"],
            "Price (USD)": f["price"],
            "Seats Available": f["available_seats"],
            "Status": "Available" if f["available_seats"] > 0 else "Sold Out",
        }
    )

df_flights = pd.DataFrame(flight_rows)

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    dest_filter = st.multiselect(
        "Filter by Destination City",
        options=sorted(df_flights["Destination City"].unique()),
    )
with col2:
    airline_filter = st.multiselect(
        "Filter by Airline",
        options=sorted(df_flights["Airline"].unique()),
    )
with col3:
    cabin_filter = st.multiselect(
        "Filter by Cabin",
        options=sorted(df_flights["Cabin"].unique()),
    )

filtered_flights = df_flights.copy()
if dest_filter:
    filtered_flights = filtered_flights[
        filtered_flights["Destination City"].isin(dest_filter)
    ]
if airline_filter:
    filtered_flights = filtered_flights[
        filtered_flights["Airline"].isin(airline_filter)
    ]
if cabin_filter:
    filtered_flights = filtered_flights[filtered_flights["Cabin"].isin(cabin_filter)]

st.dataframe(
    filtered_flights,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Price (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "Seats Available": st.column_config.NumberColumn(),
    },
)

col_a, col_b, col_c = st.columns(3)
col_a.metric("Total Flights", len(df_flights))
col_b.metric("Available", len(df_flights[df_flights["Seats Available"] > 0]))
col_c.metric("Sold Out", len(df_flights[df_flights["Seats Available"] == 0]))

st.divider()

# ── Hotels ───────────────────────────────────────────────────────────────────
st.header("Hotels")

hotel_rows = []
for h in MOCK_HOTELS:
    hotel_rows.append(
        {
            "ID": h["id"],
            "Name": h["name"],
            "City": h["city"],
            "Price / Night (USD)": h["price_per_night"],
            "Rating": h["rating"],
            "Rooms Available": h["available_rooms"],
            "Amenities": ", ".join(h["amenities"]),
            "Status": "Available" if h["available_rooms"] > 0 else "No Rooms",
        }
    )

df_hotels = pd.DataFrame(hotel_rows)

col4, col5 = st.columns(2)
with col4:
    city_filter = st.multiselect(
        "Filter by City",
        options=sorted(df_hotels["City"].unique()),
    )
with col5:
    min_rating = st.slider(
        "Minimum Rating", min_value=1.0, max_value=5.0, value=1.0, step=0.1
    )

filtered_hotels = df_hotels.copy()
if city_filter:
    filtered_hotels = filtered_hotels[filtered_hotels["City"].isin(city_filter)]
filtered_hotels = filtered_hotels[filtered_hotels["Rating"] >= min_rating]

st.dataframe(
    filtered_hotels,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Price / Night (USD)": st.column_config.NumberColumn(format="$%.2f"),
        "Rating": st.column_config.NumberColumn(format="%.1f"),
        "Rooms Available": st.column_config.NumberColumn(),
    },
)

col_d, col_e, col_f = st.columns(3)
col_d.metric("Total Hotels", len(df_hotels))
col_e.metric("Available", len(df_hotels[df_hotels["Rooms Available"] > 0]))
col_f.metric("No Rooms", len(df_hotels[df_hotels["Rooms Available"] == 0]))
