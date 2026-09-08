from typing import Optional

from ai.gemini import GeminiProvider
from ai.provider import LLMProvider


class ProviderManager:
    """Select and delegate requests to the active LLM provider."""

    ACTIVE_PROVIDER = "gemini"

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.providers = {
            self.ACTIVE_PROVIDER: provider if provider is not None else GeminiProvider(),
        }
        self.active_provider = self.ACTIVE_PROVIDER

    def generate_text(self, prompt: str) -> str:
        """Generate text using the configured active provider."""
        return self.providers[self.active_provider].generate_text(prompt)
