from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.state import FactoryAgentState
from app.agents import nodes

from app.agents.routing import (
    route_after_acquisition,
    route_after_sensor_analysis,
    route_after_image_inspection,
    route_after_triage,
    route_after_incident_creation,
    route_after_investigation,
    route_after_task_creation,
    route_after_approval,
    route_after_maintenance_start,
    route_after_maintenance_completion,
    route_after_verification,
)


def build_factory_graph(checkpointer=None):
    """Build and compile the Factory Inspector workflow."""
    if checkpointer is None:
        checkpointer = InMemorySaver()

    workflow = StateGraph(FactoryAgentState)

    # Register nodes.
    workflow.add_node("acquire_data", nodes.acquire_data)
    workflow.add_node("analyze_sensors", nodes.analyze_sensors)
    workflow.add_node("inspect_image", nodes.inspect_image)
    workflow.add_node("extract_nameplate", nodes.extract_nameplate)
    workflow.add_node("reconcile_evidence", nodes.reconcile_evidence)
    workflow.add_node("identify_equipment", nodes.identify_equipment)
    workflow.add_node("triage_incident", nodes.triage_incident)
    workflow.add_node("log_normal_operation", nodes.log_normal_operation)
    workflow.add_node("create_incident", nodes.create_incident)
    workflow.add_node(
        "evolus_maintenance_foreman",
        nodes.consult_evolus_maintenance_foreman,
    )
    workflow.add_node("investigate_incident", nodes.investigate_incident)
    workflow.add_node(
        "generate_maintenance_task",
        nodes.generate_maintenance_task,
    )
    workflow.add_node("human_approval", nodes.process_approval)
    workflow.add_node("start_maintenance", nodes.start_maintenance)
    workflow.add_node("complete_maintenance", nodes.complete_maintenance)
    workflow.add_node("verify_maintenance", nodes.verify_maintenance)
    workflow.add_node("close_incident", nodes.close_incident)
    workflow.add_node("escalate_incident", nodes.escalate_incident)
    workflow.add_node("handle_error", nodes.handle_error)

    # Start.
    workflow.add_edge(START, "acquire_data")

    # Acquire and validate incoming data.
    workflow.add_conditional_edges(
        "acquire_data",
        route_after_acquisition,
        {
            "analyze_sensors": "analyze_sensors",
            "error": "handle_error",
        },
    )

    # Analyze sensors.
    workflow.add_conditional_edges(
        "analyze_sensors",
        route_after_sensor_analysis,
        {
            "inspect_image": "inspect_image",
            "error": "handle_error",
        },
    )

    # Inspect one image, extract its nameplate, reconcile the unverified
    # evidence, then perform conservative registry matching.
    workflow.add_conditional_edges(
        "inspect_image",
        route_after_image_inspection,
        {
            "extract_nameplate": "extract_nameplate",
            "error": "handle_error",
        },
    )

    workflow.add_edge("extract_nameplate", "reconcile_evidence")
    workflow.add_edge("reconcile_evidence", "identify_equipment")
    workflow.add_edge("identify_equipment", "triage_incident")

    # Triage findings.
    workflow.add_conditional_edges(
        "triage_incident",
        route_after_triage,
        {
            "create_incident": "create_incident",
            "log_normal_operation": "log_normal_operation",
            "error": "handle_error",
        },
    )

    workflow.add_edge("log_normal_operation", END)

    # Create and investigate incidents.
    workflow.add_conditional_edges(
        "create_incident",
        route_after_incident_creation,
        {
            "investigate_incident": "evolus_maintenance_foreman",
            "error": "handle_error",
        },
    )

    # Evolus is advisory only. A failed/invalid response is recorded in state
    # and the evidence-based workflow continues to human review.
    workflow.add_edge(
        "evolus_maintenance_foreman",
        "investigate_incident",
    )

    workflow.add_conditional_edges(
        "investigate_incident",
        route_after_investigation,
        {
            "generate_maintenance_task": "generate_maintenance_task",
            "error": "handle_error",
        },
    )

    # Generate a maintenance task.
    workflow.add_conditional_edges(
        "generate_maintenance_task",
        route_after_task_creation,
        {
            "human_approval": "human_approval",
            "error": "handle_error",
        },
    )

    # Require human approval before maintenance.
    workflow.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "start_maintenance": "start_maintenance",
            "await_approval": END,
            "end": END,
            "error": "handle_error",
        },
    )

    # Simulate maintenance.
    workflow.add_conditional_edges(
        "start_maintenance",
        route_after_maintenance_start,
        {
            "complete_maintenance": "complete_maintenance",
            "error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "complete_maintenance",
        route_after_maintenance_completion,
        {
            "verify_maintenance": "verify_maintenance",
            "error": "handle_error",
        },
    )

    # Verify maintenance before closing or escalating.
    workflow.add_conditional_edges(
        "verify_maintenance",
        route_after_verification,
        {
            "close_incident": "close_incident",
            "escalate_incident": "escalate_incident",
            "error": "handle_error",
        },
    )

    workflow.add_edge("close_incident", END)
    workflow.add_edge("escalate_incident", END)
    workflow.add_edge("handle_error", END)

    return workflow.compile(checkpointer=checkpointer)
