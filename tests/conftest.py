"""Shared test fixtures for the biosignal test suite."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.core.database import Base
# Import all models so their metadata is registered on Base
import app.models.database  # noqa: F401
import app.models.sync_log  # noqa: F401


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
