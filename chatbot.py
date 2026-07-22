import asyncio
import re
import streamlit as st
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

from openai import AzureOpenAI
from app.config import settings
from app.mock.inventory_api import get_available_flights, get_available_hotels
from app.mock.knowledge_base import get_vector_store
from app.orchestrator.retriever import retrieve_context, format_context_for_prompt
from app.orchestrator.reranker import rerank_documents
from app.orchestrator.pipeline import run_pipeline
from app.validation.policy_checker import (
    check_flight_policy,
    check_hotel_policy,
    BUDGET_LIMITS,
    PREFERRED_AIRLINES,
    PREFERRED_HOTELS,
)
from app.validation.response_verifier import verify_response
from app.models.request import BookingRequest, TravelerProfile
from app.booking_activity import log_booking

import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "chat_log")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d") + ".txt")


def _log_interaction(question: str, answer: str, verification: dict | None = None):
    """Append a Q&A interaction with verification details to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"[{timestamp}]",
        f"USER: {question}",
        f"AGENT: {answer}",
    ]
    if verification:
        lines.append(f"CONFIDENCE: {verification.get('confidence', 'N/A')}")
        lines.append(f"ROUTE: {verification.get('route', 'N/A')}")
        issues = verification.get("risk_flags", [])
        lines.append(f"ISSUES: {', '.join(issues) if issues else 'None'}")
        lines.append(f"SAFE_TO_SHOW: {verification.get('safe_to_show', 'N/A')}")
        lines.append(f"NEEDS_APPROVAL: {verification.get('needs_approval', False)}")
        lines.append(f"APPROVAL_ID: {verification.get('approval_id', 'N/A')}")
    else:
        lines.append("VERIFICATION: disabled")
    lines.append("-" * 80)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _maybe_log_booking(reply: str, traveler_name: str, traveler_id: str, dest: str) -> None:
    """Extract recommended flight/hotel IDs from the reply and log booking activity."""
    flight_ids = re.findall(r"\bFL-\d+\b", reply)
    hotel_ids = re.findall(r"\bHT-\d+\b", reply)
    if not flight_ids and not hotel_ids:
        return
    flight_id = flight_ids[0] if flight_ids else None
    hotel_id = hotel_ids[0] if hotel_ids else None
    try:
        log_booking(
            traveler_name=traveler_name,
            traveler_id=traveler_id,
            destination=dest,
            flight_id=flight_id,
            hotel_id=hotel_id,
        )
    except Exception:
        pass


st.set_page_config(page_title="Travel Booking Assistant", page_icon="plane", layout="wide")
st.title("AI Travel Booking Assistant")

# --- Sidebar ---
with st.sidebar:
    st.header("Trip Details")
    emp_name = st.text_input("Your name", "Alice Johnson")
    emp_id = st.text_input("Employee ID", "EMP-001")
    department = st.text_input("Department", "Engineering")
    tier = st.selectbox("Policy tier", ["standard", "executive", "vip"])
    origin = st.text_input("Origin airport", "SFO")
    destination = st.text_input("Destination city", "Tokyo")
    dep_date = st.date_input("Departure", date.today() + timedelta(days=7))
    ret_date = st.date_input("Return", date.today() + timedelta(days=11))
    purpose = st.selectbox("Trip purpose", ["business", "conference", "training"])
    prefs = st.text_input("Preferences (comma-separated)", "non_stop, hotel_gym")

    st.divider()
    verify_enabled = st.toggle("Enable response verification", value=True)
    hitl_threshold = st.slider(
        "Verification confidence threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.05,
        help="Responses below this confidence get flagged for human review",
    )

    st.divider()
    st.subheader("Quick Test Scenarios")
    if st.button("Tokyo (Cherry Blossom)"):
        st.session_state.update(
            {"_dest": "Tokyo", "_dep": "2026-04-01", "_ret": "2026-04-05"}
        )
        st.rerun()
    if st.button("Bangkok (Songkran)"):
        st.session_state.update(
            {"_dest": "Bangkok", "_dep": "2026-04-13", "_ret": "2026-04-16"}
        )
        st.rerun()
    if st.button("Sydney (Standard)"):
        st.session_state.update(
            {"_dest": "Sydney", "_dep": "2026-04-01", "_ret": "2026-04-05"}
        )
        st.rerun()

# Init KB
if "kb_ready" not in st.session_state:
    with st.spinner("Loading knowledge base..."):
        get_vector_store()
    st.session_state.kb_ready = True

# Escalation queue
if "escalation_queue" not in st.session_state:
    st.session_state.escalation_queue = []


def _build_request() -> BookingRequest:
    return BookingRequest(
        traveler=TravelerProfile(
            employee_id=emp_id,
            name=emp_name,
            department=department,
            org_policy_tier=tier,
        ),
        origin=origin,
        destination=destination,
        departure_date=dep_date,
        return_date=ret_date,
        trip_purpose=purpose,
        preferences=[p.strip() for p in prefs.split(",") if p.strip()],
    )


def _build_system_context() -> str:
    request = _build_request()
    context = retrieve_context(request)
    keywords = [destination, tier, purpose, str(dep_date)]
    for key in context:
        context[key] = rerank_documents(context[key], keywords, top_k=3)
    context_text = format_context_for_prompt(context)

    flights = get_available_flights(origin, destination)
    hotels = get_available_hotels(destination)

    inv_lines = ["=== AVAILABLE FLIGHTS ==="]
    for f in flights:
        f_ok, f_issues = check_flight_policy(f, tier)
        inv_ok = "OK" if f.available_seats > 0 else "SOLD OUT"
        pol_ok = "OK" if f_ok else f"VIOLATION: {'; '.join(f_issues)}"
        inv_lines.append(
            f"[{f.id}] {f.airline} {f.origin}->{f.destination} "
            f"${f.price} {f.cabin_class} {f.stops} stops "
            f"{f.available_seats} seats | Inventory: {inv_ok} | Policy: {pol_ok}"
        )
    inv_lines.append("\n=== AVAILABLE HOTELS ===")
    for h in hotels:
        h_ok, h_issues = check_hotel_policy(h, tier)
        inv_ok = "OK" if h.available_rooms > 0 else "NO ROOMS"
        pol_ok = "OK" if h_ok else f"VIOLATION: {'; '.join(h_issues)}"
        inv_lines.append(
            f"[{h.id}] {h.name} ${h.price_per_night}/night "
            f"Rating:{h.rating} {h.available_rooms} rooms "
            f"Amenities:{','.join(h.amenities)} | Inventory: {inv_ok} | Policy: {pol_ok}"
        )
    inventory_text = "\n".join(inv_lines)

    budget = BUDGET_LIMITS.get(tier, BUDGET_LIMITS["standard"])
    budget_text = "\n".join(f"  {k}: ${v}" for k, v in budget.items())

    return (
        f"You are a corporate travel booking assistant. Help the traveler plan their trip.\n\n"
        f"TRAVELER: {emp_name} ({tier} tier, {department})\n"
        f"TRIP: {origin} -> {destination}, {dep_date} to {ret_date}, {purpose}\n"
        f"PREFERENCES: {prefs}\n\n"
        f"BUDGET LIMITS for {tier} tier:\n{budget_text}\n"
        f"PREFERRED AIRLINES: {', '.join(PREFERRED_AIRLINES)}\n"
        f"PREFERRED HOTELS: {', '.join(PREFERRED_HOTELS)}\n\n"
        f"{context_text}\n\n{inventory_text}\n\n"
        f"RULES:\n"
        f"- ONLY use the data above. Never invent prices, availability, or policies.\n"
        f"- If data is missing, say so clearly.\n"
        f"- Flag policy violations and sold-out options.\n"
        f"- Cite evidence IDs like [POL-001] when referencing policies.\n"
        f"- Be concise and helpful."
    )


def _confidence_color(conf: float) -> str:
    if conf >= 0.85:
        return "green"
    elif conf >= 0.60:
        return "orange"
    return "red"


def _route_badge(route: str) -> str:
    return {
        "auto_suggest": "[AUTO]",
        "suggest_with_caution": "[CAUTION]",
        "human_review": "[REVIEW]",
    }.get(route, "[UNKNOWN]")


# --- Chat state ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "verification" in msg:
            v = msg["verification"]
            conf = v.get("confidence", 0)
            route = v.get("route", "unknown")
            color = _confidence_color(conf)
            badge = _route_badge(route)
            st.markdown(
                f"---\n{badge} **Route:** `{route}` &nbsp; | &nbsp; "
                f"**Confidence:** :{color}[{conf:.0%}]"
            )
            if v.get("risk_flags"):
                st.warning("Risk flags: " + ", ".join(v["risk_flags"]))
            if v.get("needs_approval"):
                st.info("This recommendation is pending human approval.")

# Chat input
if prompt := st.chat_input("Ask about your trip..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
            )
            system_ctx = _build_system_context()
            chat_history = [{"role": "system", "content": system_ctx}]
            for m in st.session_state.messages:
                chat_history.append({"role": m["role"], "content": m["content"]})

            response = client.chat.completions.create(
                model=settings.azure_openai_chat_deployment,
                messages=chat_history,
                temperature=0.2,
            )
            reply = response.choices[0].message.content

        verification_info = {}
        if verify_enabled:
            with st.spinner("Verifying response..."):
                vr = verify_response(reply, system_ctx, prompt)
                conf = vr.get("confidence", 0.0)
                issues = vr.get("issues", [])
                safe = vr.get("safe_to_show", True)

                if conf >= settings.auto_suggest_threshold:
                    route = "auto_suggest"
                elif conf >= hitl_threshold:
                    route = "suggest_with_caution"
                else:
                    route = "human_review"

                needs_approval = route in ("human_review", "suggest_with_caution")

                approval_id = None
                if needs_approval:
                    try:
                        loop = asyncio.new_event_loop()
                        request = _build_request()
                        pipeline_result = loop.run_until_complete(run_pipeline(request))
                        approval_id = pipeline_result.approval_id
                    except Exception:
                        pass
                    finally:
                        loop.close()

                verification_info = {
                    "confidence": conf,
                    "route": route,
                    "risk_flags": issues,
                    "needs_approval": needs_approval,
                    "safe_to_show": safe,
                    "approval_id": approval_id,
                }

            color = _confidence_color(conf)
            badge = _route_badge(route)

            if not safe and conf < hitl_threshold:
                st.error(
                    "This response may contain inaccurate information. Please verify before acting on it."
                )
            st.markdown(reply)
            st.markdown(f"---\n{badge} **Route:** `{route}` | **Confidence:** :{color}[{conf:.0%}]")

            if needs_approval:
                aid = verification_info.get("approval_id", "N/A")
                st.info(
                    "This recommendation requires human review before acting on it.\n\n"
                    f"Approval ID: `{aid}`"
                )
                st.session_state.escalation_queue.append(verification_info)
        else:
            st.markdown(reply)

        msg_data = {"role": "assistant", "content": reply}
        if verification_info:
            msg_data["verification"] = verification_info
        st.session_state.messages.append(msg_data)

        _maybe_log_booking(reply, emp_name, emp_id, destination)
        _log_interaction(prompt, reply, verification_info if verification_info else None)

# --- Handle regeneration if flagged ---
if st.session_state.get("_regenerate_index") is not None:
    regen_idx = st.session_state.pop("_regenerate_index")
    if 0 <= regen_idx < len(st.session_state.messages):
        user_prompt = None
        for j in range(regen_idx - 1, -1, -1):
            if st.session_state.messages[j]["role"] == "user":
                user_prompt = st.session_state.messages[j]["content"]
                break
        if user_prompt:
            st.session_state.messages.pop(regen_idx)
            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\n"
                        "[SYSTEM NOTE: A previous answer to this question was rejected by a human reviewer "
                        "due to accuracy concerns. Please be extra careful with facts, cite evidence IDs, "
                        "and only state what is directly supported by the provided data.]"
                    ),
                }
            )
            st.rerun()

# --- Escalation queue sidebar ---
if st.session_state.escalation_queue:
    with st.sidebar:
        st.divider()
        queue_len = len(st.session_state.escalation_queue)
        st.subheader(f"Pending Reviews ({queue_len})")
        for i, item in enumerate(st.session_state.escalation_queue):
            label = f"Review #{i+1} -- {item['route']} ({item['confidence']:.0%})"
            with st.expander(label):
                st.json(item)
                col1, col2, col3 = st.columns(3)
                if col1.button("Approve", key=f"approve_{i}"):
                    for msg in st.session_state.messages:
                        v = msg.get("verification", {})
                        if v.get("approval_id") == item.get("approval_id"):
                            v["status"] = "approved"
                    st.session_state.escalation_queue.pop(i)
                    _log_interaction("[HUMAN REVIEW]", "APPROVED", {
                        "confidence": item.get("confidence"),
                        "route": item.get("route"),
                        "risk_flags": item.get("risk_flags", []),
                    })
                    st.success("Approved")
                    st.rerun()
                if col2.button("Reject", key=f"reject_{i}"):
                    for idx, msg in enumerate(st.session_state.messages):
                        v = msg.get("verification", {})
                        if v.get("approval_id") == item.get("approval_id"):
                            v["status"] = "rejected"
                            st.session_state["_regenerate_index"] = idx
                            break
                    st.session_state.escalation_queue.pop(i)
                    _log_interaction("[HUMAN REVIEW]", "REJECTED — triggering regeneration", {
                        "confidence": item.get("confidence"),
                        "route": item.get("route"),
                        "risk_flags": item.get("risk_flags", []),
                    })
                    st.rerun()
                if col3.button("Reject & Stop", key=f"reject_stop_{i}"):
                    for msg in st.session_state.messages:
                        v = msg.get("verification", {})
                        if v.get("approval_id") == item.get("approval_id"):
                            v["status"] = "rejected"
                            msg["content"] += "\n\n> **This response was rejected by a human reviewer and should not be acted upon.**"
                    st.session_state.escalation_queue.pop(i)
                    _log_interaction("[HUMAN REVIEW]", "REJECTED — no regeneration", {
                        "confidence": item.get("confidence"),
                        "route": item.get("route"),
                        "risk_flags": item.get("risk_flags", []),
                    })
                    st.error("Rejected — response marked as unreliable")
                    st.rerun()
