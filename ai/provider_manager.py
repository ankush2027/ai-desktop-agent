import platform
from typing import Optional

from ai.gemini import GeminiProvider
from ai.provider import LLMProvider
from ai.errors import AIProviderError


class ProviderManager:
    """Gemini first; one macOS fallback attempt for transient provider failures."""

    ACTIVE_PROVIDER = "gemini"

    def __init__(self, provider: Optional[LLMProvider] = None, *, fallback_provider: Optional[LLMProvider] = None):
        try:
            active_provider = provider if provider is not None else GeminiProvider()
        except ValueError as exc:
            raise AIProviderError("AI service unavailable.") from exc

        self.providers = {self.ACTIVE_PROVIDER: active_provider}
        self.active_provider = self.ACTIVE_PROVIDER
        self._fallback_provider = fallback_provider
        # Explicit provider injection stays isolated unless a fallback is also supplied.
        self._fallback_enabled = provider is None or fallback_provider is not None

    def generate_text(self, prompt: str) -> str:
        """Return provider text only; parsing, policy and execution happen later."""
        try:
            return self.providers[self.active_provider].generate_text(prompt)
        except AIProviderError as exc:
            transient = exc.transient
        except (TimeoutError, ConnectionError):
            transient = True

        if not transient or platform.system() != "Darwin" or not self._fallback_enabled:
            raise AIProviderError("AI service unavailable.") from None

        # This block is deliberately outside the primary try: no recursion,
        # provider cycling, or retry after planning/policy/execution rejection.
        print("[AI] Gemini temporarily unavailable; requesting Groq fallback")
        try:
            if self._fallback_provider is None:
                from ai.groq import GroqProvider
                self._fallback_provider = GroqProvider()
            return self._fallback_provider.generate_text(prompt)
        except (AIProviderError, TimeoutError, ConnectionError, ImportError):
            raise AIProviderError("AI service unavailable.") from None
