## Test questions based on live DB data

Routes: NRT→SGN, SGN→NRT, SGN→SYD, SYD→SGN
Hotels: Ho Chi Minh City, Sydney, Tokyo
Dates available: 2026-04-07 onwards

---

### Basic flight lookup

1. "Find me a flight from Saigon to Sydney tomorrow"
   (Tests: alias resolution SGN, date "tomorrow" = 2026-04-07, 4 results expected)

2. "I want to fly from Tokyo to Ho Chi Minh City on April 7"
   (Tests: NRT→SGN, should show Vietnam Airlines $660, VietJet $682, JAL $547, ANA $644)

3. "Show me flights from SGN to NRT on April 8"
   (Tests: direct IATA input, 4 results with prices $302–$565)

---

### Filters

4. "Flights from Saigon to Tokyo under $400 tomorrow"
   (Tests: price filter — only ANA $302 and JAL $395 qualify on 2026-04-07)

5. "Are there any direct flights from Ho Chi Minh City to Tokyo?"
   (Tests: stops=0 filter — Vietnam Airlines 09:30 and VietJet 14:00 are non-stop)

6. "I need a flight from Tokyo to Saigon that arrives before 4pm"
   (Tests: arrival_time_max=16:00 — Vietnam Airlines arrives 15:30, VietJet 20:00 excluded)

7. "Fly me from Sydney to Saigon, depart after 10am on April 7"
   (Tests: departure_time_min=10:00 — Singapore Airlines 11:30 and Qantas 19:50 qualify)

---

### Hotel lookup

8. "Find me a hotel in Ho Chi Minh City for April 7"
   (Tests: hotel search, should return 12 properties $18–$25/night)

9. "What's the best rated hotel in Ho Chi Minh City?"
   (Tests: rating sort — MEME Homestay and Private Rooms are both 4.8)

10. "Show me hotels in Saigon under $20 per night"
    (Tests: max_price filter — Lumi Living, MEME HOME, Sakura Dormitory at $18)

---

### Flight + Hotel combo

11. "I want to fly from Tokyo to Ho Chi Minh City on April 7 and need a hotel under $25/night"
    (Tests: both, NRT→SGN flights + HCMC hotels filtered by price)

12. "Plan a trip from Sydney to Saigon on April 8, show flights and a well-rated hotel"
    (Tests: SYD→SGN flights + HCMC hotels with rating, follow-up context)

---

### Multi-constraint / reasoning

13. "Which airline is cheapest for Saigon to Sydney on April 7?"
    (Tests: ranking — Jetstar $399 is cheapest)

14. "I have a $500 budget for a one-way flight from Saigon to Sydney. What are my options?"
    (Tests: price filter — only Jetstar $399 and Vietnam Airlines $500 fit on 2026-04-07)

15. "Compare Vietnam Airlines and Qantas from SGN to SYD on April 7"
    (Tests: multi-row comparison — VN $500/1stop vs QF $604/1stop)

---

### Follow-up / context

16. Ask first: "Flights from Saigon to Tokyo tomorrow"
    Then follow up: "What about the day after?"
    (Tests: date shift with inherited route, should query 2026-04-08)

17. Ask first: "Flights from SGN to SYD on April 7"
    Then follow up: "Which one has the earliest departure?"
    (Tests: context retention — Vietnam Airlines departs 00:05)

---

### Edge cases / hallucination checks

18. "Find me a flight from Saigon to London"
    (Tests: no data for SGN→LHR — bot should say no results and suggest available routes)

19. "Are there any hotels in Tokyo?"
    (Tests: Tokyo is in hotel DB — should return results for Tokyo)

20. "Book me a flight" (no details)
    (Tests: general/incomplete query handling — bot should ask for origin, destination, date)
