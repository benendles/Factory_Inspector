import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.equipment_registry import (
    EquipmentRecord,
    EquipmentRegistry,
    MatchStatus,
)


class TestEquipmentRegistry(unittest.TestCase):
    def setUp(self):
        self.motor = EquipmentRecord(
            asset_id="MOTOR-001",
            equipment_type="electric_motor",
            manufacturer="Siemens",
            model_number="1LE1001",
            serial_number="SN-12345",
            asset_tag="PLANT-A-M001",
            location="Production Hall A",
            specifications={
                "voltage": "400 V",
                "power": "5.5 kW",
                "frequency": "50 Hz",
            },
        )

        self.registry = EquipmentRegistry([self.motor])

    def test_get_registered_asset(self):
        result = self.registry.get("MOTOR-001")

        self.assertIsNotNone(result)
        self.assertEqual(result.manufacturer, "Siemens")

    def test_exact_serial_identifies_registered_asset(self):
        result = self.registry.identify(
            {
                "serial_number": "SN-12345",
                "manufacturer": "Siemens",
                "model_number": "1LE1001",
                "equipment_type": "electric_motor",
            }
        )

        self.assertEqual(result.status, MatchStatus.VERIFIED)
        self.assertEqual(result.matched_asset.asset_id, "MOTOR-001")

    def test_model_only_is_not_verified(self):
        result = self.registry.identify(
            {
                "manufacturer": "Siemens",
                "model_number": "1LE1001",
                "equipment_type": "electric_motor",
            }
        )

        self.assertEqual(result.status, MatchStatus.POSSIBLE)

    def test_unknown_serial_does_not_match_by_serial(self):
        result = self.registry.identify(
            {
                "serial_number": "UNKNOWN-999",
                "manufacturer": "Siemens",
                "model_number": "1LE1001",
            }
        )

        # The serial number alone is not found, but the descriptive
        # details can still produce a possible match.
        self.assertEqual(result.status, MatchStatus.POSSIBLE)

    def test_conflicting_model_prevents_verified_match(self):
        result = self.registry.identify(
            {
                "serial_number": "SN-12345",
                "model_number": "DIFFERENT-MODEL",
            }
        )

        self.assertEqual(result.status, MatchStatus.POSSIBLE)
        self.assertIn("model_number", result.conflicting_fields)

    def test_duplicate_serial_is_rejected(self):
        duplicate = EquipmentRecord(
            asset_id="MOTOR-002",
            equipment_type="electric_motor",
            serial_number="SN-12345",
        )

        with self.assertRaises(ValueError):
            self.registry.register(duplicate)

    def test_unknown_asset_returns_none(self):
        self.assertIsNone(self.registry.get("UNKNOWN-ASSET"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
    