import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Locate Factory_Inspector/.env from this test file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

if not ENV_FILE.is_file():
    raise FileNotFoundError(f"Environment file not found at: {ENV_FILE}")

# Load variables from the existing project-root .env file.
load_dotenv(ENV_FILE, override=True)

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        f"DATABASE_URL is missing or empty in {ENV_FILE}"
    )

# Normalize the URL for the psycopg 3 driver.
parsed_url = make_url(database_url)

if parsed_url.drivername in ("postgresql", "postgres"):
    parsed_url = parsed_url.set(drivername="postgresql+psycopg")

engine = create_engine(
    parsed_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), current_user, version()")
        )
        database, user, version = result.one()

        print("Successfully connected to Supabase!")
        print(f"Database: {database}")
        print(f"Database user: {user}")
        print(f"PostgreSQL version: {version.split(',')[0]}")

except Exception as exc:
    print("Could not connect to Supabase.")
    print(f"Error type: {type(exc).__name__}")
    print(f"Details: {exc}")

finally:
    engine.dispose()