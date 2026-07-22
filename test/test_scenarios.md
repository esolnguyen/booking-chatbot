# Test Scenarios for Low Confidence / Human-in-the-Loop

## Scenario 1: Bangkok During Songkran (Inventory Failure)

**Sidebar settings:**
- Origin: `SFO`
- Destination: `Bangkok`
- Departure: `2026-04-13`
- Return: `2026-04-16`
- Tier: `standard`

**Ask:** "Book me a flight and hotel in Bangkok"

**Why it triggers low confidence:**
- Flight FL-011 (Delta to BKK) has 0 available seats
- Hotel HT-011 (Marriott Sukhumvit) has 0 available rooms
- Songkran festival causes 200-300% price spikes and business closures
- Inventory failure caps confidence at 0.4 → routed to `human_review`

---

## Scenario 2: Policy Violation (Over Budget)

**Sidebar settings:**
- Origin: `SFO`
- Destination: `Singapore`
- Tier: `standard`

**Ask:** "I want the Marina Bay Sands and business class on Singapore Airlines"

**Why it triggers low confidence:**
- Marina Bay Sands is $550/night (standard hotel limit is $500)
- Singapore Airlines business class is $4,500 (international economy limit is $4,000, business needs VP approval)
- Policy violations cap confidence at 0.5 → routed to `suggest_with_caution` or `human_review`

---

## Scenario 3: No Inventory (Unknown Destination)

**Sidebar settings:**
- Origin: `SFO`
- Destination: `Paris` (or `Berlin`, `Sydney`, etc.)

**Ask:** "What flights and hotels are available?"

**Why it triggers low confidence:**
- No mock flights or hotels exist for this destination
- Pipeline returns confidence 0.0 with `no_inventory` risk flag
- Immediately routed to `human_review`

---

## Scenario 4: Raise the Threshold (Force Flag on Good Responses)

**Sidebar settings:**
- Any valid destination (e.g. `Tokyo`, `New York`)
- Drag "Verification confidence threshold" slider up to `0.95`

**Ask:** Any normal question like "Recommend a flight and hotel in Tokyo"

**Why it triggers low confidence:**
- Even a solid response with 0.80 confidence will fall below the 0.95 threshold
- Routed to `suggest_with_caution` → appears in escalation queue

---

## Scenario 5: Non-Preferred Vendor

**Sidebar settings:**
- Origin: `SFO`
- Destination: `New York`
- Tier: `standard`

**Ask:** "Book me the cheapest flight to New York, I don't care about the airline"

**Why it may trigger low confidence:**
- Cheapest flight is FL-010 BudgetAir at $280 with 2 stops and only 3 seats
- BudgetAir is not a preferred vendor (preferred: Delta, United, Singapore Airlines)
- Low seat availability + non-preferred vendor = risk flags

---

## Expected Behavior When Flagged

1. Response shows in chat with route badge and confidence score
2. Item appears in sidebar under "Pending Reviews"
3. Reviewer can:
 - **Approve** — marks as reviewed, logs to `chat_log/`
 - **Reject** — removes response, auto-regenerates with stricter instructions
 - **Reject & Stop** — stamps response with rejection warning, no retry
4. All actions are logged to `chat_log/YYYY-MM-DD.txt`
