"""Focused tests for image, OCR, reconciliation, and upload workflow input."""

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.agents import nodes
from app.api.routes import simulator


def image_result(**equipment):
    return {
        "machine_id": "MACHINE-DEMO-001",
        "equipment": {
            "equipment_type": "electric_motor",
            "manufacturer": "Demo Motors",
            "model_number": "DM-100",
            "serial_number": "SN-001",
            "asset_tag": None,
            "visible_components": ["motor housing"],
            "visible_markings": ["DM-100"],
            "identification_status": "partially_identified",
            "confidence": "medium",
            "identification_notes": [],
            **equipment,
        },
        "observations": [],
        "requires_human_review": True,
        "summary": "Visible motor evidence.",
    }


def ocr_result(**fields):
    return {
        "provider": "test_ocr",
        "status": "text_extracted",
        "raw_text": "Model: DM-100\nSerial: SN-001",
        "fields": {
            "manufacturer": "Demo Motors",
            "model_number": "DM-100",
            "serial_number": "SN-001",
            "voltage": "400 V",
            "power": "5.5 kW",
            "frequency": "50 Hz",
            "current": "11 A",
            **fields,
        },
        "confidence": 91.0,
        "requires_human_review": True,
        "notes": [],
    }


def evidence_state(image_path: Path | None) -> dict:
    return {
        "machine_id": "MACHINE-DEMO-001",
        "image_path": str(image_path) if image_path else None,
        "image_evidence": {
            "status": "available" if image_path else "unavailable",
            "source": "test",
        },
        "messages": [],
        "physical_identity_confirmed": False,
        "physical_verification_required": True,
        "registry_requires_physical_verification": True,
        "equipment_identifier_conflicts": [],
        "identifier_conflicts": [],
    }


def install_registry_matcher(monkeypatch, captured: dict | None = None):
    class FakeSession:
        def close(self):
            return None

    class FakeMatcher:
        def __init__(self, _db):
            pass

        def match(self, **kwargs):
            if captured is not None:
                captured.update(kwargs)

            return {
                "status": "verified_match",
                "candidate": {
                    "id": str(uuid4()),
                    "manufacturer": "Demo Motors",
                    "model_number": "DM-100",
                    "equipment_type": "electric_motor",
                },
                "candidates": [],
                "identifier_conflicts": [],
            }

    monkeypatch.setattr(nodes, "SessionLocal", FakeSession)
    monkeypatch.setattr(nodes, "SQLEquipmentMatcher", FakeMatcher)


def run_evidence_nodes(state: dict) -> dict:
    nodes.inspect_image(state)
    nodes.extract_nameplate(state)
    nodes.reconcile_evidence(state)
    return state


