"""Integration test for equipment persistence in Supabase."""

import os
import unittest
from uuid import uuid4

from sqlalchemy import select

from app.database.models import Equipment
from app.database.session import SessionLocal


class TestEquipmentPersistence(unittest.TestCase):
    """Verify that equipment can be stored and retrieved."""

    def setUp(self):
        self.db = SessionLocal()
        self.machine_id = f"TEST-{uuid4().hex[:12].upper()}"

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_create_and_retrieve_equipment(self):
        equipment = Equipment(
            machine_id=self.machine_id,
            name="Persistence Test Machine",
            manufacturer="Test Manufacturer",
            model_number="TEST-MODEL-001",
            serial_number=f"SN-{uuid4().hex[:10].upper()}",
            asset_tag=f"TAG-{uuid4().hex[:10].upper()}",
            location="Test Facility",
            equipment_type="test_equipment",
            metadata_json={
                "source": "integration_test",
                "test_record": True,
            },
        )

        self.db.add(equipment)
        self.db.flush()

        equipment_id = equipment.id

        # Retrieve the record using its machine identifier.
        retrieved = self.db.scalar(
            select(Equipment).where(
                Equipment.machine_id == self.machine_id
            )
        )

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, equipment_id)
        self.assertEqual(
            retrieved.name,
            "Persistence Test Machine",
        )
        self.assertEqual(
            retrieved.metadata_json["source"],
            "integration_test",
        )

        # Commit, then retrieve again to verify persisted data.
        self.db.commit()
        self.db.expire_all()

        persisted = self.db.scalar(
            select(Equipment).where(
                Equipment.machine_id == self.machine_id
            )
        )

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.id, equipment_id)

        print(
            "\nEquipment persistence verified:"
            f"\n  Machine ID: {persisted.machine_id}"
            f"\n  Database ID: {persisted.id}"
            "\n  Record successfully saved and retrieved."
        )

        # Remove the test record so it does not remain in the registry.
        self.db.delete(persisted)
        self.db.commit()


if __name__ == "__main__":
    unittest.main()