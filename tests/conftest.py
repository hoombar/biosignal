"""Shared test fixtures for the biosignal test suite."""

from datetime import date as _date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.core.database import Base
# Import all models so their metadata is registered on Base
import app.models.database  # noqa: F401
import app.models.sync_log  # noqa: F401
from app.models.database import DailyHabit, Habit


async def ensure_habit(session: AsyncSession, name: str, habit_type: str = "binary") -> Habit:
    """Get-or-create a Habit row for tests. Idempotent on name."""
    result = await session.execute(select(Habit).where(Habit.name == name))
    habit = result.scalar_one_or_none()
    if habit is not None:
        return habit
    habit = Habit(name=name, habit_type=habit_type)
    session.add(habit)
    await session.flush()
    return habit


async def log_habit(
    session: AsyncSession,
    name: str,
    target_date: _date,
    value: int,
    habit_type: str = "binary",
) -> DailyHabit:
    """Get-or-create a Habit, then add a DailyHabit row for the given date."""
    habit = await ensure_habit(session, name, habit_type)
    daily = DailyHabit(date=target_date, habit_id=habit.id, habit_value=value)
    session.add(daily)
    return daily


@pytest_asyncio.fixture
async def async_session():
    """
    Provide an in-memory SQLite async session for tests.

    Creates all tables before the test, drops them after. Each test gets
    a clean database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
