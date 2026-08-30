import os
from typing import Optional

from google import genai


class GeminiProvider:
    """Minimal Gemini provider wrapper using the official Google GenAI SDK."""

    DEFAULT_MODEL = "gemini-3.6-flash"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.model_name = model_name or os.getenv("GEMINI_MODEL") or self.DEFAULT_MODEL
        self.client = genai.Client(api_key=self.api_key)

    def generate_text(self, prompt: str) -> str:
        """Send a simple prompt to Gemini and return the model text output."""
        response = self.client.interactions.create(
            model=self.model_name,
            input=prompt,
        )

        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        if hasattr(response, "text") and response.text:
            return response.text

        return str(response)
