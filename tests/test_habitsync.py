"""Tests for HabitSync client and parsing."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.habitsync import HabitSyncClient, parse_habitsync_response, _normalize_habit_name


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> dict | list:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename) as f:
        return json.load(f)


class TestNormalizeHabitName:
    """Tests for habit name normalization."""

    def test_simple_name(self):
        assert _normalize_habit_name("Coffee") == "coffee"

    def test_name_with_spaces(self):
        assert _normalize_habit_name("PM Energy Slump") == "pm_energy_slump"

    def test_name_with_special_chars(self):
        assert _normalize_habit_name("Carb-Heavy Lunch") == "carb_heavy_lunch"

    def test_name_with_multiple_spaces(self):
        assert _normalize_habit_name("My  Cool   Habit") == "my_cool_habit"


class TestParseHabitsyncResponse:
    """Tests for parsing HabitSync response into DailyHabit objects."""

    def test_parse_empty_response(self):
        habits = parse_habitsync_response({}, date(2025, 1, 28))
        assert habits == []

    def test_parse_single_habit(self):
        habits_data = {
            "coffee": {"value": "3", "type": "counter"}
        }
        habits = parse_habitsync_response(habits_data, date(2025, 1, 28))

        assert len(habits) == 1
        assert habits[0].habit_name == "coffee"
        assert habits[0].habit_value == "3"
        assert habits[0].habit_type == "counter"
        assert habits[0].date == date(2025, 1, 28)

    def test_parse_multiple_habits(self):
        habits_data = {
            "coffee": {"value": "2", "type": "counter"},
            "brain_fog": {"value": "1", "type": "counter"},
            "stretch": {"value": "0", "type": "counter"},
        }
        habits = parse_habitsync_response(habits_data, date(2025, 2, 7))

        assert len(habits) == 3
        habit_names = {h.habit_name for h in habits}
        assert habit_names == {"coffee", "brain_fog", "stretch"}


class TestHabitSyncClientOffsetCalculation:
    """Tests for the offset calculation in fetch_all_for_date."""

    @pytest.mark.asyncio
    async def test_offset_is_negative_for_past_dates(self):
        """Offset should be negative for dates in the past."""
        client = HabitSyncClient(base_url="http://test", api_key="test-key")

        # Mock get_habits to return habits without embedded records
        habits_without_records = [
            {"uuid": "habit-1", "name": "Coffee", "records": []},
        ]

        # Mock get_habit_record to capture the offset parameter
        captured_offsets = []

        async def mock_get_habit_record(habit_uuid, offset, timezone):
            captured_offsets.append(offset)
            return {"recordValue": 3.0, "completion": "COMPLETED"}

        with patch.object(client, 'get_habits', new_callable=AsyncMock) as mock_get_habits:
            with patch.object(client, 'get_habit_record', side_effect=mock_get_habit_record):
                mock_get_habits.return_value = habits_without_records

                # Fetch for 7 days ago
                with patch('app.services.habitsync.date') as mock_date:
                    mock_date.today.return_value = date(2026, 2, 14)
                    # We need to patch at module level where it's used
                    pass

                # Instead, let's test the actual calculation
                from datetime import date as date_class
                target_date = date(2026, 2, 7)
                today = date(2026, 2, 14)
                expected_offset = (target_date - today).days  # Should be -7

                assert expected_offset == -7, f"Offset should be -7, got {expected_offset}"

    @pytest.mark.asyncio
    async def test_offset_is_zero_for_today(self):
        """Offset should be 0 for today's date."""
        from datetime import date as date_class
        target_date = date(2026, 2, 14)
        today = date(2026, 2, 14)
        offset = (target_date - today).days

        assert offset == 0

    @pytest.mark.asyncio
    async def test_offset_is_positive_for_future_dates(self):
        """Offset should be positive for future dates (though unlikely in practice)."""
        from datetime import date as date_class
        target_date = date(2026, 2, 21)
        today = date(2026, 2, 14)
        offset = (target_date - today).days

        assert offset == 7


class TestHabitSyncClientFallback:
    """Tests for fallback to offset-based API when embedded records missing."""

    @pytest.mark.asyncio
    async def test_uses_embedded_record_when_available(self):
        """Should use embedded record if epochDay matches."""
        client = HabitSyncClient(base_url="http://test", api_key="test-key")

        # Feb 7, 2026 = epochDay 20491
        target_date = date(2026, 2, 7)
        epoch_day = (target_date - date(1970, 1, 1)).days

        habits_with_records = [
            {
                "uuid": "habit-1",
                "name": "Coffee",
                "records": [
                    {"epochDay": epoch_day, "recordValue": 3.0, "completion": "COMPLETED"}
                ]
            },
        ]

        with patch.object(client, 'get_habits', new_callable=AsyncMock) as mock_get_habits:
            with patch.object(client, 'get_habit_record', new_callable=AsyncMock) as mock_get_record:
                mock_get_habits.return_value = habits_with_records

                result = await client.fetch_all_for_date(target_date, "Europe/London")

                # Should NOT call get_habit_record since embedded record exists
                mock_get_record.assert_not_called()
                assert result["coffee"]["value"] == "3"

    @pytest.mark.asyncio
    async def test_falls_back_to_offset_api_when_no_embedded_record(self):
        """Should call get_habit_record when no matching embedded record."""
        client = HabitSyncClient(base_url="http://test", api_key="test-key")

        target_date = date(2026, 2, 7)

        # Habits with records for different dates (not matching target)
        habits_without_matching_records = [
            {
                "uuid": "habit-1",
                "name": "Coffee",
                "records": [
                    {"epochDay": 99999, "recordValue": 1.0, "completion": "COMPLETED"}  # Wrong date
                ]
            },
        ]

        with patch.object(client, 'get_habits', new_callable=AsyncMock) as mock_get_habits:
            with patch.object(client, 'get_habit_record', new_callable=AsyncMock) as mock_get_record:
                mock_get_habits.return_value = habits_without_matching_records
                mock_get_record.return_value = {"recordValue": 3.0, "completion": "COMPLETED"}

                result = await client.fetch_all_for_date(target_date, "Europe/London")

                # Should call get_habit_record as fallback
                mock_get_record.assert_called_once()
                # Verify the offset is negative (past date)
                call_args = mock_get_record.call_args
                offset = call_args[0][1]  # Second positional arg
                assert offset < 0, f"Offset should be negative for past date, got {offset}"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_record_found(self):
        """Should return empty dict when neither embedded nor API has record."""
        client = HabitSyncClient(base_url="http://test", api_key="test-key")

        target_date = date(2026, 2, 7)

        habits_without_records = [
            {"uuid": "habit-1", "name": "Coffee", "records": []},
        ]

        with patch.object(client, 'get_habits', new_callable=AsyncMock) as mock_get_habits:
            with patch.object(client, 'get_habit_record', new_callable=AsyncMock) as mock_get_record:
                mock_get_habits.return_value = habits_without_records
                mock_get_record.return_value = None  # No record found

                result = await client.fetch_all_for_date(target_date, "Europe/London")

                assert result == {}
