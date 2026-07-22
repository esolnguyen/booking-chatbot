# Test Cases for Confidence Scoring & Routing

## How Confidence is Calculated

```
confidence = 0.35 × policy_compliant + 0.25 × inventory_available
 + 0.20 × evidence_grounded + 0.10 × freshness + 0.10 × margin
```

- `margin = max(0.0, 1.0 - num_risk_flags × 0.15)`
- Verification agent can adjust confidence by -0.3 to +0.1
- Hard overrides: inventory fail → cap at 0.40, policy fail → cap at 0.50, price mismatch → cap at 0.30

## Routing Thresholds

| Confidence | Route | UI Display |
|---|---|---|
| ≥ 0.85 | `auto_suggest` | Green banner |
| 0.60 – 0.84 | `suggest_with_caution` | Orange banner |
| < 0.60 | `human_review` | Red banner |

---

## Test Case 1: High Confidence — New York Standard Trip

**Expected route:** `auto_suggest` (~85-100%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | New York |
| Departure | 2026-04-01 |
| Return | 2026-04-03 |
| Tier | standard |
| Purpose | business |

**Why high confidence:**
- Flights FL-008 (Delta $450) and FL-009 (United $420) are well under the $2000 domestic limit
- Marriott Midtown NYC (HT-008, $480/night) is under the $500 standard hotel limit
- Both are preferred vendors (Delta/United, Marriott)
- Inventory is plentiful (55 and 40 seats, 6 rooms)
- No disruptive events on these dates
- All policy checks pass, all inventory available

---

## Test Case 2: Medium Confidence — Tokyo Cherry Blossom Season

**Expected route:** `suggest_with_caution` (~60-84%)

| Field | Value |
|---|---|
| Origin | SFO |
| Departure | 2026-04-01 |
| Return | 2026-04-05 |
| Destination | Tokyo |
| Tier | standard |
| Purpose | business |

**Why medium confidence:**
- Flights are policy-compliant (FL-001 Delta $1800, under $4000 intl economy limit)
- Marriott Shinjuku (HT-001, $350/night) is under $500 limit and preferred
- BUT cherry blossom event EVT-001 triggers high-demand risk flags
- Hilton Tokyo Bay (HT-002) is sold out (0 rooms) — limits options
- Marriott Shinjuku only has 3 rooms left — low availability risk
- Event risk flags reduce the margin component of confidence

---

## Test Case 3: Low Confidence — Bangkok During Songkran

**Expected route:** `human_review` (< 60%, likely capped at ~40%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | Bangkok |
| Departure | 2026-04-13 |
| Return | 2026-04-16 |
| Tier | standard |
| Purpose | business |

**Why low confidence:**
- FL-011 (Delta to BKK) has 0 seats — SOLD OUT
- FL-012 (United to BKK) has only 5 seats
- HT-011 (Marriott Sukhumvit) has 0 rooms — SOLD OUT
- HT-012 (Hyatt Regency) has only 2 rooms
- Songkran festival (EVT-002) causes massive disruptions, 200-300% price spikes
- If agent picks any sold-out option → inventory_ok = false → confidence capped at 0.40
- Multiple risk flags from event + low inventory further reduce margin
- Destination risk_level = 2 (higher than other cities)

---

## Test Case 4: Low Confidence — Singapore with Policy Violation

**Expected route:** `human_review` or `suggest_with_caution` (capped at ~50%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | Singapore |
| Departure | 2026-04-01 |
| Return | 2026-04-05 |
| Tier | standard |
| Purpose | business |

**Why lower confidence:**
- Marina Bay Sands (HT-006, $550/night) exceeds standard hotel limit of $500 → policy violation
- Marina Bay Sands is also NOT a preferred hotel vendor → double violation
- If agent picks HT-006: policy_compliant = false → confidence capped at 0.50
- If agent picks Hyatt Singapore (HT-007, $320/night) instead → policy passes, confidence higher
- FL-007 (Singapore Airlines business $4500) exceeds standard intl economy limit of $4000
- Tests whether the agent avoids policy-violating options

---

## Test Case 5: High Confidence — Executive Tier London

**Expected route:** `auto_suggest` (~85-100%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | London |
| Departure | 2026-04-01 |
| Return | 2026-04-05 |
| Tier | executive |
| Purpose | conference |

**Why high confidence:**
- Executive tier has generous limits ($800/night hotel, $6000 intl economy)
- FL-004 (Delta $2100) and FL-005 (United $1950) well within budget
- Hilton London City (HT-004, $380) and Marriott Canary Wharf (HT-005, $450) both under $800
- All preferred vendors
- Good inventory availability
- No disruptive events on these dates (Wimbledon is in June-July)

---

## Test Case 6: Zero Confidence — Unknown Destination

**Expected route:** `human_review` (0%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | Lagos |
| Departure | 2026-04-01 |
| Return | 2026-04-05 |
| Tier | standard |
| Purpose | business |

**Why zero confidence:**
- No flights or hotels in mock data for Lagos
- Pipeline returns immediately with `no_inventory` flag
- Confidence = 0.0, route = `human_review`

---

## Test Case 7: Non-Preferred Vendor Pressure — New York Budget

**Expected route:** `suggest_with_caution` (~60-75%)

| Field | Value |
|---|---|
| Origin | SFO |
| Destination | New York |
| Departure | 2026-04-01 |
| Return | 2026-04-03 |
| Tier | standard |
| Purpose | business |
| Preferences | cheapest |

**What to watch:**
- FL-010 (BudgetAir $280) is cheapest but NOT a preferred airline → policy violation
- Budget Stay NYC (HT-010, $180/night) is cheapest but NOT preferred → policy violation
- If agent optimizes for price and picks non-preferred vendors → policy_compliant = false → cap at 0.50
- If agent correctly picks preferred vendors (FL-009 United $420 + HT-008 Marriott $480) → higher confidence
- Tests whether the agent balances cost vs. policy compliance

---

## Quick Reference: Mock Inventory Cheat Sheet

### Flights from SFO

| ID | Airline | Dest | Price | Class | Seats | Preferred? |
|---|---|---|---|---|---|---|
| FL-001 | Delta | NRT (Tokyo) | $1,800 | economy | 45 | |
| FL-002 | United | NRT (Tokyo) | $1,650 | economy | 12 | |
| FL-003 | Singapore Air | NRT (Tokyo) | $3,200 | business | 8 | |
| FL-004 | Delta | LHR (London) | $2,100 | economy | 30 | |
| FL-005 | United | LHR (London) | $1,950 | economy | 22 | |
| FL-006 | Delta | SIN (Singapore) | $2,400 | economy | 18 | |
| FL-007 | Singapore Air | SIN (Singapore) | $4,500 | business | 6 | |
| FL-008 | Delta | JFK (New York) | $450 | economy | 55 | |
| FL-009 | United | JFK (New York) | $420 | economy | 40 | |
| FL-010 | BudgetAir | JFK (New York) | $280 | economy | 3 | |
| FL-011 | Delta | BKK (Bangkok) | $2,200 | economy | **0** | |
| FL-012 | United | BKK (Bangkok) | $2,050 | economy | 5 | |

### Hotels

| ID | Hotel | City | $/Night | Rooms | Preferred? |
|---|---|---|---|---|---|
| HT-001 | Marriott Shinjuku | Tokyo | $350 | 3 | |
| HT-002 | Hilton Tokyo Bay | Tokyo | $420 | **0** | |
| HT-003 | Budget Inn Tokyo | Tokyo | $120 | 15 | |
| HT-004 | Hilton London City | London | $380 | 8 | |
| HT-005 | Marriott Canary Wharf | London | $450 | 5 | |
| HT-006 | Marina Bay Sands | Singapore | $550 | 2 | |
| HT-007 | Hyatt Singapore | Singapore | $320 | 10 | |
| HT-008 | Marriott Midtown NYC | New York | $480 | 6 | |
| HT-009 | Hilton Times Square | New York | $520 | 4 | |
| HT-010 | Budget Stay NYC | New York | $180 | 20 | |
| HT-011 | Marriott Sukhumvit | Bangkok | $200 | **0** | |
| HT-012 | Hyatt Regency Bangkok | Bangkok | $250 | 2 | |

### Standard Tier Budget Limits

| Category | Limit |
|---|---|
| Hotel per night | $500 |
| Domestic flight (economy) | $2,000 |
| International flight (economy) | $4,000 |
| International flight (business) | $6,000 |
