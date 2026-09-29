"""Text-only Groq fallback using the same LLMProvider interface as Gemini."""

import os
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from groq import APIError, Groq

from ai.errors import AIProviderError


class GroqProvider:
    MODEL = "openai/gpt-oss-120b"
    REQUEST_TIMEOUT_SECONDS = 20.0

    def __init__(self, api_key: Optional[str] = None):
        load_dotenv(find_dotenv(usecwd=True), override=False)
        key = (api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")).strip()
        if not key:
            raise AIProviderError("Groq API key is not configured.")
        self.client = Groq(
            api_key=key,
            base_url="https://api.groq.com",
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def generate_text(self, prompt: str) -> str:
        print("[AI] Sending request to Groq")
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
        except APIError:
            # SDK errors can contain credentials, prompts and response bodies.
            raise AIProviderError("Groq request failed.") from None

        choices = getattr(response, "choices", None)
        if not choices or len(choices) != 1:
            raise AIProviderError("Groq returned no complete text response.")
        choice = choices[0]
        message = getattr(choice, "message", None)
        text = getattr(message, "content", None)
        if (getattr(choice, "finish_reason", None) != "stop"
                or getattr(message, "tool_calls", None)
                or not isinstance(text, str) or not text.strip()):
            raise AIProviderError("Groq returned no complete text response.")
        print("[AI] Groq response received")
        return text
