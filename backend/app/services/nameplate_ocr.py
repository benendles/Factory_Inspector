import os
import re
import shutil
from pathlib import Path
from typing import Literal

import pytesseract
from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError
from google.cloud import vision
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel, Field


IdentificationStatus = Literal[
    "text_extracted",
    "limited_text",
    "no_text_detected",
]


class NameplateFields(BaseModel):
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    voltage: str | None = None
    power: str | None = None
    frequency: str | None = None
    current: str | None = None
    speed_rpm: str | None = None
    power_factor: str | None = None


class NameplateOCRResult(BaseModel):
    image_path: str
    raw_text: str
    fields: NameplateFields
    status: IdentificationStatus
    confidence: float = Field(ge=0.0, le=100.0)
    requires_human_review: bool = True
    notes: list[str] = Field(default_factory=list)


class NameplateOCRService:
    """
    Extract candidate equipment specifications from nameplate images.

    Google Cloud Vision is the preferred OCR provider.
    Tesseract is used as a fallback if Google Vision fails or is not configured.

    OCR results are candidates only and must not be treated as verified
    equipment specifications without human or authoritative-source review.
    """

    SUPPORTED_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
    }

    OCR_CONFIGS = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
        "--oem 3 --psm 4",
        "--oem 3 --psm 12",
    ]

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        provider: Literal["auto", "google", "tesseract"] = "auto",
    ):
        """
        Args:
            tesseract_cmd: Optional path to the Tesseract executable.
            provider:
                auto       - Prefer Google Vision, fall back to Tesseract.
                google     - Require Google Vision.
                tesseract  - Use only local Tesseract OCR.
        """
        if provider not in {"auto", "google", "tesseract"}:
            raise ValueError(
                "provider must be 'auto', 'google', or 'tesseract'."
            )

        self.provider = provider
        self.google_client = None
        self.google_setup_error: str | None = None
        self.tesseract_available = False

        # Load the .env file from the project root.
        # nameplate_ocr.py is:
        # backend/app/services/nameplate_ocr.py
        project_root = Path(__file__).resolve().parents[3]
        load_dotenv(project_root / ".env")

        api_key = os.getenv("GOOGLE_CLOUD_VISION_API_KEY", "").strip()

        if provider in {"auto", "google"} and api_key:
            try:
                self.google_client = vision.ImageAnnotatorClient(
                    client_options={"api_key": api_key}
                )
            except Exception as exc:
                self.google_setup_error = (
                    f"Google Vision client initialization failed: {exc}"
                )

        elif provider == "google":
            self.google_setup_error = (
                "GOOGLE_CLOUD_VISION_API_KEY is missing from the project .env."
            )

        # Configure Tesseract for local OCR and fallback.
        if provider in {"auto", "tesseract"}:
            executable = tesseract_cmd or shutil.which("tesseract")

            if executable:
                pytesseract.pytesseract.tesseract_cmd = executable
                self.tesseract_available = True

        if provider == "tesseract" and not self.tesseract_available:
            raise RuntimeError(
                "Tesseract executable was not found. Install it with "
                "'brew install tesseract', then run 'tesseract --version'."
            )

        if provider == "google" and self.google_client is None:
            raise RuntimeError(
                self.google_setup_error
                or "Could not initialize the Google Cloud Vision client."
            )

        if provider == "auto":
            if self.google_client is None and not self.tesseract_available:
                raise RuntimeError(
                    "No OCR provider is available. Configure "
                    "GOOGLE_CLOUD_VISION_API_KEY or install Tesseract."
                )

    @staticmethod
    def _preprocess_variants(image: Image.Image) -> list[Image.Image]:
        """Generate image variants for local Tesseract OCR."""
        image = ImageOps.exif_transpose(image)
        grayscale = ImageOps.grayscale(image)

        if grayscale.width < 1800:
            scale = 1800 / grayscale.width
            grayscale = grayscale.resize(
                (
                    1800,
                    max(1, int(grayscale.height * scale)),
                ),
                Image.Resampling.LANCZOS,
            )

        contrast = ImageEnhance.Contrast(grayscale).enhance(2.0)
        sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)
        sharp = sharp.filter(ImageFilter.SHARPEN)

        threshold = sharp.point(lambda pixel: 255 if pixel > 155 else 0)

        return [grayscale, contrast, sharp, threshold]

    @staticmethod
    def _run_tesseract(
        image: Image.Image,
        config: str,
    ) -> tuple[str, float]:
        """Return Tesseract text and its mean word confidence."""
        text = pytesseract.image_to_string(
            image,
            config=config,
        ).strip()

        data = pytesseract.image_to_data(
            image,
            config=config,
            output_type=pytesseract.Output.DICT,
        )

        scores: list[float] = []

        for value in data.get("conf", []):
            try:
                score = float(value)
                if score >= 0:
                    scores.append(score)
            except (TypeError, ValueError):
                continue

        confidence = sum(scores) / len(scores) if scores else 0.0

        return text, confidence

    @classmethod
    def _best_tesseract_result(
        cls,
        image: Image.Image,
    ) -> tuple[str, float]:
        """Try several preprocessing and segmentation combinations."""
        best_text = ""
        best_confidence = 0.0
        best_score = float("-inf")

        for variant in cls._preprocess_variants(image):
            for config in cls.OCR_CONFIGS:
                text, confidence = cls._run_tesseract(variant, config)

                useful_characters = sum(char.isalnum() for char in text)
                score = confidence + min(useful_characters, 200) * 0.03

                if text and score > best_score:
                    best_text = text
                    best_confidence = confidence
                    best_score = score

        return best_text, best_confidence

    def _run_google_vision(
        self,
        image_path: Path,
    ) -> tuple[str, float]:
        """
        Run Google Cloud Vision document text detection.

        Google Vision does not provide a directly comparable overall
        document-confidence score here. A neutral 0.0 is returned for
        confidence so we do not pretend that text presence is accuracy.
        """
        if self.google_client is None:
            raise RuntimeError(
                self.google_setup_error
                or "Google Cloud Vision is not configured."
            )

        image = vision.Image(content=image_path.read_bytes())

        response = self.google_client.document_text_detection(image=image)

        if response.error.message:
            raise RuntimeError(
                f"Google Cloud Vision error: {response.error.message}"
            )

        annotation = response.full_text_annotation
        text = annotation.text.strip() if annotation else ""

        return text, 0.0

    @staticmethod
    def _extract_field(
        text: str,
        patterns: list[str],
    ) -> str | None:
        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE | re.MULTILINE,
            )

            if match:
                value = match.group(1).strip(" \t:;,.|-")

                if value:
                    return value[:100]

        return None

    @classmethod
    def _parse_fields(cls, text: str) -> NameplateFields:
        """Extract candidate fields from OCR text."""
        labelled_patterns = {
            "manufacturer": [
                r"^\s*(?:manufacturer|mfr|make|brand)\s*[:#=-]\s*(.{2,80})$",
                r"^\s*(?:manufacturer|mfr|make|brand)\s+(.{2,80})$",
            ],
            "model_number": [
                r"^\s*(?:model|model\s*(?:no|number|#)|type)\s*[:#=-]\s*([A-Z0-9][A-Z0-9./_-]{1,50})\s*$",
            ],
            "serial_number": [
                r"^\s*(?:serial(?:\s*(?:no|number|#))?|s/?n)\s*[:#=-]\s*([A-Z0-9][A-Z0-9./_-]{1,50})\s*$",
            ],
            "voltage": [
                r"^\s*(?:rated\s*)?(?:voltage|volt|volts|u)\s*[:= -]\s*([0-9.,/ -]+\s*(?:VAC|VDC|KV|V)?)\s*$",
            ],
            "power": [
                r"^\s*(?:rated\s*)?(?:power|output|p)\s*[:= -]\s*([0-9.,]+\s*(?:KW|W|HP|MW))\s*$",
            ],
            "frequency": [
                r"^\s*(?:frequency|freq|hz|f)\s*[:= -]\s*([0-9.,]+\s*(?:HZ)?)\s*$",
            ],
            "current": [
                r"^\s*(?:rated\s*)?(?:current|amps?|a)\s*[:= -]\s*([0-9.,/ -]+\s*A?)\s*$",
            ],
            "speed_rpm": [
                r"^\s*(?:speed|rated\s*speed|n)\s*[:= -]\s*([0-9.,]+\s*(?:RPM|R/MIN)?)\s*$",
            ],
            "power_factor": [
                r"^\s*(?:power\s*factor|cos\s*[φΦф]|cosphi)\s*[:= -]\s*(0?\.\d+|1(?:\.0+)?)\s*$",
            ],
        }

        values = {
            field: cls._extract_field(text, patterns)
            for field, patterns in labelled_patterns.items()
        }

        # Unlabelled table values are candidates and require verification.
        fallback_patterns = {
            "voltage": [
                r"(?<![\d.])(\d{2,4}\s*/\s*\d{2,4}\s*V)\b",
                r"(?<![\d.])(\d{2,4}\s*V(?:AC|DC)?)\b",
            ],
            "power": [
                r"(?<![\d.])(\d+(?:[.,]\d+)?\s*(?:kW|MW|HP))\b",
                r"(?<![\d.])(\d+(?:[.,]\d+)?\s*W)\b",
            ],
            "frequency": [
                r"(?<![\d.])(\d{2,3}(?:[.,]\d+)?\s*Hz)\b",
            ],
            "current": [
                r"(?<![\d.])(\d+(?:[.,]\d+)?\s*/\s*\d+(?:[.,]\d+)?\s*A)\b",
                r"(?<![\d.])(\d+(?:[.,]\d+)?\s*A)\b",
            ],
            "speed_rpm": [
                r"(?<![\d.])(\d{3,5}\s*RPM)\b",
                r"(?<![\d.])(\d{3,5}\s*r/min)\b",
            ],
            "power_factor": [
                r"\bcos\s*[φΦф]\s*[:= -]?\s*(0?\.\d+|1(?:\.0+)?)\b",
            ],
        }

        for field, patterns in fallback_patterns.items():
            if values[field] is None:
                values[field] = cls._extract_field(text, patterns)

        return NameplateFields(**values)

    def inspect(self, image_path: str | Path) -> NameplateOCRResult:
        """Extract text, parse candidate fields, and flag uncertain results."""
        path = Path(image_path).expanduser().resolve()

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Nameplate image not found: {path}")

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported image format: {path.suffix}. "
                f"Supported formats: "
                f"{', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        try:
            with Image.open(path) as original:
                original.verify()

            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original.copy())

        except Exception as exc:
            raise ValueError(
                f"Could not read nameplate image: {exc}"
            ) from exc

        notes: list[str] = []
        provider_used: str

        # Try Google Vision first unless Tesseract was explicitly requested.
        if self.provider in {"auto", "google"}:
            try:
                raw_text, confidence = self._run_google_vision(path)
                provider_used = "google_cloud_vision"

            except (GoogleAPICallError, RuntimeError, OSError) as exc:
                if self.provider == "google":
                    raise RuntimeError(
                        f"Google Cloud Vision OCR failed: {exc}"
                    ) from exc

                if not self.tesseract_available:
                    raise RuntimeError(
                        "Google Cloud Vision failed and Tesseract is "
                        f"unavailable. Details: {exc}"
                    ) from exc

                notes.append(
                    "Google Cloud Vision failed; Tesseract fallback was used. "
                    f"Reason: {exc}"
                )
                raw_text, confidence = self._best_tesseract_result(image)
                provider_used = "tesseract_fallback"

        else:
            try:
                raw_text, confidence = self._best_tesseract_result(image)
                provider_used = "tesseract"
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError(
                    "Tesseract could not be launched. Check its installation "
                    "and PATH."
                ) from exc
            except pytesseract.TesseractError as exc:
                raise RuntimeError(f"Tesseract OCR failed: {exc}") from exc

        fields = self._parse_fields(raw_text)

        if not raw_text.strip():
            status: IdentificationStatus = "no_text_detected"
            notes.append(
                "No text was detected. Try a sharper, closer, well-lit image."
            )
        elif len(raw_text.strip()) < 20:
            status = "limited_text"
            notes.append(
                "Only a small amount of text was detected. "
                "Some nameplate details may be missing or misread."
            )
        else:
            status = "text_extracted"
            notes.append(
                "Extracted specifications are candidates and have not been "
                "verified against a registry or manufacturer documentation."
            )

        if provider_used != "google_cloud_vision":
            if confidence < 50:
                notes.append(
                    "Tesseract OCR confidence is low. Review the raw text "
                    "and image manually."
                )
        else:
            notes.append(
                "Google Cloud Vision does not supply the Tesseract-style "
                "confidence score used by this service; confidence is "
                "reported as 0.0, not as a probability of correctness."
            )

        if not fields.model_number:
            notes.append("No clearly labelled model number was extracted.")

        if not fields.serial_number:
            notes.append("No clearly labelled serial number was extracted.")

        if any(
            [
                fields.voltage,
                fields.power,
                fields.frequency,
                fields.current,
                fields.speed_rpm,
                fields.power_factor,
            ]
        ):
            notes.append(
                "Some electrical specifications may have been extracted "
                "from unlabelled table fragments; verify them against the "
                "original nameplate."
            )

        notes.append(f"OCR provider used: {provider_used}.")

        return NameplateOCRResult(
            image_path=str(path),
            raw_text=raw_text,
            fields=fields,
            status=status,
            confidence=round(confidence, 2),
            requires_human_review=True,
            notes=notes,
        )