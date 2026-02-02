import asyncio
import os
import logging
from datetime import date
from typing import Any, Optional
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError, GarminConnectConnectionError

logger = logging.getLogger(__name__)


class GarminMfaRequiredError(Exception):
    """Raised when Garmin login requires MFA and cannot proceed non-interactively."""
    pass


class GarminClient:
    """Async wrapper for Garmin Connect API."""

    def __init__(self, email: str, password: str, token_dir: str):
        self.email = email
        self.password = password
        self.token_dir = token_dir
        self.client: Optional[Garmin] = None

    async def connect(self) -> None:
        """Connect to Garmin and authenticate."""
        os.makedirs(self.token_dir, exist_ok=True)

        def _connect():
            # Try loading saved tokens first
            try:
                client = Garmin(self.email, self.password)
                client.login(self.token_dir)
                logger.info("Logged in using saved tokens")
                return client
            except FileNotFoundError:
                logger.info("No saved tokens found")
            except Exception as token_err:
                logger.info(f"Saved tokens invalid: {token_err}")

            raise GarminMfaRequiredError(
                "No valid Garmin tokens found. "
                "Please complete authentication setup at /setup/garmin"
            )

        try:
            self.client = await asyncio.to_thread(_connect)
            logger.info("Connected to Garmin successfully")
        except GarminConnectAuthenticationError as e:
            logger.error(f"Garmin authentication failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Garmin connection error: {e}")
            raise

    async def _call_with_retry(self, func, *args, max_retries: int = 3, **kwargs) -> Any:
        """Call a Garmin API function with retry logic."""
        if self.client is None:
            await self.connect()

        for attempt in range(max_retries):
            try:
                result = await asyncio.to_thread(func, *args, **kwargs)
                return result
            except GarminConnectTooManyRequestsError as e:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except GarminConnectAuthenticationError as e:
                logger.warning("Authentication error, attempting re-login")
                await self.connect()
                if attempt < max_retries - 1:
                    continue
                else:
                    raise
            except GarminConnectConnectionError as e:
                wait_time = 2 ** attempt
                logger.warning(f"Connection error, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    raise

    async def fetch_sleep(self, date_str: str) -> Optional[dict]:
        """Fetch sleep data for a specific date."""
        try:
            return await self._call_with_retry(self.client.get_sleep_data, date_str)
        except Exception as e:
            logger.error(f"Failed to fetch sleep data for {date_str}: {e}")
            return None

    async def fetch_heart_rate(self, date_str: str) -> Optional[dict]:
        """Fetch heart rate data for a specific date."""
        try:
            return await self._call_with_retry(self.client.get_heart_rates, date_str)
        except Exception as e:
            logger.error(f"Failed to fetch heart rate for {date_str}: {e}")
            return None

    async def fetch_hrv(self, date_str: str) -> Optional[dict]:
        """Fetch HRV data for a specific date (may return None if not available)."""
        try:
            return await self._call_with_retry(self.client.get_hrv_data, date_str)
        except Exception as e:
            logger.debug(f"HRV data not available for {date_str}: {e}")
            return None

    async def fetch_body_battery(self, date_str: str) -> Optional[list]:
        """Fetch body battery data for a specific date."""
        try:
            # get_body_battery requires start and end date (same date for single day)
            return await self._call_with_retry(self.client.get_body_battery, date_str, date_str)
        except Exception as e:
            logger.error(f"Failed to fetch body battery for {date_str}: {e}")
            return None

    async def fetch_stress(self, date_str: str) -> Optional[dict]:
        """Fetch stress data for a specific date."""
        try:
            return await self._call_with_retry(self.client.get_all_day_stress, date_str)
        except Exception as e:
            logger.error(f"Failed to fetch stress for {date_str}: {e}")
            return None

    async def fetch_spo2(self, date_str: str) -> Optional[dict]:
        """Fetch SpO2 data for a specific date (may return None if not available)."""
        try:
            return await self._call_with_retry(self.client.get_spo2_data, date_str)
        except Exception as e:
            logger.debug(f"SpO2 data not available for {date_str}: {e}")
            return None

    async def fetch_steps(self, date_str: str) -> Optional[dict]:
        """Fetch steps data for a specific date."""
        try:
            return await self._call_with_retry(self.client.get_steps_data, date_str)
        except Exception as e:
            logger.error(f"Failed to fetch steps for {date_str}: {e}")
            return None

    async def fetch_activities(self, start: int = 0, limit: int = 20) -> Optional[list]:
        """Fetch activities list."""
        try:
            return await self._call_with_retry(self.client.get_activities, start, limit)
        except Exception as e:
            logger.error(f"Failed to fetch activities: {e}")
            return None

    async def fetch_all_for_date(self, date_str: str) -> dict[str, Any]:
        """Fetch all data types for a specific date."""
        logger.info(f"Fetching all Garmin data for {date_str}")

        results = {}

        # Fetch all endpoints - don't let one failure block others
        results["sleep"] = await self.fetch_sleep(date_str)
        results["heart_rate"] = await self.fetch_heart_rate(date_str)
        results["hrv"] = await self.fetch_hrv(date_str)
        results["body_battery"] = await self.fetch_body_battery(date_str)
        results["stress"] = await self.fetch_stress(date_str)
        results["spo2"] = await self.fetch_spo2(date_str)
        results["steps"] = await self.fetch_steps(date_str)

        return results
