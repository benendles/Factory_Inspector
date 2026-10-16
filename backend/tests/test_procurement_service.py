from uuid import uuid4

from app.api.schemas.procurement import ProcurementProposal
from app.services.procurement_service import ProcurementService
from app.services.supplier_search_service import SupplierSearchService


class FakeResponse:
    status_code = 200

    def json(self):
        return {"results": [{
            "title": "Acme Motors MX-100 cooling fan $42.50",
            "url": "https://supplier.example/mx-100-fan",
            "content": "A search result for Acme Motors MX-100. $42.50.",
        }]}


class FakeHttpClient:
    def __init__(self):
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        return FakeResponse()


def verified_state() -> dict:
    registry_id = str(uuid4())
    return {
        "physical_identity_confirmed": True,
        "physical_verification_required": False,
        "registry_requires_physical_verification": False,
        "physical_identity_verification_decision": "confirmed",
        "physical_identity_verified_registry_id": registry_id,
        "physical_identity_verification_audit_id": str(uuid4()),
        "registry_match_status": "verified_match",
        "registry_match": {
            "status": "verified_match",
            "candidate": {
                "id": registry_id,
                "manufacturer": "Acme Motors",
                "model_number": "MX-100",
                "equipment_type": "electric_motor",
            },
        },
        "equipment_identifier_conflicts": [],
        "identifier_conflicts": [],
        "sensor_analysis": {"anomalies": [{
            "sensor": "temperature", "value": 95, "threshold": 90,
        }]},
    }


def test_procurement_is_blocked_before_audited_identity_confirmation():
    client = FakeHttpClient()
    service = ProcurementService(
        supplier_search_service=SupplierSearchService(
            api_key="test-key", enabled=True, http_client=client,
        )
    )
    state = verified_state()
    state["physical_identity_confirmed"] = False

    proposal = service.create_proposal(state)

    assert proposal["research_status"] == "blocked_identity_not_confirmed"
    assert proposal["supplier_offers"] == []
    assert proposal["requires_human_approval"] is False
    assert client.calls == 0


def test_procurement_preserves_unverified_price_and_cannot_approve_maintenance():
    client = FakeHttpClient()
    service = ProcurementService(
        supplier_search_service=SupplierSearchService(
            api_key="test-key", enabled=True, http_client=client,
        )
    )

    proposal = service.create_proposal(verified_state())

    assert proposal["research_status"] == "completed"
    assert proposal["possibly_compatible_parts"]
    assert proposal["supplier_offers"][0]["price_status"] == "unverified_listing"
    assert proposal["known_parts_subtotal_usd"] is None
    assert proposal["estimated_total_usd"] is None
    assert proposal["requires_human_approval"] is True
    assert proposal["requires_technician_review"] is True
    assert ProcurementProposal.model_validate(proposal).research_status == (
        "completed"
    )
