import os
from typing import Optional

from google import genai


class GeminiProvider:
    """Minimal Gemini provider wrapper using the official Google GenAI SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=self.api_key)

    def generate_text(self, prompt: str) -> str:
        """Send a simple prompt to Gemini and return the response text."""
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        if hasattr(response, "text") and response.text:
            return response.text

        return str(response)
