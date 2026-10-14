from dataclasses import dataclass
from typing import Literal


Severity = Literal["low", "medium", "high", "critical"]


@dataclass
class SensorReadings:
    """Sensor measurements for one factory machine."""

    machine_id: str
    temperature_c: float
    vibration_mm_s: float
    pressure_bar: float
    moisture_percent: float


@dataclass
class SensorAnomaly:
    """A detected sensor anomaly."""

    sensor: str
    value: float
    threshold: float
    unit: str
    severity: Severity
    description: str


@dataclass
class SensorAnalysisResult:
    """Complete result of analyzing a machine's sensor readings."""

    machine_id: str
    status: Literal["normal", "warning", "critical"]
    anomalies: list[SensorAnomaly]
    summary: str


class SensorAnalysisService:
    """
    Analyze factory sensor readings using configurable thresholds.

    The default thresholds are illustrative values for our simulated
    equipment, not universal industrial safety limits.
    """

    def __init__(
        self,
        temperature_warning_c: float = 75.0,
        temperature_critical_c: float = 90.0,
        vibration_warning_mm_s: float = 4.5,
        vibration_critical_mm_s: float = 7.1,
        pressure_min_bar: float = 2.0,
        pressure_max_bar: float = 8.0,
        moisture_min_percent: float = 10.0,
        moisture_max_percent: float = 90.0,
    ):
        if temperature_warning_c >= temperature_critical_c:
            raise ValueError(
                "Temperature warning threshold must be below "
                "the critical threshold."
            )

        if vibration_warning_mm_s >= vibration_critical_mm_s:
            raise ValueError(
                "Vibration warning threshold must be below "
                "the critical threshold."
            )

        if pressure_min_bar >= pressure_max_bar:
            raise ValueError(
                "Minimum pressure must be below maximum pressure."
            )

        if moisture_min_percent >= moisture_max_percent:
            raise ValueError(
                "Minimum moisture must be below maximum moisture."
            )

        self.temperature_warning_c = temperature_warning_c
        self.temperature_critical_c = temperature_critical_c

        self.vibration_warning_mm_s = vibration_warning_mm_s
        self.vibration_critical_mm_s = vibration_critical_mm_s

        self.pressure_min_bar = pressure_min_bar
        self.pressure_max_bar = pressure_max_bar

        self.moisture_min_percent = moisture_min_percent
        self.moisture_max_percent = moisture_max_percent

    @staticmethod
    def _validate_readings(readings: SensorReadings) -> None:
        """Reject invalid sensor measurements."""

        if not readings.machine_id.strip():
            raise ValueError("machine_id cannot be empty.")

        measurements = {
            "temperature_c": readings.temperature_c,
            "vibration_mm_s": readings.vibration_mm_s,
            "pressure_bar": readings.pressure_bar,
            "moisture_percent": readings.moisture_percent,
        }

        for name, value in measurements.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric.")

            if not float("-inf") < float(value) < float("inf"):
                raise ValueError(f"{name} must be finite.")

        if readings.vibration_mm_s < 0:
            raise ValueError("Vibration cannot be negative.")

        if readings.pressure_bar < 0:
            raise ValueError("Pressure cannot be negative.")

        if not 0 <= readings.moisture_percent <= 100:
            raise ValueError("Moisture must be between 0 and 100 percent.")

    def analyze(
        self,
        readings: SensorReadings,
    ) -> SensorAnalysisResult:
        """Analyze readings and return all detected anomalies."""

        self._validate_readings(readings)

        anomalies: list[SensorAnomaly] = []

        # 1. Temperature analysis
        if readings.temperature_c >= self.temperature_critical_c:
            anomalies.append(
                SensorAnomaly(
                    sensor="temperature",
                    value=readings.temperature_c,
                    threshold=self.temperature_critical_c,
                    unit="°C",
                    severity="critical",
                    description=(
                        "Temperature has reached or exceeded "
                        "the critical simulated threshold."
                    ),
                )
            )

        elif readings.temperature_c >= self.temperature_warning_c:
            anomalies.append(
                SensorAnomaly(
                    sensor="temperature",
                    value=readings.temperature_c,
                    threshold=self.temperature_warning_c,
                    unit="°C",
                    severity="medium",
                    description=(
                        "Temperature has reached or exceeded "
                        "the warning threshold."
                    ),
                )
            )

        # 2. Vibration analysis
        if readings.vibration_mm_s >= self.vibration_critical_mm_s:
            anomalies.append(
                SensorAnomaly(
                    sensor="vibration",
                    value=readings.vibration_mm_s,
                    threshold=self.vibration_critical_mm_s,
                    unit="mm/s",
                    severity="critical",
                    description=(
                        "Vibration has reached or exceeded "
                        "the critical simulated threshold."
                    ),
                )
            )

        elif readings.vibration_mm_s >= self.vibration_warning_mm_s:
            anomalies.append(
                SensorAnomaly(
                    sensor="vibration",
                    value=readings.vibration_mm_s,
                    threshold=self.vibration_warning_mm_s,
                    unit="mm/s",
                    severity="medium",
                    description=(
                        "Vibration has reached or exceeded "
                        "the warning threshold."
                    ),
                )
            )

        # 3. Pressure analysis
        if readings.pressure_bar < self.pressure_min_bar:
            anomalies.append(
                SensorAnomaly(
                    sensor="pressure",
                    value=readings.pressure_bar,
                    threshold=self.pressure_min_bar,
                    unit="bar",
                    severity="high",
                    description=(
                        "Pressure is below the configured "
                        "simulated operating range."
                    ),
                )
            )

        elif readings.pressure_bar > self.pressure_max_bar:
            anomalies.append(
                SensorAnomaly(
                    sensor="pressure",
                    value=readings.pressure_bar,
                    threshold=self.pressure_max_bar,
                    unit="bar",
                    severity="high",
                    description=(
                        "Pressure is above the configured "
                        "simulated operating range."
                    ),
                )
            )

        # 4. Moisture analysis
        if readings.moisture_percent < self.moisture_min_percent:
            anomalies.append(
                SensorAnomaly(
                    sensor="moisture",
                    value=readings.moisture_percent,
                    threshold=self.moisture_min_percent,
                    unit="%",
                    severity="medium",
                    description=(
                        "Moisture is below the configured "
                        "simulated operating range."
                    ),
                )
            )

        elif readings.moisture_percent > self.moisture_max_percent:
            anomalies.append(
                SensorAnomaly(
                    sensor="moisture",
                    value=readings.moisture_percent,
                    threshold=self.moisture_max_percent,
                    unit="%",
                    severity="medium",
                    description=(
                        "Moisture is above the configured "
                        "simulated operating range."
                    ),
                )
            )

        # 5. Determine overall status
        if any(a.severity == "critical" for a in anomalies):
            status = "critical"

        elif anomalies:
            status = "warning"

        else:
            status = "normal"

        # 6. Build a human-readable summary
        if not anomalies:
            summary = "All readings are within the configured simulated ranges."
        else:
            affected_sensors = ", ".join(
                anomaly.sensor for anomaly in anomalies
            )
            summary = (
                f"Detected {len(anomalies)} anomaly or anomalies "
                f"affecting: {affected_sensors}."
            )

        return SensorAnalysisResult(
            machine_id=readings.machine_id,
            status=status,
            anomalies=anomalies,
            summary=summary,
        )