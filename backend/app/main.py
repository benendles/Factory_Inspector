"""FastAPI application entry point for Factory Inspector."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.equipment import router as equipment_router
from app.api.routes.inspections import router as inspections_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.health import router as health_router
from app.api.routes.simulator import router as simulator_router
from app.config import settings
from app.database.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI-assisted factory inspection, anomaly investigation, "
        "maintenance approval, and verification API."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/", tags=["General"])
def root():
    """Return basic API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Check application and database connectivity."""
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

app.include_router(
    health_router
)
app.include_router(
    equipment_router,
    prefix=settings.api_prefix,
)
app.include_router(
    inspections_router, 
    prefix=settings.api_prefix)
app.include_router(
    approvals_router,
    prefix=settings.api_prefix,
)
app.include_router(
    incidents_router,
    prefix=settings.api_prefix,
)
app.include_router(
    simulator_router, 
    prefix=settings.api_prefix)