def test_image_and_ocr_evidence_reach_registry_matching(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "evidence.png"
    image_path.write_bytes(b"test image")
    state = evidence_state(image_path)
    captured: dict = {}

    monkeypatch.setattr(
        nodes.image_service,
        "inspect_image",
        lambda **_kwargs: image_result(),
    )
    monkeypatch.setattr(
        nodes.nameplate_ocr_service,
        "inspect",
        lambda _path: ocr_result(),
    )
    install_registry_matcher(monkeypatch, captured)

    run_evidence_nodes(state)
    nodes.identify_equipment(state)

    assert state["image_inspection_result"]["status"] == "completed"
    assert state["nameplate_ocr_result"]["provider"] == "test_ocr"
    assert state["nameplate_ocr_result"]["fields"]["voltage"] == "400 V"
    assert state["evidence_reconciliation"]["status"] == "reconciled"
    assert state["registry_match_status"] == "verified_match"
    assert captured["serial_number"] == "SN-001"
    assert state["physical_identity_confirmed"] is False


def test_ocr_can_supply_registry_identifiers_when_visual_inspection_fails(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "evidence.png"
    image_path.write_bytes(b"test image")
    state = evidence_state(image_path)
    captured: dict = {}

    monkeypatch.setattr(
        nodes.image_service,
        "inspect_image",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("AMD unavailable")),
    )
    monkeypatch.setattr(
        nodes.nameplate_ocr_service,
        "inspect",
        lambda _path: ocr_result(serial_number="OCR-SN-009"),
    )
    install_registry_matcher(monkeypatch, captured)

    run_evidence_nodes(state)
    nodes.identify_equipment(state)

    assert state["image_inspection_result"]["status"] == "error"
    assert "AMD unavailable" not in str(state["image_inspection_result"])
    assert state["nameplate_ocr_result"]["status"] == "text_extracted"
    assert captured["serial_number"] == "OCR-SN-009"
    assert state["evidence_reconciliation"]["status"] == "partial_evidence"
    assert state["physical_identity_confirmed"] is False


def test_visual_evidence_remains_available_when_ocr_fails(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "evidence.png"
    image_path.write_bytes(b"test image")
    state = evidence_state(image_path)
    captured: dict = {}

    monkeypatch.setattr(
        nodes.image_service,
        "inspect_image",
        lambda **_kwargs: image_result(serial_number="VISUAL-SN-008"),
    )
    monkeypatch.setattr(
        nodes.nameplate_ocr_service,
        "inspect",
        lambda _path: (_ for _ in ()).throw(RuntimeError("OCR unavailable")),
    )
    install_registry_matcher(monkeypatch, captured)

    run_evidence_nodes(state)
    nodes.identify_equipment(state)

    assert state["image_inspection_result"]["status"] == "completed"
    assert state["nameplate_ocr_result"]["status"] == "error"
    assert "OCR unavailable" not in str(state["nameplate_ocr_result"])
    assert captured["serial_number"] == "VISUAL-SN-008"
    assert state["physical_identity_confirmed"] is False


def test_missing_image_evidence_is_explicit_and_does_not_fabricate_fields():
    state = evidence_state(None)

    run_evidence_nodes(state)

    assert state["image_inspection_result"]["status"] == "unavailable"
    assert state["nameplate_ocr_result"]["status"] == "unavailable"
    assert state["nameplate_ocr_result"]["fields"] == {}
    assert state["evidence_reconciliation"]["status"] == "evidence_unavailable"
    assert state["physical_identity_confirmed"] is False


def test_conflicting_visual_and_ocr_identifiers_block_verified_match(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "evidence.png"
    image_path.write_bytes(b"test image")
    state = evidence_state(image_path)

    monkeypatch.setattr(
        nodes.image_service,
        "inspect_image",
        lambda **_kwargs: image_result(model_number="VISUAL-100"),
    )
    monkeypatch.setattr(
        nodes.nameplate_ocr_service,
        "inspect",
        lambda _path: ocr_result(model_number="OCR-200"),
    )
    install_registry_matcher(monkeypatch)

    run_evidence_nodes(state)
    nodes.identify_equipment(state)

    assert state["evidence_reconciliation"]["status"] == "conflicts_detected"
    assert state["evidence_reconciliation"]["contradictions"][0]["field"] == (
        "model_number"
    )
    assert state["registry_match_status"] == "possible_match"
    assert state["physical_identity_confirmed"] is False


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_multipart_upload_uses_a_short_lived_validated_image(monkeypatch):
    app = FastAPI()
    app.include_router(simulator.router)
    captured: dict = {}

    def fake_start_workflow(**kwargs):
        image_path = Path(kwargs["image_path"])
        captured.update(kwargs)
        captured["image_exists_during_workflow"] = image_path.is_file()
        try:
            asyncio.get_running_loop()
            captured["called_on_event_loop"] = True
        except RuntimeError:
            captured["called_on_event_loop"] = False
        return {"workflow_status": "awaiting_approval"}

    monkeypatch.setattr(
        simulator.factory_workflow_service,
        "start_workflow",
        fake_start_workflow,
    )

    response = TestClient(app).post(
        "/simulator/workflow/with-image",
        data={"scenario_id": "overheating", "machine_id": "MACHINE-001"},
        files={"image": ("inspection.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert captured["image_exists_during_workflow"] is True
    assert captured["called_on_event_loop"] is False
    assert captured["image_evidence"] == {
        "status": "available",
        "source": "uploaded_image",
        "content_type": "image/png",
        "size_bytes": len(png_bytes()),
    }
    assert not Path(captured["image_path"]).exists()


def test_multipart_upload_rejects_an_unsupported_media_type():
    app = FastAPI()
    app.include_router(simulator.router)

    response = TestClient(app).post(
        "/simulator/workflow/with-image",
        data={"scenario_id": "overheating", "machine_id": "MACHINE-001"},
        files={"image": ("inspection.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415


def test_multipart_upload_rejects_unreadable_image_content():
    app = FastAPI()
    app.include_router(simulator.router)

    response = TestClient(app).post(
        "/simulator/workflow/with-image",
        data={"scenario_id": "overheating", "machine_id": "MACHINE-001"},
        files={"image": ("inspection.png", b"not a PNG", "image/png")},
    )

    assert response.status_code == 422


def test_multipart_upload_rejects_an_oversized_image(monkeypatch):
    app = FastAPI()
    app.include_router(simulator.router)
    monkeypatch.setattr(simulator, "MAX_IMAGE_UPLOAD_BYTES", 1)

    response = TestClient(app).post(
        "/simulator/workflow/with-image",
        data={"scenario_id": "overheating", "machine_id": "MACHINE-001"},
        files={"image": ("inspection.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 413
