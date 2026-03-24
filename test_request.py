"""Quick test script — run with: python test_request.py"""

import httpx
import json
import asyncio


SAMPLE_REQUESTS = [
    {
        "name": "Standard employee, Tokyo business trip (cherry blossom season)",
        "payload": {
            "traveler": {
                "employee_id": "EMP-001",
                "name": "Alice Johnson",
                "department": "Engineering",
                "org_policy_tier": "standard",
            },
            "origin": "SFO",
            "destination": "Tokyo",
            "departure_date": "2026-04-01",
            "return_date": "2026-04-05",
            "trip_purpose": "business",
            "preferences": ["non_stop", "hotel_gym"],
        },
    },
    {
        "name": "Executive, New York conference",
        "payload": {
            "traveler": {
                "employee_id": "EMP-002",
                "name": "Bob Smith",
                "department": "Sales",
                "org_policy_tier": "executive",
            },
            "origin": "SFO",
            "destination": "New York",
            "departure_date": "2026-04-01",
            "return_date": "2026-04-03",
            "trip_purpose": "conference",
            "preferences": ["window_seat"],
        },
    },

    {
        "name": "Standard employee, Bangkok during Songkran (edge case)",
        "payload": {
            "traveler": {
                "employee_id": "EMP-003",
                "name": "Carol Lee",
                "department": "Marketing",
                "org_policy_tier": "standard",
            },
            "origin": "SFO",
            "destination": "Bangkok",
            "departure_date": "2026-04-13",
            "return_date": "2026-04-16",
            "trip_purpose": "business",
            "preferences": [],
        },
    },
]


async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=60.0) as client:
        # Health check
        resp = await client.get("/health")
        print(f"Health: {resp.json()}\n")

        for req in SAMPLE_REQUESTS:
            print(f"{'='*60}")
            print(f"TEST: {req['name']}")
            print(f"{'='*60}")
            resp = await client.post("/recommend", json=req["payload"])
            if resp.status_code == 200:
                result = resp.json()
                print(f"Route:      {result['route']}")
                print(f"Confidence: {result['confidence']}")
                print(f"Risk flags: {result['risk_flags']}")
                print(f"Explanation: {result['explanation'][:300]}")
                if result["options"]:
                    opt = result["options"][0]
                    print(f"Flight:     {opt['flight']['airline']} ${opt['flight']['price']}")
                    print(f"Hotel:      {opt['hotel']['name']} ${opt['hotel']['price_per_night']}/night")
                    print(f"Total:      ${opt['total_price']}")
                    print(f"Policy OK:  {opt['policy_compliant']}")
                    print(f"Inventory:  {opt['inventory_available']}")
                print(f"Verification: {result['verification_notes'][:200]}")
            else:
                print(f"ERROR {resp.status_code}: {resp.text}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
