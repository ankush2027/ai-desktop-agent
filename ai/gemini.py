import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai._gaos.lib import compat_errors
import httpx


class GeminiProviderError(ValueError):
    """Application-level error raised when Gemini cannot complete a request."""


class GeminiProvider:
    """Minimal Gemini provider wrapper using the official Google GenAI SDK."""

    DEFAULT_MODEL = "gemini-3.1-flash-lite"
    REQUEST_TIMEOUT_SECONDS = 20.0

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        load_dotenv(find_dotenv(usecwd=True), override=False)

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.model_name = model_name or os.getenv("GEMINI_MODEL") or self.DEFAULT_MODEL
        self.client = genai.Client(api_key=self.api_key)

    def generate_text(self, prompt: str) -> str:
        """Send a simple prompt to Gemini and return the model text output."""
        print("[AI] Sending request to Gemini")
        try:
            response = self.client.interactions.create(
                model=self.model_name,
                input=prompt,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except (
            httpx.TimeoutException,
            httpx.RequestError,
            genai_errors.APIError,
            compat_errors.APIError,
            compat_errors.NoResponseError,
        ) as exc:
            reason = str(exc).splitlines()[0][:200] or exc.__class__.__name__
            print(f"[AI] Gemini request failed: {reason}")
            raise GeminiProviderError(f"Gemini request failed: {reason}") from exc

        if hasattr(response, "output_text") and response.output_text:
            print("[AI] Gemini response received")
            return response.output_text

        if hasattr(response, "text") and response.text:
            print("[AI] Gemini response received")
            return response.text

        print("[AI] Gemini response received")
        return str(response)
