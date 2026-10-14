import os
from pathlib import Path
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

# Load environment variables from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check the .env file in the project root."
    )

# Normalize the PostgreSQL driver for Psycopg 3.
database_url = make_url(DATABASE_URL)

if database_url.drivername in ("postgresql", "postgres"):
    database_url = database_url.set(drivername="postgresql+psycopg")

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session
    and closes it after the request.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """
    Create tables defined in models.py.

    Intended for initial development only. Use database migrations
    for production schema changes.
    """
    from app.database.models import Base

    Base.metadata.create_all(bind=engine)