from typing import Optional

from ai.gemini import GeminiProvider
from ai.provider import LLMProvider
from ai.errors import AIProviderError


class ProviderManager:
    """Select and delegate requests to the active LLM provider."""

    ACTIVE_PROVIDER = "gemini"

    def __init__(self, provider: Optional[LLMProvider] = None):
        try:
            active_provider = provider if provider is not None else GeminiProvider()
        except ValueError as exc:
            raise AIProviderError("AI service unavailable.") from exc

        self.providers = {self.ACTIVE_PROVIDER: active_provider}
        self.active_provider = self.ACTIVE_PROVIDER

    def generate_text(self, prompt: str) -> str:
        """Generate text using the configured active provider."""
        try:
            return self.providers[self.active_provider].generate_text(prompt)
        except AIProviderError as exc:
            raise AIProviderError("AI service unavailable.") from exc
        except (TimeoutError, ConnectionError) as exc:
            raise AIProviderError("AI service unavailable.") from exc
