from typing import Protocol


class LLMProvider(Protocol):
    """Interface required by AIBrain from an LLM provider."""

    def generate_text(self, prompt: str) -> str:
        ...
