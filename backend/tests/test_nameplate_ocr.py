import json
import sys
import unittest
from pathlib import Path

# Ensure the backend directory is importable when running this test directly.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.nameplate_ocr import NameplateOCRService


class TestNameplateOCR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = NameplateOCRService()
        cls.project_root = BACKEND_DIR.parent
        cls.sample_dir = cls.project_root / "data" / "sample_images"

    def test_missing_image_raises_error(self):
        missing_path = self.sample_dir / "this_image_does_not_exist.jpg"

        with self.assertRaises(FileNotFoundError):
            self.service.inspect(missing_path)

    def test_unsupported_file_extension_raises_error(self):
        unsupported_path = self.sample_dir / "document.pdf"

        with self.assertRaises(FileNotFoundError):
            self.service.inspect(unsupported_path)

    def test_parse_labelled_nameplate_fields(self):
        sample_text = """
        Manufacturer: Siemens
        Model: ABC-123
        Serial Number: SN-98765
        Voltage: 400 V
        Power: 5.5 kW
        Frequency: 50 Hz
        """

        fields = self.service._parse_fields(sample_text)

        self.assertEqual(fields.manufacturer, "Siemens")
        self.assertEqual(fields.model_number, "ABC-123")
        self.assertEqual(fields.serial_number, "SN-98765")
        self.assertEqual(fields.voltage, "400 V")
        self.assertEqual(fields.power, "5.5 kW")
        self.assertEqual(fields.frequency, "50 Hz")

    def test_parse_unknown_fields_as_none(self):
        fields = self.service._parse_fields(
            "Industrial equipment\nNo readable model information"
        )

        self.assertIsNone(fields.model_number)
        self.assertIsNone(fields.serial_number)

    def test_inspect_real_sample_if_available(self):
        if not self.sample_dir.exists():
            self.skipTest(
                f"Sample image directory does not exist: {self.sample_dir}"
            )

        candidates = [
            path
            for path in self.sample_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in self.service.SUPPORTED_EXTENSIONS
        ]

        if not candidates:
            self.skipTest("No sample images are available for OCR testing.")

        image_path = candidates[0]
        result = self.service.inspect(image_path)

        print(f"\nOCR sample: {image_path.name}")
        print(json.dumps(result.model_dump(), indent=2))

        self.assertTrue(result.requires_human_review)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 100.0)
        self.assertIsInstance(result.raw_text, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)