# Bot Test Examples

Practical, copy-paste-ready prompts for the AI Travel Booking Assistant.
Each test shows what to set in the sidebar, what to ask, and what to expect.

---

## How to read each test

| Field | Meaning |
|---|---|
| **Sidebar** | Settings to configure before chatting |
| **Ask** | Copy-paste this into the chat input |
| **Expected flight** | ID + key facts from seed data |
| **Expected hotel** | ID + key facts from seed data |
| **Expected route** | auto_suggest / suggest_with_caution / human_review |
| **Activity feed** | What should appear in the Live Booking Activity Feed page |

---

## Test 1 — Clean international trip (Sydney, standard)

**Why this is useful:** Straightforward international happy path. All preferred vendors, well within budget, no events on these dates.

### Sidebar settings
| Field | Value |
|---|---|
| Name | Alice Johnson |
| Employee ID | EMP-001 |
| Department | Engineering |
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Sydney` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |
| Trip purpose | `business` |
| Preferences | *(leave blank)* |

### Ask
```
Recommend the best flight and hotel for my Sydney trip.
```

### What to expect
- **Flight:** FL-009 United SFO→SYD $1,350 (1 stop, 25 seats) or FL-008 Delta $1,500 (non-stop, 30 seats)
- **Hotel:** HT-008 Marriott Sydney CBD $420/night — preferred vendor, 8 rooms, gym + restaurant
- **Route:** `auto_suggest` — both under standard intl limit ($4,000 economy), preferred vendors, no events in April
- **Activity feed:** `Alice Johnson (EMP-001) just booked a flight` + `just booked a hotel`

### Follow-up questions to try
```
Why did you pick United over Delta?
```
```
Is the Marriott Sydney CBD within my hotel budget?
```
```
How long is the flight from SFO to Sydney?
```

---

## Test 2 — Peak season with low inventory (Tokyo, cherry blossom)

**Why this is useful:** Tests event awareness and low-room-count risk flags.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Tokyo` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |
| Trip purpose | `business` |

### Ask
```
I need a flight and hotel in Tokyo. What do you recommend?
```

### What to expect
- **Flight:** FL-001 Delta SFO→NRT $1,800 economy (45 seats) — preferred, under $4,000 intl limit
- **Hotel:** HT-001 Marriott Shinjuku $350/night — only 3 rooms left; HT-002 Hilton Tokyo Bay is sold out
- **Route:** `suggest_with_caution` — cherry blossom EVT-001 triggers high-demand risk flag
- **Activity feed:** booking cards appear for Alice with FL-001 + HT-001

### Follow-up questions to try
```
Are there any events in Tokyo during my travel dates?
```
```
The Hilton Tokyo Bay looks good — is it available?
```
> Expected: agent flags HT-002 as sold out (0 rooms).

```
How many rooms does Marriott Shinjuku have left?
```

---

## Test 3 — Inventory crisis (Bangkok, Songkran festival)

**Why this is useful:** Triggers sold-out flights + hotel + festival disruption — the hardest failure case.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Bangkok` |
| Departure | `2026-04-13` |
| Return | `2026-04-16` |
| Trip purpose | `business` |

### Ask
```
Book me a flight and hotel in Bangkok for this trip.
```

### What to expect
- **Flight:** FL-012 United SFO→BKK $2,050 (only 5 seats) — FL-011 Delta is sold out (0 seats)
- **Hotel:** HT-012 Hyatt Regency Bangkok $250/night (2 rooms) — HT-011 Marriott Sukhumvit sold out
- **Route:** `human_review` — Songkran EVT-002 (200-300% price spike, road closures), sold-out primary options
- **Escalation queue:** item appears in sidebar for human approval

### Follow-up questions to try
```
Why is confidence low for this booking?
```
```
Is it safe to travel to Bangkok during Songkran for a business meeting?
```
```
What is the cheapest available option for Bangkok on these dates?
```

---

## Test 4 — Policy violation (Singapore, over-budget)

**Why this is useful:** Tests whether the agent respects the standard-tier hotel and flight budget caps.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Singapore` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |
| Trip purpose | `conference` |

