"""Factory simulation engine for Factory Inspector."""

from typing import Any

from app.simulator.scenarios import get_scenario, list_scenarios
from app.simulator.sensor_rules import evaluate_readings


def run_scenario(scenario_name: str) -> dict[str, Any]:
    """Run a predefined factory scenario and analyze its sensor readings."""

    scenario = get_scenario(scenario_name)

    sensor_readings = scenario["sensor_readings"]
    analysis = evaluate_readings(sensor_readings)

    return {
        "scenario_id": scenario_name,
        "scenario_name": scenario["name"],
        "description": scenario["description"],
        "sensor_readings": sensor_readings,
        "analysis": analysis,
        "expected_status": scenario["expected_status"],
        "maintenance_will_resolve": scenario["maintenance_will_resolve"],
        "thresholds_are_simulated": True,
    }


def simulate_maintenance(
    scenario_name: str,
) -> dict[str, Any]:
    """Simulate maintenance and return fresh post-maintenance readings.

    This is a software demonstration only. It does not operate equipment
    or perform real maintenance.
    """

    scenario = get_scenario(scenario_name)

    before_readings = dict(scenario["sensor_readings"])

    if scenario["maintenance_will_resolve"]:
        after_readings = {
            "temperature_c": 55.0,
            "vibration_mm_s": 2.0,
            "pressure_bar": 4.0,
            "moisture_percent": 45.0,
        }
    else:
        # Simulate a failure to resolve the original anomalies.
        after_readings = dict(before_readings)

    before_analysis = evaluate_readings(before_readings)
    after_analysis = evaluate_readings(after_readings)

    resolved = (
        before_analysis["status"] != "normal"
        and after_analysis["status"] == "normal"
    )

    if resolved:
        outcome = "resolved"
        summary = (
            "Fresh simulated readings show that the configured "
            "sensor anomalies are no longer present."
        )
    else:
        outcome = "escalation_required"
        summary = (
            "Fresh simulated readings show that the anomalies persist. "
            "Further investigation and human review are required."
        )

    return {
        "scenario_id": scenario_name,
        "before_readings": before_readings,
        "after_readings": after_readings,
        "before_analysis": before_analysis,
        "after_analysis": after_analysis,
        "outcome": outcome,
        "resolved": resolved,
        "summary": summary,
        "safety_certified": False,
        "thresholds_are_simulated": True,
    }


def get_available_scenarios() -> list[dict[str, Any]]:
    """List scenarios available to the simulator."""

    return list_scenarios()