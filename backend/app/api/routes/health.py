"""Health-check endpoints for Factory Inspector."""

from fastapi import APIRouter
from sqlalchemy import text

from app.database.session import engine

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Check API availability and database connectivity."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except Exception:
        return {
            "status": "unhealthy",
            "database": "unavailable",
        }