"""Sync log model for tracking sync operations."""

from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, JSON

from app.core.database import Base


class SyncLog(Base):
    """Log of sync operations."""

    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String, nullable=False)  # "garmin", "habitsync", "all"
    date_synced = Column(Date, nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)  # "success", "failed", "partial"
    details = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
