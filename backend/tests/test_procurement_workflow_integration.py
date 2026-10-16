from app.services.repair_planning_service import RepairPlanningService

from test_repair_planning_service import compatible_part, verified_state


def test_repair_plan_caches_disabled_procurement_and_gets_do_not_research_again():
    plan = RepairPlanningService([compatible_part()]).create_plan(
        verified_state()
    )

    assert plan["procurement"]["research_status"] == "research_disabled"
    assert plan["procurement"]["supplier_offers"] == []
    assert plan["procurement"]["requires_human_approval"] is True
    assert plan["requires_human_approval"] is True
