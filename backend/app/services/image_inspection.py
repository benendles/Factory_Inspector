import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.amd_token_factory import AMDTokenFactory

logger = logging.getLogger(__name__)


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
    confidence: Literal["low", "medium", "high"]


class ImageInspectionResult(BaseModel):
    """Structured result returned by a factory image inspection."""

    machine_id: str
    observations: list[VisualObservation] = Field(default_factory=list)
    requires_human_review: bool = True
    summary: str


class ImageInspectionService:
    """Inspect factory images using an AMD vision-language model."""

    def __init__(self, amd_client: AMDTokenFactory | None = None):
        self.amd = amd_client or AMDTokenFactory()

    def inspect_image(
        self,
        image_path: str | Path,
        machine_id: str = "UNKNOWN",
    ) -> ImageInspectionResult:
        path = Path(image_path)

        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

        mime_type, _ = mimetypes.guess_type(path.name)

        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError(
                "Unsupported image type. Use JPEG, PNG, or WEBP."
            )

        image_bytes = path.read_bytes()
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{encoded_image}"

        prompt = f"""
You are a visual inspection assistant for an industrial factory.

Inspect the supplied image for possible visible equipment anomalies.

Machine ID: {machine_id}

Return ONLY a valid JSON object with this exact structure:
{{
  "machine_id": "{machine_id}",
  "observations": [
    {{
      "anomaly_type": "short_identifier",
      "description": "Describe visible evidence without inventing causes.",
      "location_description": "Approximate location in the image.",
      "confidence": "low"
    }}
  ],
  "requires_human_review": true,
  "summary": "Brief summary of the visual inspection."
}}

Rules:
- The confidence value must be low, medium, or high.
- Report visible evidence, not an unverified diagnosis.
- Do not infer temperature, pressure, or vibration from an image.
- Do not invent objects or abnormalities that are not visible.
- If no anomaly is apparent, return an empty observations list.
- Treat the image as evidence, not proof of equipment safety.
- Set requires_human_review to true if an anomaly is observed or
  if the image is insufficient to assess the equipment.
- A normal-looking image does not establish that a machine is safe.
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
            raise ValueError("AMD model returned an empty inspection result.")

        # Handle responses wrapped in Markdown code fences.
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

        try:
            data = json.loads(cleaned)
            result = ImageInspectionResult.model_validate(data)

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "AMD returned an invalid inspection response: %s",
                exc,
            )
            raise ValueError(
                "AMD returned a response that did not match "
                "the required inspection JSON schema."
            ) from exc

        # The caller-supplied machine ID is authoritative.
        result.machine_id = machine_id

        return result