"""Predefined factory scenarios for Factory Inspector."""

from typing import Any


SCENARIOS: dict[str, dict[str, Any]] = {
    "normal_operation": {
        "name": "Normal Operation",
        "description": "All simulated sensors report normal readings.",
        "sensor_readings": {
            "temperature_c": 55.0,
            "vibration_mm_s": 2.0,
            "pressure_bar": 4.0,
            "moisture_percent": 45.0,
        },
        "expected_status": "normal",
        "maintenance_will_resolve": True,
    },
    "overheating": {
        "name": "Equipment Overheating",
        "description": "Simulated equipment temperature is critically high.",
        "sensor_readings": {
            "temperature_c": 95.0,
            "vibration_mm_s": 2.5,
            "pressure_bar": 4.0,
            "moisture_percent": 45.0,
        },
        "expected_status": "critical",
        "maintenance_will_resolve": True,
    },
    "excessive_vibration": {
        "name": "Excessive Vibration",
        "description": "Simulated equipment vibration is critically high.",
        "sensor_readings": {
            "temperature_c": 55.0,
            "vibration_mm_s": 8.2,
            "pressure_bar": 4.0,
            "moisture_percent": 45.0,
        },
        "expected_status": "critical",
        "maintenance_will_resolve": True,
    },
    "critical_failure": {
        "name": "Multiple Critical Anomalies",
        "description": (
            "Multiple simulated sensors report critical anomalies."
        ),
        "sensor_readings": {
            "temperature_c": 95.0,
            "vibration_mm_s": 8.2,
            "pressure_bar": 9.0,
            "moisture_percent": 45.0,
        },
        "expected_status": "critical",
        "maintenance_will_resolve": True,
    },
    "persistent_anomaly": {
        "name": "Persistent Anomaly",
        "description": (
            "A simulated critical anomaly persists after "
            "the maintenance simulation."
        ),
        "sensor_readings": {
            "temperature_c": 95.0,
            "vibration_mm_s": 8.2,
            "pressure_bar": 4.0,
            "moisture_percent": 45.0,
        },
        "expected_status": "critical",
        "maintenance_will_resolve": False,
    },
}


def get_scenario(scenario_name: str) -> dict[str, Any]:
    """Return a copy of a predefined scenario."""

    if scenario_name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. "
            f"Available scenarios: {available}"
        )

    scenario = SCENARIOS[scenario_name]

    return {
        **scenario,
        "sensor_readings": dict(scenario["sensor_readings"]),
    }


def list_scenarios() -> list[dict[str, Any]]:
    """Return scenario names and descriptions without sensor payloads."""

    return [
        {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "description": scenario["description"],
            "expected_status": scenario["expected_status"],
        }
        for scenario_id, scenario in SCENARIOS.items()
    ]