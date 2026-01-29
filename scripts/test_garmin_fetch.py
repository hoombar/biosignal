#!/usr/bin/env python3
"""
One-time script to fetch real Garmin API responses and save as test fixtures.
Run this once with real credentials to capture the actual API response shapes.
"""

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.services.garmin import GarminClient


async def main():
    settings = get_settings()
    client = GarminClient(settings.garmin_email, settings.garmin_password, settings.garmin_token_dir)

    # Fetch yesterday's data
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching Garmin data for {yesterday}...")

    await client.connect()
    data = await client.fetch_all_for_date(yesterday)

    # Also fetch recent activities
    activities = await client.fetch_activities(start=0, limit=10)
    data["activities"] = activities

    # Save to fixtures directory
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    for endpoint, response in data.items():
        if response is not None:
            filename = fixtures_dir / f"garmin_{endpoint}.json"
            with open(filename, "w") as f:
                json.dump(response, f, indent=2, default=str)
            print(f"Saved {endpoint} data to {filename}")
            print(f"  Keys: {list(response.keys()) if isinstance(response, dict) else 'list'}")
        else:
            print(f"No data for {endpoint}")

    print("\nDone! Check tests/fixtures/ for captured responses.")


if __name__ == "__main__":
    asyncio.run(main())
