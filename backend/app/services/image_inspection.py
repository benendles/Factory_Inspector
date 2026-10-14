import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.amd_token_factory import AMDTokenFactory

logger = logging.getLogger(__name__)


ConfidenceLevel = Literal["low", "medium", "high"]

IdentificationStatus = Literal[
    "identified",
    "partially_identified",
    "unidentified",
]


class EquipmentIdentification(BaseModel):
    """Equipment identity inferred from the supplied image."""

    equipment_type: str = Field(
        description=(
            "General equipment category, such as electric motor, "
            "pump, conveyor, compressor, or unknown."
        )
    )

    manufacturer: str | None = Field(
        default=None,
        description="Manufacturer, only when supported by visible evidence.",
    )

    model_number: str | None = Field(
        default=None,
        description="Visible model number, if it can be read reliably.",
    )

    serial_number: str | None = Field(
        default=None,
        description="Visible serial number, if it can be read reliably.",
    )

    asset_tag: str | None = Field(
        default=None,
        description="Visible factory asset identifier, if present.",
    )

    visible_components: list[str] = Field(
        default_factory=list,
        description="Components visibly identifiable in the image.",
    )

    visible_markings: list[str] = Field(
        default_factory=list,
        description=(
            "Relevant text or markings visible on the equipment. "
            "Transcription may require separate OCR verification."
        ),
    )

    identification_status: IdentificationStatus

    confidence: ConfidenceLevel

    identification_notes: list[str] = Field(default_factory=list)


class VisualObservation(BaseModel):
    """A possible anomaly observed in a factory image."""

    anomaly_type: str = Field(
        description="Short identifier for the possible anomaly."
    )

    description: str = Field(
        description="What is visibly observable in the image."
    )

    location_description: str = Field(
        description="Approximate location of the observation in the image."
    )

    confidence: ConfidenceLevel


class ImageInspectionResult(BaseModel):
    """Combined equipment identification and visual inspection result."""

    machine_id: str

    equipment: EquipmentIdentification

    observations: list[VisualObservation] = Field(default_factory=list)

    requires_human_review: bool = True

    summary: str


class ImageInspectionService:
    """Identify visible equipment and inspect factory images using AMD."""

    def __init__(self, amd_client: AMDTokenFactory | None = None):
        self.amd = amd_client or AMDTokenFactory()

    @staticmethod
    def _clean_json_response(content: str) -> str:
        """Remove Markdown code fences if the model adds them."""

        cleaned = content.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

        return cleaned

    @staticmethod
    def _validate_identification_status(
        equipment: EquipmentIdentification,
    ) -> EquipmentIdentification:
        """
        Prevent unsupported claims of exact identification.

        A specific model or serial number alone does not prove that
        the equipment has been matched to a verified factory asset.
        """

        if equipment.equipment_type.strip().lower() in {
            "",
            "unknown",
            "unidentified",
            "none",
        }:
            equipment.equipment_type = "unknown"
            equipment.identification_status = "unidentified"

        if (
            equipment.identification_status == "identified"
            and equipment.equipment_type == "unknown"
        ):
            equipment.identification_status = "unidentified"

        if equipment.identification_status == "identified":
            equipment.identification_notes.append(
                "Visual identification is model output and has not "
                "been independently verified against a factory registry."
            )

        return equipment

    def inspect_image(
        self,
        image_path: str | Path,
        machine_id: str = "UNKNOWN",
    ) -> ImageInspectionResult:
        """
        Identify visible equipment and report possible visual anomalies.

        This method does not verify equipment identity against a registry,
        establish a definitive fault diagnosis, or certify equipment safety.
        """

        path = Path(image_path)

        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        mime_type, _ = mimetypes.guess_type(path.name)

        if mime_type not in {
            "image/jpeg",
            "image/png",
            "image/webp",
        }:
            raise ValueError(
                "Unsupported image type. Use JPEG, PNG, or WEBP."
            )

        image_bytes = path.read_bytes()

        if not image_bytes:
            raise ValueError(f"Image file is empty: {path}")

        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{encoded_image}"

        prompt = f"""
You are an industrial equipment identification and visual inspection
assistant for Factory Inspector.

Inspect the supplied factory image.

The caller supplied this machine ID: {machine_id}

IMPORTANT:
The machine ID may be UNKNOWN. Do not treat it as proof of equipment
identity. Do not invent factory registry records.

Return ONLY a valid JSON object matching this structure:

{{
  "machine_id": "{machine_id}",
  "equipment": {{
    "equipment_type": "electric_motor",
    "manufacturer": null,
    "model_number": null,
    "serial_number": null,
    "asset_tag": null,
    "visible_components": [
      "motor housing"
    ],
    "visible_markings": [],
    "identification_status": "partially_identified",
    "confidence": "medium",
    "identification_notes": []
  }},
  "observations": [
    {{
      "anomaly_type": "visible_damage",
      "description": "Describe only the visible evidence.",
      "location_description": "Approximate location in the image.",
      "confidence": "low"
    }}
  ],
  "requires_human_review": true,
  "summary": "Brief summary of identification and visual inspection."
}}

EQUIPMENT IDENTIFICATION RULES:

1. Identify the broad equipment category when reasonably possible.
   Examples include electric motor, pump, conveyor, compressor,
   industrial robot, valve, or control panel.

2. If the equipment category cannot be established, use "unknown".

3. Identify only components that are actually visible.

4. Report manufacturer, model number, serial number, and asset tag
   only when there is visible evidence supporting those values.

5. Never invent a manufacturer, model number, serial number,
   asset tag, specification, or factory registry record.

6. If markings are unreadable, set the corresponding field to null
   and explain the limitation in identification_notes.

7. Use "identified" only when the image supports a reasonably specific
   equipment identification. Use "partially_identified" when the broad
   equipment category is known but important identity details are
   missing. Use "unidentified" when the equipment cannot be identified.

8. Confidence describes visual identification confidence, not proof
   that the equipment identity has been independently verified.

VISUAL INSPECTION RULES:

1. Report visible evidence, not an unverified diagnosis.

2. Do not infer temperature, pressure, vibration, internal damage,
   or electrical condition from the image alone.

3. Do not invent objects, damage, leaks, or abnormalities.

4. If no anomaly is apparent, return an empty observations list.

5. Set requires_human_review to true when an anomaly is observed,
   the image is insufficient for assessment, or identification
   limitations prevent a reliable conclusion.

6. A normal-looking image does not establish that a machine is safe.

Return valid JSON only. Do not use Markdown fences.
"""

        response = self.amd.client.chat.completions.create(
            model=self.amd.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                            },
                        },
                    ],
                }
            ],
            temperature=0,
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError(
                "AMD model returned an empty inspection result."
            )

        cleaned = self._clean_json_response(content)

        try:
            data = json.loads(cleaned)
            result = ImageInspectionResult.model_validate(data)

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "AMD returned an invalid identification/inspection "
                "response: %s",
                exc,
            )

            raise ValueError(
                "AMD returned a response that did not match the "
                "required equipment identification and inspection schema."
            ) from exc

        # The caller-supplied ID remains authoritative.
        result.machine_id = machine_id

        result.equipment = self._validate_identification_status(
            result.equipment
        )

        if result.observations:
            result.requires_human_review = True

        return result