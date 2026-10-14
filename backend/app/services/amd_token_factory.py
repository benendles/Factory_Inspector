import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class AMDTokenFactory:
    def __init__(self):
        api_key = os.getenv("AMD_TOKEN_FACTORY_API_KEY")
        base_url = os.getenv("AMD_TOKEN_FACTORY_BASE_URL")
        self.model = os.getenv("AMD_VISION_MODEL")

        if not api_key:
            raise ValueError(
                "AMD_TOKEN_FACTORY_API_KEY is missing from .env"
            )

        if not base_url:
            raise ValueError(
                "AMD_TOKEN_FACTORY_BASE_URL is missing from .env"
            )

        if not self.model:
            raise ValueError(
                "AMD_VISION_MODEL is missing from .env"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        return response.choices[0].message.content or ""