### Ask
```
I want to stay at Marina Bay Sands and fly Singapore Airlines business class.
```

### What to expect
- **Flight:** FL-007 Singapore Airlines SFO→SIN $4,500 business — exceeds $4,000 standard economy limit
- **Hotel:** HT-006 Marina Bay Sands $550/night — exceeds $500 standard limit + not preferred vendor
- **Route:** `human_review` — double policy violation caps confidence at ≤0.50
- Agent should flag both violations and suggest compliant alternatives:
 - FL-006 Delta SFO→SIN $2,400 economy 
 - HT-007 Hyatt Singapore $320/night 

### Follow-up questions to try
```
What is the policy limit for hotels on the standard tier?
```
```
Can I get approved to stay at Marina Bay Sands?
```
```
What is the preferred hotel in Singapore within my budget?
```

---

## Test 5 — Executive tier, relaxed limits (London, conference)

**Why this is useful:** Confirms executive tier unlocks higher limits and business class flights.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `executive` |
| Origin | `SFO` |
| Destination | `London` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |
| Trip purpose | `conference` |
| Preferences | `hotel_gym, non_stop` |

### Ask
```
What are the best flight and hotel options for my London conference?
```

### What to expect
- **Flight:** FL-004 Delta SFO→LHR $2,100 economy non-stop (30 seats) — well under $6,000 executive limit
- **Hotel:** HT-005 Marriott Canary Wharf $450/night — preferred, 5 rooms, gym + pool + spa
- **Route:** `auto_suggest` — executive limits comfortable, preferred vendors, no events (Wimbledon is June-July)

### Follow-up questions to try
```
Can I upgrade to business class for this flight as an executive-tier traveler?
```
```
Compare Hilton London City vs Marriott Canary Wharf.
```

---

## Test 6 — Cheapest option pressure (Sydney, non-preferred vendor)

