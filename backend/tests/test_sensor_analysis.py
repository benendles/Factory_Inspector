from app.services.sensor_analysis import (
    SensorAnalysisService,
    SensorReadings,
)


def main():
    service = SensorAnalysisService()

    # Test 1: Normal operating conditions
    normal_readings = SensorReadings(
        machine_id="MACHINE-001",
        temperature_c=45.0,
        vibration_mm_s=2.0,
        pressure_bar=5.0,
        moisture_percent=50.0,
    )

    normal_result = service.analyze(normal_readings)

    print("\nTEST 1: NORMAL MACHINE")
    print(normal_result)

    assert normal_result.status == "normal"
    assert len(normal_result.anomalies) == 0

    # Test 2: Multiple anomalies
    abnormal_readings = SensorReadings(
        machine_id="MACHINE-002",
        temperature_c=98.5,
        vibration_mm_s=12.4,
        pressure_bar=9.5,
        moisture_percent=50.0,
    )

    abnormal_result = service.analyze(abnormal_readings)

    print("\nTEST 2: ABNORMAL MACHINE")
    print(abnormal_result)

    assert abnormal_result.status == "critical"
    assert len(abnormal_result.anomalies) == 3

    # Test 3: Invalid readings
    try:
        invalid_readings = SensorReadings(
            machine_id="MACHINE-003",
            temperature_c=50.0,
            vibration_mm_s=2.0,
            pressure_bar=5.0,
            moisture_percent=150.0,
        )

        service.analyze(invalid_readings)

    except ValueError as error:
        print("\nTEST 3: INVALID READINGS REJECTED")
        print(error)

    else:
        raise AssertionError("Invalid moisture reading was accepted.")

    print("\nAll sensor analysis tests passed!")


if __name__ == "__main__":
    main()