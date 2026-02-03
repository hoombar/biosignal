"""HabitSync API client."""

import logging
from datetime import date
from typing import Any, Optional
import httpx
import re

from app.models.database import DailyHabit

logger = logging.getLogger(__name__)


def _normalize_habit_name(name: str) -> str:
    """Normalize habit name to snake_case."""
    # Replace spaces and special chars with underscores, lowercase
    normalized = re.sub(r'[^a-z0-9]+', '_', name.lower())
    return normalized.strip('_')


class HabitSyncClient:
    """Async client for HabitSync API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                headers={"X-API-Key": self.api_key},
                timeout=30.0
            )
        return self.client

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    def _parse_json_response(self, response: httpx.Response, context: str) -> list[dict] | None:
        """Safely parse JSON response, returning None on failure."""
        if not response.text:
            logger.error(f"{context}: Empty response body")
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            logger.error(f"{context}: Unexpected content-type '{content_type}', body: {response.text[:200]}")
            return None

        try:
            return response.json()
        except Exception as e:
            logger.error(f"{context}: Failed to parse JSON: {e}, body: {response.text[:200]}")
            return None

    async def _try_get_habits(self, client: httpx.AsyncClient, endpoint: str) -> list[dict] | None:
        """Try to fetch habits from a specific endpoint. Returns None if endpoint doesn't work."""
        try:
            response = await client.get(f"{self.base_url}{endpoint}")
            response.raise_for_status()
            habits = self._parse_json_response(response, f"get_habits ({endpoint})")
            if habits is not None:
                logger.info(f"Fetched {len(habits)} habits from HabitSync using {endpoint}")
            return habits
        except httpx.HTTPStatusError as e:
            logger.warning(f"Endpoint {endpoint} returned HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.warning(f"Endpoint {endpoint} failed: {e}")
            return None

    async def get_habits(self) -> list[dict]:
        """Get list of all habits."""
        client = await self._get_client()

        # Try multiple possible endpoints - HabitSync API structure varies by version
        endpoints = [
            "/api/habit/list",  # Correct endpoint per OpenAPI spec
            "/api/user/habit",  # Alternate endpoint
            "/api/habit",       # Older global API
        ]

        for endpoint in endpoints:
            habits = await self._try_get_habits(client, endpoint)
            if habits is not None:
                return habits
            logger.info(f"Endpoint {endpoint} didn't work, trying next...")

        logger.error("All HabitSync API endpoints failed. Check HABITSYNC_URL and HABITSYNC_API_KEY configuration.")
        return []

    async def get_habit_record(self, habit_uuid: str, offset: int, timezone: str) -> Optional[dict]:
        """
        Get habit record for a specific day.

        Args:
            habit_uuid: UUID of the habit
            offset: Days from today (0=today, 1=yesterday, etc.)
            timezone: Timezone string (e.g., "Europe/London")
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/api/record/{habit_uuid}/simple",
                params={"offset": offset, "timeZone": timezone}
            )
            response.raise_for_status()
            if not response.text:
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No record for this day
                return None
            logger.error(f"HTTP error fetching habit record: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching habit record: {e}")
            return None

    async def fetch_all_for_date(self, target_date: date, timezone: str) -> dict[str, Any]:
        """
        Fetch all habit records for a specific date.

        Returns:
            Dict mapping normalized habit names to their values.
        """
        from datetime import date as date_class

        # Calculate epoch day for target date (days since 1970-01-01)
        epoch_day = (target_date - date_class(1970, 1, 1)).days

        logger.info(f"Fetching HabitSync data for {target_date} (epochDay={epoch_day})")

        # Get all habits (includes embedded records)
        habits = await self.get_habits()

        results = {}
        for habit in habits:
            habit_name = habit.get("name")
            is_negative = habit.get("progressComputation", {}).get("isNegative", False)

            if not habit_name:
                continue

            normalized_name = _normalize_habit_name(habit_name)

            # Find record for target date in embedded records
            records = habit.get("records", [])
            target_record = None
            for record in records:
                if record.get("epochDay") == epoch_day:
                    target_record = record
                    break

            if target_record:
                record_value = target_record.get("recordValue", 0)
                completion = target_record.get("completion", "MISSED")

                # Determine type and value based on habit configuration
                if is_negative:
                    # Negative habits: track occurrences (0 = good, >0 = bad)
                    results[normalized_name] = {
                        "value": str(int(record_value)) if record_value else "0",
                        "type": "counter"
                    }
                else:
                    # Positive habits: completion status
                    is_completed = completion in ("COMPLETED", "COMPLETED_BY_OTHER_RECORDS")
                    results[normalized_name] = {
                        "value": str(int(record_value)) if record_value else ("1" if is_completed else "0"),
                        "type": "counter"
                    }

        logger.info(f"Fetched {len(results)} habit records for {target_date}")
        return results


def parse_habitsync_response(habits_data: dict[str, Any], date: date) -> list[DailyHabit]:
    """
    Parse HabitSync data into DailyHabit objects.

    Args:
        habits_data: Dict from fetch_all_for_date (habit_name -> {value, type})
        date: The date these habits are for
    """
    habit_rows = []

    for habit_name, data in habits_data.items():
        habit_rows.append(DailyHabit(
            date=date,
            habit_name=habit_name,
            habit_value=data["value"],
            habit_type=data["type"]
        ))

    logger.debug(f"Parsed {len(habit_rows)} daily habits for {date}")
    return habit_rows
