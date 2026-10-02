from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_session_factory(url: str | None = None):
    engine = create_engine(url or get_settings().database_url, future=True)
    return sessionmaker(engine, class_=Session, expire_on_commit=False), engine


SessionLocal, engine = make_session_factory()
