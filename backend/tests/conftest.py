"""Test-wide protection against accidental live services."""

import os

import pytest


# Set before test modules import the workflow singleton. Unit tests inject
# fakes and must never open the configured production PostgreSQL connection.
os.environ["FACTORY_WORKFLOW_CHECKPOINTER"] = "memory"
os.environ["WORKFLOW_ARTIFACT_PERSISTENCE"] = "false"


@pytest.fixture(autouse=True)
def disable_live_procurement_providers(monkeypatch):
    """Require an explicit injected fake before any test can call providers."""

    # A legacy database smoke test loads .env with override=True. Reapply the
    # test isolation policy for every individual test so later graph tests
    # cannot accidentally write to the configured production database.
    monkeypatch.setenv("FACTORY_WORKFLOW_CHECKPOINTER", "memory")
    monkeypatch.setenv("WORKFLOW_ARTIFACT_PERSISTENCE", "false")
    monkeypatch.setenv("TAVILY_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("AMD_REPAIR_DIAGNOSIS_ENABLED", "false")
    monkeypatch.setenv("EVOLUS_ENABLED", "false")
