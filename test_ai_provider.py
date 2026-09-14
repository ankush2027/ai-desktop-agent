# Direct script runs must enter pytest before importing application singletons.
if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


import os
import pytest

from ai import GeminiProvider
import httpx


class FakeInteractionResponse:
    def __init__(self, output_text):
        self.output_text = output_text


class FakeInteractions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeInteractionResponse("ok")


class FakeClient:
    def __init__(self):
        self.interactions = FakeInteractions()


def _patch_genai_client(fake_client):
    import ai.gemini as gemini_module

    original = gemini_module.genai.Client
    gemini_module.genai.Client = lambda api_key: fake_client
    return original


def test_provider_initializes_when_api_key_exists(monkeypatch):
    """Provider initialization should work when GEMINI_API_KEY is present."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_client = FakeClient()
    monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: fake_client)
    provider = GeminiProvider()
    assert provider is not None
    assert provider.api_key == "test-key"
    assert provider.client is fake_client


@pytest.mark.parametrize("previous", [None, "existing-key-with-exact-CaSe"])
def test_provider_loads_dotenv_file_without_real_api_call(tmp_path, monkeypatch, previous):
    """Provider initialization should load a local .env file before reading the API key."""
    import ai.gemini as gemini_module

    if previous is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", previous)
    before = dict(os.environ)
    fake_client = FakeClient()
    (tmp_path / ".env").write_text("GEMINI_API_KEY=dotenv-key\n", encoding="utf-8")
    # dotenv itself changes os.environ, so record the key before calling it.
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("GEMINI_API_KEY", "temporary-placeholder")
        isolated.delenv("GEMINI_API_KEY")
        isolated.chdir(tmp_path)
        isolated.setattr(gemini_module.genai, "Client", lambda api_key: fake_client)
        with pytest.raises(RuntimeError, match="exercise cleanup"):
            provider = GeminiProvider()
            assert provider.api_key == "dotenv-key"
            assert provider.client is fake_client
            raise RuntimeError("exercise cleanup")
    assert dict(os.environ) == before


def test_dotenv_preserves_existing_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "existing-key")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: FakeClient())
    assert GeminiProvider().api_key == "existing-key"


def test_generate_text_uses_supported_model_without_real_api_call():
    """generate_text should use the supported Interactions API and not require a real call."""
    import ai.gemini as gemini_module

    fake_client = FakeClient()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key", model_name="gemini-3.6-flash")
        result = provider.generate_text("hello")

        assert result == "ok"
        assert fake_client.interactions.calls[0]["model"] == "gemini-3.6-flash"
        assert fake_client.interactions.calls[0]["input"] == "hello"
        assert fake_client.interactions.calls[0]["timeout"] == 20.0
    finally:
        gemini_module.genai.Client = original


def test_generate_text_handles_connection_failure_without_real_api_call():
    """Connection errors should become a clean application-level exception."""
    import ai.gemini as gemini_module

    class FailingInteractions:
        def create(self, **kwargs):
            raise httpx.ConnectError("connection refused")

    fake_client = type("FakeClient", (), {"interactions": FailingInteractions()})()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key")
        try:
            provider.generate_text("hello")
            assert False, "Expected GeminiProviderError"
        except ValueError as exc:
            assert "Gemini request failed" in str(exc)
    finally:
        gemini_module.genai.Client = original


def test_generate_text_handles_timeout_without_real_api_call():
    """Timeouts should fail fast with a clean application-level exception."""
    import ai.gemini as gemini_module

    class TimeoutInteractions:
        def create(self, **kwargs):
            from google.genai._gaos.lib.compat_errors import APITimeoutError

            raise APITimeoutError("request timed out")

    fake_client = type("FakeClient", (), {"interactions": TimeoutInteractions()})()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key")
        try:
            provider.generate_text("hello")
            assert False, "Expected GeminiProviderError"
        except ValueError as exc:
            assert "Gemini request failed" in str(exc)
    finally:
        gemini_module.genai.Client = original
