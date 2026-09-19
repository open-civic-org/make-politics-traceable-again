from __future__ import annotations

from collections.abc import Generator

from packages.db.session import get_session_factory
from sqlalchemy.orm import Session


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
