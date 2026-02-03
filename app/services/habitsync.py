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
                headers={"X-Api-Key": self.api_key},
                timeout=30.0
            )
        return self.client

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def get_habits(self) -> list[dict]:
        """Get list of all habits."""
        try:
            client = await self._get_client()
            # Try user-scoped endpoint first (newer API)
            response = await client.get(f"{self.base_url}/api/user/habit")
            response.raise_for_status()
            habits = response.json()
            logger.info(f"Fetched {len(habits)} habits from HabitSync")
            return habits
        except httpx.HTTPStatusError as e:
            # If 404, try the old endpoint
            if e.response.status_code == 404:
                try:
                    logger.info("Trying fallback endpoint /api/habit")
                    response = await client.get(f"{self.base_url}/api/habit")
                    response.raise_for_status()
                    habits = response.json()
                    logger.info(f"Fetched {len(habits)} habits from HabitSync (fallback)")
                    return habits
                except Exception as fallback_error:
                    logger.error(f"Fallback endpoint also failed: {fallback_error}")
                    return []
            logger.error(f"HTTP error fetching habits: {e}")
            logger.error(f"Response status: {e.response.status_code}, URL: {e.request.url}")
            logger.error(f"Response body: {e.response.text[:500]}")
            return []
        except httpx.ConnectError as e:
            logger.error(f"Connection error to HabitSync: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching habits: {e}")
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

        # Calculate offset from today
        today = date_class.today()
        offset = (today - target_date).days

        logger.info(f"Fetching HabitSync data for {target_date} (offset={offset})")

        # Get all habits
        habits = await self.get_habits()

        # Filter out archived habits
        active_habits = [h for h in habits if not h.get("archived", False)]

        # Fetch records for each habit
        results = {}
        for habit in active_habits:
            habit_uuid = habit.get("uuid")
            habit_name = habit.get("name")
            habit_type = habit.get("type")

            if habit_uuid and habit_name:
                record = await self.get_habit_record(habit_uuid, offset, timezone)
                if record:
                    normalized_name = _normalize_habit_name(habit_name)
                    record_value = record.get("recordValue")
                    completion = record.get("completion", False)

                    # Store the value based on habit type
                    if habit_type == "YesNoHabit":
                        results[normalized_name] = {
                            "value": "true" if completion else "false",
                            "type": "boolean"
                        }
                    elif habit_type == "CounterHabit":
                        results[normalized_name] = {
                            "value": str(int(record_value)) if record_value else "0",
                            "type": "counter"
                        }
                    else:
                        results[normalized_name] = {
                            "value": str(record_value) if record_value else "",
                            "type": "other"
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
