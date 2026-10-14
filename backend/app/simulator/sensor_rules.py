"""Simulated sensor rules for Factory Inspector.

IMPORTANT:
These values are demonstration thresholds for software testing.
They are not validated industrial safety limits.
"""

from typing import Any


SENSOR_RULES: dict[str, dict[str, Any]] = {
    "temperature_c": {
        "unit": "°C",
        "normal_min": 20.0,
        "normal_max": 75.0,
        "warning_threshold": 80.0,
        "critical_threshold": 90.0,
    },
    "vibration_mm_s": {
        "unit": "mm/s",
        "normal_min": 0.0,
        "normal_max": 4.5,
        "warning_threshold": 5.0,
        "critical_threshold": 7.1,
    },
    "pressure_bar": {
        "unit": "bar",
        "normal_min": 2.0,
        "normal_max": 6.0,
        "warning_threshold": 7.0,
        "critical_threshold": 8.0,
    },
    "moisture_percent": {
        "unit": "%",
        "normal_min": 20.0,
        "normal_max": 70.0,
        "warning_threshold": 80.0,
        "critical_threshold": 90.0,
    },
}


def evaluate_sensor(
    sensor_name: str,
    value: float,
) -> dict[str, Any]:
    """Evaluate a sensor reading against simulated thresholds."""

    if sensor_name not in SENSOR_RULES:
        raise ValueError(f"Unsupported sensor: {sensor_name}")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Sensor value must be numeric.")

    rule = SENSOR_RULES[sensor_name]
    value = float(value)

    if value >= rule["critical_threshold"]:
        severity = "critical"
    elif value >= rule["warning_threshold"]:
        severity = "warning"
    elif (
        value < rule["normal_min"]
        or value > rule["normal_max"]
    ):
        severity = "warning"
    else:
        severity = "normal"

    return {
        "sensor": sensor_name,
        "value": value,
        "unit": rule["unit"],
        "severity": severity,
        "thresholds_are_simulated": True,
    }


def evaluate_readings(
    readings: dict[str, float],
) -> dict[str, Any]:
    """Evaluate all supported readings in a sensor payload."""

    results = [
        evaluate_sensor(sensor_name, value)
        for sensor_name, value in readings.items()
        if sensor_name in SENSOR_RULES
    ]

    anomalies = [
        result
        for result in results
        if result["severity"] != "normal"
    ]

    if any(item["severity"] == "critical" for item in anomalies):
        overall_status = "critical"
    elif anomalies:
        overall_status = "warning"
    else:
        overall_status = "normal"

    return {
        "status": overall_status,
        "readings": results,
        "anomalies": anomalies,
        "thresholds_are_simulated": True,
    }