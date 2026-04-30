from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import sessionmaker


class BaseRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _serialize_datetime(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value
