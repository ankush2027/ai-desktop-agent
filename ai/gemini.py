import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
import httpx

from ai.errors import AIProviderError
from logger import error_category


class GeminiProviderError(AIProviderError):
    """Application-level error raised when Gemini cannot complete a request."""


class GeminiProvider:
    """Minimal Gemini provider wrapper using the official Google GenAI SDK."""

    DEFAULT_MODEL = "gemini-3.1-flash-lite"
    REQUEST_TIMEOUT_SECONDS = 20.0

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        load_dotenv(find_dotenv(usecwd=True), override=False)

        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.model_name = (model_name or os.getenv("GEMINI_MODEL") or "").strip() or self.DEFAULT_MODEL
        self.client = genai.Client(api_key=self.api_key)

    def generate_text(self, prompt: str) -> str:
        """Send a simple prompt to Gemini and return the model text output."""
        print("[AI] Sending request to Gemini")
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(
                        timeout=int(self.REQUEST_TIMEOUT_SECONDS * 1000),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                ),
            )
        except (
            httpx.TimeoutException,
            httpx.RequestError,
            genai_errors.APIError,
        ) as exc:
            print(f"[AI] Gemini request failed: category={error_category(exc)}")
            # DIAGNOSTIC: log the exception type and HTTP status code so the
            # caller can distinguish transient server errors (503) from auth
            # failures (401/403), invalid models (404), quota (429), etc.
            # The response body (str(exc)) is intentionally excluded: it may
            # contain private provider payload and is tested for non-disclosure.
            _exc_type = type(exc).__name__
            _status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            print(f"[AI] Gemini diagnostic: exc_type={_exc_type} http_status={_status}")
            transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)) or (
                isinstance(exc, genai_errors.APIError) and exc.code in {408, 500, 502, 503, 504}
            )
            raise GeminiProviderError("Gemini request failed.", transient=transient) from None

        text = response.text
        if not isinstance(text, str) or not text.strip():
            raise GeminiProviderError("Gemini returned no text.")
        print("[AI] Gemini response received")
        return text
