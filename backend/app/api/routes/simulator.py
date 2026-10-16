"""API endpoints for the Factory Inspector simulator and agent workflow."""

import os
import tempfile
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.services.factory_workflow_service import (
    factory_workflow_service,
)
from app.simulator.factory_simulator import (
    get_available_scenarios,
    run_scenario,
    simulate_maintenance,
)


router = APIRouter(
    prefix="/simulator",
    tags=["Factory Simulator"],
)

MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MEDIA_TYPES = {
    "image/jpeg": (".jpg", "JPEG"),
    "image/png": (".png", "PNG"),
    "image/webp": (".webp", "WEBP"),
}


async def _store_validated_workflow_image(
    image: UploadFile,
) -> tuple[str, dict[str, Any]]:
    """Store one validated image temporarily for the synchronous workflow run."""

    content_type = (image.content_type or "").lower()
    allowed = ALLOWED_IMAGE_MEDIA_TYPES.get(content_type)

    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG, PNG, or WEBP inspection image.",
        )

    content = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The inspection image is empty.",
        )

    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The inspection image exceeds the 10 MiB size limit.",
        )

    suffix, expected_format = allowed
    descriptor, temporary_path = tempfile.mkstemp(
        prefix="factory-inspector-evidence-",
        suffix=suffix,
    )

    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)

        try:
            with Image.open(temporary_path) as uploaded_image:
                actual_format = uploaded_image.format
                uploaded_image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded file is not a readable image.",
            ) from exc

        if actual_format != expected_format:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded content does not match its image type.",
            )

        return temporary_path, {
            "status": "available",
            "source": "uploaded_image",
            "content_type": content_type,
            "size_bytes": len(content),
        }

    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
    finally:
        await image.close()


# ---------------------------------------------------------------------------
# REQUEST SCHEMAS
# ---------------------------------------------------------------------------


class ScenarioRunRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=100)


class MaintenanceSimulationRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=100)


class WorkflowStartRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    machine_id: str = Field(min_length=1, max_length=100)


class WorkflowApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]

    approval_user: str = Field(
        min_length=1,
        max_length=150,
        description="Identity of the person making the approval decision.",
    )

    approval_comment: str | None = Field(
        default=None,
        max_length=1000,
    )


class PhysicalIdentityVerificationRequest(BaseModel):
    decision: Literal["confirmed", "rejected"]

    reviewer: str = Field(
        min_length=1,
        max_length=150,
        description=(
            "Reviewer recording the physical identity decision. "
            "This field is not authentication."
        ),
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
    )

    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Evidence supporting the decision, such as a nameplate "
            "inspection reference. Do not include secrets."
        ),
    )


# ---------------------------------------------------------------------------
# SIMULATOR ENDPOINTS
# ---------------------------------------------------------------------------


@router.get("/scenarios")
def list_simulator_scenarios():
    return {
        "scenarios": get_available_scenarios(),
        "thresholds_are_simulated": True,
    }


@router.post("/run")
def execute_simulation(request: ScenarioRunRequest):
    try:
        return run_scenario(request.scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/maintenance")
def execute_maintenance_simulation(
    request: MaintenanceSimulationRequest,
):
    try:
        return simulate_maintenance(request.scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# WORKFLOW ENDPOINTS
# ---------------------------------------------------------------------------


@router.post("/workflow", status_code=200)
def start_factory_workflow(request: WorkflowStartRequest):
    try:
        return factory_workflow_service.start_workflow(
            scenario_id=request.scenario_id,
            machine_id=request.machine_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not start the factory workflow.",
        ) from exc


@router.post("/workflow/with-image", status_code=200)
async def start_factory_workflow_with_image(
    scenario_id: str = Form(..., min_length=1, max_length=100),
    machine_id: str = Form(..., min_length=1, max_length=100),
    image: UploadFile = File(...),
):
    """Start the existing workflow using one validated inspection image."""

    temporary_path, image_evidence = await _store_validated_workflow_image(
        image
    )

    try:
        # The LangGraph workflow and its provider clients are synchronous.
        # Keeping them off this async request handler's event loop also lets
        # the Evolus advisory node safely run its bounded async client.
        return await run_in_threadpool(
            factory_workflow_service.start_workflow,
            scenario_id=scenario_id,
            machine_id=machine_id,
            image_path=temporary_path,
            image_evidence=image_evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not start the factory workflow with image evidence.",
        ) from exc
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


@router.get("/workflow/{thread_id}")
def get_factory_workflow(thread_id: UUID):
    try:
        return factory_workflow_service.get_workflow(str(thread_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve the factory workflow.",
        ) from exc


@router.post("/workflow/{thread_id}/identity-verification")
def verify_factory_equipment_identity(
    thread_id: UUID,
    request: PhysicalIdentityVerificationRequest,
):
    """
    Record a reviewed physical identity decision.

    This does not resume the graph or approve maintenance.
    """

    try:
        return factory_workflow_service.verify_physical_identity(
            thread_id=str(thread_id),
            decision=request.decision,
            reviewer=request.reviewer,
            comment=request.comment,
            evidence=request.evidence,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not record physical identity verification. "
                "Maintenance approval remains blocked."
            ),
        ) from exc


@router.post("/workflow/{thread_id}/approval")
def approve_factory_workflow(
    thread_id: UUID,
    request: WorkflowApprovalRequest,
):
    try:
        return factory_workflow_service.decide_approval(
            thread_id=str(thread_id),
            decision=request.decision,
            approval_user=request.approval_user,
            approval_comment=request.approval_comment,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not process the workflow approval.",
        ) from exc
