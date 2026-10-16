# Repair planning

Factory Inspector can prepare an advisory repair plan for the same in-memory
maintenance task that is waiting for human approval. It does not order parts,
contact suppliers, control equipment, or authorize maintenance.

## Workflow and safeguards

The LangGraph topology is unchanged. A maintenance task is created and the
workflow pauses at its existing human-approval interrupt. The separate
physical-identity-verification endpoint records an audit decision and updates
that paused checkpoint.

Only a complete, audited identity confirmation can generate an asset-specific
repair plan. The service requires all of the following:

- `physical_identity_confirmed` is `true` and the verification decision is
  `confirmed`.
- Physical-verification flags are cleared.
- The registry has one `verified_match` candidate whose ID matches the
  recorded verified registry ID.
- The audit ID is a UUID.
- Both identifier-conflict lists exist and are empty.

Identity confirmation does not approve maintenance. The workflow stays paused
until the existing approval endpoint records an explicit decision. A rejected
identity replaces any existing asset-specific plan with a
`blocked_identity_rejected` plan that has no asset ID, parts, or prices.

## Local catalogue

`RepairPlanningService` has a small, read-only Python catalogue in
`backend/app/services/repair_planning_service.py`. It is deliberately a
demonstration fixture. Its entries and identifiers are not manufacturer part
numbers, live supplier data, current prices, stock claims, or quotations.

An entry has this shape:

```python
{
    "part_id": "internal-catalogue-id",
    "part_number": "DEMO-...",
    "part_name": "Demonstration part",
    "compatible_equipment_manufacturer": "Exact manufacturer",
    "compatible_model_numbers": ["Exact model"],
    "compatible_equipment_types": ["Exact type"],
    "quantity": 1,
    "unit_price": None,
    "currency": None,
    "supplier_name": None,
    "price_source": None,
    "price_checked_at": None,
    "availability": "unknown",
    "compatibility_basis": "Documented basis for the catalogue rule",
    "catalogue_kind": "demonstration",
}
```

Future catalogue entries must include explicit manufacturer, model, and
equipment-type compatibility rules. A broad category, a manufacturer-only
match, OCR text, or a registry match alone is never sufficient to claim that
a part is confirmed compatible.

## Compatibility and pricing rules

Compatibility can be `confirmed_compatible`, `requires_verification`,
`incompatible`, or `insufficient_equipment_data`.

- Only exact explicit catalogue matches are `confirmed_compatible`.
- Incompatible parts are returned separately and never contribute to a total.
- Missing model data produces an incomplete plan rather than a guessed match.
- Monetary arithmetic uses Python `Decimal`; JSON monetary values are decimal
  strings, not floating-point values.
- An unknown price is `null`, never zero.
- A known price requires a currency, source, and retrieval timestamp.
- Prices in different currencies are never summed.
- Labour, transport, and tax remain `null` until configured, sourced values
  are available. Consequently, `estimated_total` stays `null` in this first
  version even when a parts-only subtotal is known.

`price_completeness` describes whether compatible part prices are complete.
The plan also lists limitations and indicates when a supplier quote or
technician review is still required.

## API response

Workflow responses contain `repair_plan`. After identity confirmation the same
object also appears in the pending-approval payload. A workflow retrieval
reuses the checkpointed plan; it does not regenerate a plan or a maintenance
task.

The implementation does not use the separate SQL `MaintenanceTask` REST
subsystem. The plan refers to the LangGraph task ID (for example `MT-...`), so
it remains governed by the workflow's identity and approval safeguards.

## Tests

From `backend/`:

```bash
../.venv/bin/python -m pytest \
  tests/test_repair_planning_service.py \
  tests/test_repair_workflow_integration.py
```

The tests cover exact compatibility, missing prices, incompatible parts,
missing model data, mixed currencies, identity blocks, paused approval,
workflow retrieval, and planning failures.
