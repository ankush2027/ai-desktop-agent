import json

from ai.brain import AIBrain
from ai.errors import AIProviderError
from ai.provider_manager import ProviderManager


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate_text(self, prompt):
        self.calls.append(prompt)
        return json.dumps({
            "actions": [{"action": "open", "target": "brave", "params": {}}],
        })


def test_provider_manager_delegates_to_active_provider():
    provider = FakeProvider()
    manager = ProviderManager(provider=provider)

    assert manager.generate_text("hello")
    assert provider.calls == ["hello"]
    assert manager.active_provider == "gemini"
    assert list(manager.providers) == ["gemini"]


def test_brain_uses_provider_manager_without_constructing_gemini_directly():
    provider = FakeProvider()
    brain = AIBrain(provider_manager=ProviderManager(provider=provider))

    plan = brain.plan("open brave")

    assert plan["actions"][0]["target"] == "brave"
    assert len(provider.calls) == 1


def test_provider_manager_translates_connection_failure():
    class FailingProvider:
        def generate_text(self, prompt):
            raise ConnectionError("private connection detail")

    manager = ProviderManager(provider=FailingProvider())

    try:
        manager.generate_text("hello")
        assert False, "Expected AIProviderError"
    except AIProviderError as exc:
        assert str(exc) == "AI service unavailable."


def test_provider_manager_sanitizes_provider_failure():
    class FailingProvider:
        def generate_text(self, prompt):
            raise AIProviderError("provider secret")

    manager = ProviderManager(provider=FailingProvider())

    try:
        manager.generate_text("hello")
        assert False, "Expected AIProviderError"
    except AIProviderError as exc:
        assert str(exc) == "AI service unavailable."
