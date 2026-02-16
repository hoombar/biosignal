"""Tests for SpO2 feature computation."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.models.database import Spo2Sample, SleepSession
from app.services.features import compute_spo2_features


def create_spo2_sample(timestamp: datetime, value: int) -> Spo2Sample:
    """Create a mock SpO2 sample."""
    sample = MagicMock(spec=Spo2Sample)
    sample.timestamp = timestamp
    sample.spo2_value = value
    return sample


def create_sleep_session(sleep_start: datetime, sleep_end: datetime) -> SleepSession:
    """Create a mock sleep session."""
    session = MagicMock(spec=SleepSession)
    session.sleep_start = sleep_start
    session.sleep_end = sleep_end
    return session


class TestComputeSpo2Features:
    """Tests for compute_spo2_features function."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_sleep_session(self):
        """Should return empty dict if no sleep session exists."""
        from zoneinfo import ZoneInfo

        session = AsyncMock()
        # Mock execute to return no sleep session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await compute_spo2_features(session, date(2025, 1, 28), ZoneInfo("Europe/London"))

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_spo2_samples(self):
        """Should return empty dict if no SpO2 samples during sleep."""
        from zoneinfo import ZoneInfo

        session = AsyncMock()

        # First call returns sleep session
        sleep = create_sleep_session(
            datetime(2025, 1, 28, 0, 0),
            datetime(2025, 1, 28, 7, 0)
        )
        mock_sleep_result = MagicMock()
        mock_sleep_result.scalar_one_or_none.return_value = sleep

        # Second call returns no SpO2 samples
        mock_spo2_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_spo2_result.scalars.return_value = mock_scalars

        session.execute.side_effect = [mock_sleep_result, mock_spo2_result]

        result = await compute_spo2_features(session, date(2025, 1, 28), ZoneInfo("Europe/London"))

        assert result == {}

    @pytest.mark.asyncio
    async def test_computes_overnight_statistics(self):
        """Should compute avg, min, max for SpO2 samples."""
        from zoneinfo import ZoneInfo

        session = AsyncMock()

        # Sleep session
        sleep = create_sleep_session(
            datetime(2025, 1, 28, 0, 0),
            datetime(2025, 1, 28, 7, 0)
        )
        mock_sleep_result = MagicMock()
        mock_sleep_result.scalar_one_or_none.return_value = sleep

        # SpO2 samples: 95, 96, 97, 98, 96
        samples = [
            create_spo2_sample(datetime(2025, 1, 28, 1, 0), 95),
            create_spo2_sample(datetime(2025, 1, 28, 2, 0), 96),
            create_spo2_sample(datetime(2025, 1, 28, 3, 0), 97),
            create_spo2_sample(datetime(2025, 1, 28, 4, 0), 98),
            create_spo2_sample(datetime(2025, 1, 28, 5, 0), 96),
        ]
        mock_spo2_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = samples
        mock_spo2_result.scalars.return_value = mock_scalars

        session.execute.side_effect = [mock_sleep_result, mock_spo2_result]

        result = await compute_spo2_features(session, date(2025, 1, 28), ZoneInfo("Europe/London"))

        assert result["spo2_overnight_avg"] == pytest.approx(96.4, rel=0.01)
        assert result["spo2_overnight_min"] == 95
        assert result["spo2_overnight_max"] == 98
        assert result["spo2_dips_below_94"] == 0

    @pytest.mark.asyncio
    async def test_counts_dips_below_94(self):
        """Should count readings below 94% threshold."""
        from zoneinfo import ZoneInfo

        session = AsyncMock()

        # Sleep session
        sleep = create_sleep_session(
            datetime(2025, 1, 28, 0, 0),
            datetime(2025, 1, 28, 7, 0)
        )
        mock_sleep_result = MagicMock()
        mock_sleep_result.scalar_one_or_none.return_value = sleep

        # SpO2 samples with dips: 96, 93, 92, 95, 91
        samples = [
            create_spo2_sample(datetime(2025, 1, 28, 1, 0), 96),
            create_spo2_sample(datetime(2025, 1, 28, 2, 0), 93),  # dip
            create_spo2_sample(datetime(2025, 1, 28, 3, 0), 92),  # dip
            create_spo2_sample(datetime(2025, 1, 28, 4, 0), 95),
            create_spo2_sample(datetime(2025, 1, 28, 5, 0), 91),  # dip
        ]
        mock_spo2_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = samples
        mock_spo2_result.scalars.return_value = mock_scalars

        session.execute.side_effect = [mock_sleep_result, mock_spo2_result]

        result = await compute_spo2_features(session, date(2025, 1, 28), ZoneInfo("Europe/London"))

        assert result["spo2_dips_below_94"] == 3
        assert result["spo2_overnight_min"] == 91

    @pytest.mark.asyncio
    async def test_handles_single_sample(self):
        """Should handle edge case of single SpO2 reading."""
        from zoneinfo import ZoneInfo

        session = AsyncMock()

        sleep = create_sleep_session(
            datetime(2025, 1, 28, 0, 0),
            datetime(2025, 1, 28, 7, 0)
        )
        mock_sleep_result = MagicMock()
        mock_sleep_result.scalar_one_or_none.return_value = sleep

        samples = [create_spo2_sample(datetime(2025, 1, 28, 3, 0), 97)]
        mock_spo2_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = samples
        mock_spo2_result.scalars.return_value = mock_scalars

        session.execute.side_effect = [mock_sleep_result, mock_spo2_result]

        result = await compute_spo2_features(session, date(2025, 1, 28), ZoneInfo("Europe/London"))

        assert result["spo2_overnight_avg"] == 97
        assert result["spo2_overnight_min"] == 97
        assert result["spo2_overnight_max"] == 97
        assert result["spo2_dips_below_94"] == 0