**Why this is useful:** Tests whether the agent picks the policy-safe option over the cheapest one.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Sydney` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |
| Preferences | `cheapest` |

### Ask
```
I want the absolute cheapest flight and hotel to Sydney. Cost is the only priority.
```

### What to expect
- Cheapest flight is FL-010 BudgetAir $750 — not preferred vendor, 2 stops, only 5 seats left
- Cheapest hotel is HT-010 Budget Inn Sydney $160/night — not preferred vendor (Marriott/Hilton/Hyatt required)
- Agent should warn about non-preferred vendors and suggest FL-009 United $1,350 + HT-008 Marriott $420 instead
- **Route:** `suggest_with_caution` or `human_review` if agent picks non-preferred options

### Follow-up questions to try
```
What happens if I book with BudgetAir instead of a preferred airline?
```
```
Is Budget Inn Sydney a preferred hotel vendor?
```

---

## Test 7 — Unknown destination (no inventory)

**Why this is useful:** Tests graceful failure when no data exists for the requested city.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Origin | `SFO` |
| Destination | `Paris` |
| Departure | `2026-04-01` |

### Ask
```
What flights and hotels are available in Paris?
```

### What to expect
- No flights or hotels exist for Paris in mock data
- Agent should clearly say no inventory is available for this destination
- **Route:** `human_review` — confidence 0.0, `no_inventory` flag
- No booking cards in activity feed (nothing to log)

---

## Test 8 — Availability check only (no booking intent)

**Why this is useful:** Tests informational queries that shouldn't trigger booking activity.

### Sidebar settings
*(any destination — e.g. Tokyo)*

### Ask
```
Which Tokyo hotels still have rooms available right now?
```

### What to expect
- Agent lists HT-001 Marriott Shinjuku (3 rooms) and HT-003 Budget Inn Tokyo (15 rooms)
- Flags HT-002 Hilton Tokyo Bay as sold out (0 rooms)
- Activity feed: **no new booking card** (informational only — no FL/HT IDs in recommendation context)

---

## Test 9 — Multi-turn conversation (Tokyo, follow-up refinement)

**Why this is useful:** Tests whether the agent holds context across turns.

### Sidebar settings
| Field | Value |
|---|---|
| Policy tier | `standard` |
| Destination | `Tokyo` |
| Departure | `2026-04-01` |
| Return | `2026-04-05` |

### Turn 1
```
Recommend a flight and hotel for Tokyo.
```

### Turn 2
```
What if I want a non-stop flight only?
```
> Expected: agent narrows to FL-001 Delta non-stop (FL-002 United has 1 stop).

### Turn 3
```
The hotel you suggested only has 3 rooms. Should I book quickly?
```
> Expected: agent confirms low availability for HT-001 Marriott Shinjuku and recommends booking soon given cherry blossom demand spike.

### Turn 4
```
What's my total estimated cost for 4 nights?
```
> Expected: flight + (4 × hotel rate) calculated from seed data prices.

---

## Quick Reference — Seed Data Cheat Sheet

### Flights (all depart SFO)

| ID | Airline | Destination | Price | Cabin | Seats | Policy (standard) |
|---|---|---|---|---|---|---|
| FL-001 | Delta | NRT Tokyo | $1,800 | economy | 45 | |
| FL-002 | United | NRT Tokyo | $1,650 | economy | 12 | |
| FL-003 | Singapore Air | NRT Tokyo | $3,200 | business | 8 | (needs VP) |
| FL-004 | Delta | LHR London | $2,100 | economy | 30 | |
| FL-005 | United | LHR London | $1,950 | economy | 22 | |
| FL-006 | Delta | SIN Singapore | $2,400 | economy | 18 | |
| FL-007 | Singapore Air | SIN Singapore | $4,500 | business | 6 | over limit |
| FL-008 | Delta | SYD Sydney | $1,500 | economy | 30 | |
| FL-009 | United | SYD Sydney | $1,350 | economy | 25 | |
| FL-010 | BudgetAir | SYD Sydney | $750 | economy | 5 | non-preferred |
| FL-011 | Delta | BKK Bangkok | $2,200 | economy | **0** | sold out |
| FL-012 | United | BKK Bangkok | $2,050 | economy | 5 | |

### Hotels

| ID | Hotel | City | $/Night | Rooms | Policy (standard) |
|---|---|---|---|---|---|
| HT-001 | Marriott Shinjuku | Tokyo | $350 | 3 | |
| HT-002 | Hilton Tokyo Bay | Tokyo | $420 | **0** | sold out |
| HT-003 | Budget Inn Tokyo | Tokyo | $120 | 15 | non-preferred |
| HT-004 | Hilton London City | London | $380 | 8 | |
| HT-005 | Marriott Canary Wharf | London | $450 | 5 | |
| HT-006 | Marina Bay Sands | Singapore | $550 | 2 | over limit + non-preferred |
| HT-007 | Hyatt Singapore | Singapore | $320 | 10 | |
| HT-008 | Marriott Sydney CBD | Sydney | $420 | 8 | |
| HT-009 | Hilton Sydney | Sydney | $480 | 5 | |
| HT-010 | Budget Inn Sydney | Sydney | $160 | 18 | non-preferred |
| HT-011 | Marriott Sukhumvit | Bangkok | $200 | **0** | sold out |
| HT-012 | Hyatt Regency Bangkok | Bangkok | $250 | 2 | |

### Events that affect pricing/availability

| Event | City | Dates | Impact |
|---|---|---|---|
| Cherry Blossom | Tokyo | 2026-03-25 → 2026-04-15 | 150-200% hotel price spike |
| Songkran Festival | Bangkok | 2026-04-13 → 2026-04-15 | 200-300% spike, road closures |
| Wimbledon | London | 2026-06-29 → 2026-07-12 | Moderate demand increase |
| Vivid Sydney Festival | Sydney | 2026-05-22 → 2026-06-13 | 30-60% hotel price increase in CBD |

### Budget limits

| Tier | Hotel/night | Domestic flight | Intl economy | Intl business |
|---|---|---|---|---|
| standard | $500 | $2,000 | $4,000 | $6,000 (VP approval) |
| executive | $800 | $6,000 | $6,000 | $8,000 (director approval) |
