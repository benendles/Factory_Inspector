from typing import Any, Literal
from typing_extensions import TypedDict


class FactoryAgentState(TypedDict, total=False):
    """
    Shared state passed between nodes in the Factory Inspector LangGraph.

    Each node reads the fields it needs and returns a dictionary
    containing only the fields it updates.
    """

    
    # 1. Initial factory inspection input
    
    machine_id: str
    sensor_readings: dict[str, Any]
    image_path: str | None
    timestamp: str

    
    # 2. Sensor and vision analysis
    
    sensor_analysis: dict[str, Any]
    vision_analysis: dict[str, Any]

    anomalies_detected: bool
    severity: str

    
    # 3. Incident management
   
    incident_id: str
    incident: dict[str, Any]
    incident_created: bool

    
    # 4. Investigation and maintenance planning
    
    investigation: dict[str, Any]
    action_plan: list[dict[str, Any]]

    maintenance_task_id: str
    maintenance_status: str

    
    # 5. Human approval
   
    requires_human_approval: bool
    approval_status: Literal["pending", "approved", "rejected"]
    approval_user: str
    approval_comment: str


    # 6. Maintenance verification
    post_maintenance_readings: dict[str, Any]
    verification_result: dict[str, Any]
    resolved: bool

    
    # 7. Workflow control
    
    status: str
    error: str | None
    messages: list[str]