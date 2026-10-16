import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

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

    def test_parse_siemens_tesseract_label_variants(self):
        fields = self.service._parse_fields(
            "SIEMENS.\n\n3~ Motor\n"
            "Type 1LE1001-1AB23-4AA4\n\nSIN Q8W123456"
        )

        self.assertEqual(fields.manufacturer, "SIEMENS")
        self.assertEqual(fields.model_number, "1LE1001-1AB23-4AA4")
        self.assertEqual(fields.serial_number, "Q8W123456")
        self.assertIsNone(fields.voltage)
        self.assertIsNone(fields.power)
        self.assertIsNone(fields.frequency)

    def test_parse_unknown_fields_as_none(self):
        fields = self.service._parse_fields(
            "Industrial equipment\nNo readable model information"
        )

        self.assertIsNone(fields.model_number)
        self.assertIsNone(fields.serial_number)

    def test_richer_tesseract_result_wins_when_confidence_is_comparable(self):
        sparse_text = (
            "SIEMENS\nType 1LE1001-1AB23-4AA4\nSIN Q8W123456"
        )
        rich_text = (
            "SIEMENS\nType 1LE1001-1AB23-4AA4\nSIN Q8W123456\n"
            "400 V\n7.5 kW\n50 Hz\n14.4 A\n1460 rpm"
        )

        responses = iter(
            [(sparse_text, 84.0), (rich_text, 76.0)] + [("", 0.0)] * 14
        )

        with (
            patch.object(
                NameplateOCRService,
                "_preprocess_variants",
                return_value=[Image.new("L", (1, 1))] * 4,
            ),
            patch.object(
                NameplateOCRService,
                "_run_tesseract",
                side_effect=lambda *_args: next(responses),
            ),
        ):
            text, confidence, notes = self.service._best_tesseract_result(
                Image.new("L", (1, 1))
            )

        fields = self.service._parse_fields(text)
        self.assertEqual(text, rich_text)
        self.assertEqual(confidence, 76.0)
        self.assertEqual(fields.power, "7.5 kW")
        self.assertEqual(fields.voltage, "400 V")
        self.assertEqual(fields.frequency, "50 Hz")
        self.assertEqual(fields.current, "14.4 A")
        self.assertEqual(fields.speed_rpm, "1460 rpm")
        self.assertEqual(notes, [])

    def test_conflicting_tesseract_candidates_are_flagged_not_merged(self):
        first_text = "Model: MOTOR-100\nSerial: SN-001\n400 V"
        second_text = "Model: MOTOR-200\nSerial: SN-001\n400 V"
        responses = iter(
            [(first_text, 83.0), (second_text, 80.0)] + [("", 0.0)] * 14
        )

        with (
            patch.object(
                NameplateOCRService,
                "_preprocess_variants",
                return_value=[Image.new("L", (1, 1))] * 4,
            ),
            patch.object(
                NameplateOCRService,
                "_run_tesseract",
                side_effect=lambda *_args: next(responses),
            ),
        ):
            text, _confidence, notes = self.service._best_tesseract_result(
                Image.new("L", (1, 1))
            )

        self.assertEqual(
            self.service._parse_fields(text).model_number,
            "MOTOR-100",
        )
        self.assertTrue(
            any("conflicting model_number candidates" in note for note in notes)
        )
        self.assertTrue(any("MOTOR-100, MOTOR-200" in note for note in notes))

    def test_conflict_notes_ignore_implausible_noise_but_keep_current_conflict(self):
        selected_text = "Type 1LE1001-1AB23-4AA4\nCurrent 14.4A"
        noisy_text = "Type cea\nCurrent: 5\na"
        plausible_conflict_text = (
            "Type 1LE1001-1AB23-4AA4\nCurrent 144A"
        )
        responses = iter(
            [
                (selected_text, 84.0),
                (noisy_text, 83.0),
                (plausible_conflict_text, 82.0),
            ]
            + [("", 0.0)] * 13
        )

        with (
            patch.object(
                NameplateOCRService,
                "_preprocess_variants",
                return_value=[Image.new("L", (1, 1))] * 4,
            ),
            patch.object(
                NameplateOCRService,
                "_run_tesseract",
                side_effect=lambda *_args: next(responses),
            ),
        ):
            text, _confidence, notes = self.service._best_tesseract_result(
                Image.new("L", (1, 1))
            )

        self.assertEqual(text, selected_text)
        self.assertFalse(
            any("conflicting model_number candidates" in note for note in notes)
        )
        current_note = next(
            note
            for note in notes
            if "conflicting current candidates" in note
        )
        self.assertIn("14.4A, 144A", current_note)
        self.assertNotIn("5\na", current_note)

    def test_empty_tesseract_results_remain_empty(self):
        with (
            patch.object(
                NameplateOCRService,
                "_preprocess_variants",
                return_value=[Image.new("L", (1, 1))] * 4,
            ),
            patch.object(
                NameplateOCRService,
                "_run_tesseract",
                return_value=("", 0.0),
            ),
        ):
            text, confidence, notes = self.service._best_tesseract_result(
                Image.new("L", (1, 1))
            )

        self.assertEqual(text, "")
        self.assertEqual(confidence, 0.0)
        self.assertEqual(notes, [])

    def test_low_confidence_richer_result_does_not_displace_clearer_result(self):
        low_confidence_rich_text = (
            "Model: UNCERTAIN-100\nSerial: UNCERTAIN-SN\n"
            "400 V\n7.5 kW\n50 Hz"
        )
        clearer_text = "Model: CLEAR-100"
        responses = iter(
            [(low_confidence_rich_text, 30.0), (clearer_text, 72.0)]
            + [("", 0.0)] * 14
        )

        with (
            patch.object(
                NameplateOCRService,
                "_preprocess_variants",
                return_value=[Image.new("L", (1, 1))] * 4,
            ),
            patch.object(
                NameplateOCRService,
                "_run_tesseract",
                side_effect=lambda *_args: next(responses),
            ),
        ):
            text, confidence, _notes = self.service._best_tesseract_result(
                Image.new("L", (1, 1))
            )

        self.assertEqual(text, clearer_text)
        self.assertEqual(confidence, 72.0)

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
