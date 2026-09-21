# Direct script runs must enter pytest before importing application singletons.
if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


import os
import pytest

from ai import GeminiProvider
import httpx


class FakeContentResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeContentResponse("ok")


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


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
    """generate_text should use the public generate_content API and not require a real call."""
    import ai.gemini as gemini_module

    fake_client = FakeClient()
    original = _patch_genai_client(fake_client)

    try:
        provider = GeminiProvider(api_key="test-key", model_name="gemini-3.6-flash")
        result = provider.generate_text("hello")

        assert result == "ok"
        assert fake_client.models.calls[0]["model"] == "gemini-3.6-flash"
        assert fake_client.models.calls[0]["contents"] == "hello"
        options = fake_client.models.calls[0]["config"].http_options
        assert options.timeout == 20_000
        assert options.retry_options.attempts == 1
    finally:
        gemini_module.genai.Client = original


def test_generate_text_handles_connection_failure_without_real_api_call():
    """Connection errors should become a clean application-level exception."""
    import ai.gemini as gemini_module

    class FailingModels:
        def generate_content(self, **kwargs):
            raise httpx.ConnectError("connection refused")

    fake_client = type("FakeClient", (), {"models": FailingModels()})()
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

    class TimeoutModels:
        def generate_content(self, **kwargs):
            raise httpx.ReadTimeout("request timed out")

    fake_client = type("FakeClient", (), {"models": TimeoutModels()})()
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

@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_or_blank_key_fails_before_client_creation(monkeypatch, key, capsys):
    from unittest.mock import Mock
    import main

    if key is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", key)
    client = Mock(side_effect=AssertionError("client must not be created"))
    monkeypatch.setattr("ai.gemini.genai.Client", client)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiProvider()
    assert main.handle_command("please help me find something") == []
    assert "AI service unavailable." in capsys.readouterr().out
    assert main.handle_command("help") == [{"action": "help", "target": "", "params": {}}]
    client.assert_not_called()


def test_configuration_precedence_for_key_and_model(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=file-key\nGEMINI_MODEL=file-model\n", encoding="utf-8"
    )
    monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: FakeClient())
    assert GeminiProvider().model_name == "file-model"
    monkeypatch.setenv("GEMINI_API_KEY", "shell-key")
    monkeypatch.setenv("GEMINI_MODEL", "shell-model")
    provider = GeminiProvider()
    assert (provider.api_key, provider.model_name) == ("shell-key", "shell-model")
    explicit = GeminiProvider(api_key="explicit-key", model_name="explicit-model")
    assert (explicit.api_key, explicit.model_name) == ("explicit-key", "explicit-model")
    # An explicitly empty shell key must not be replaced by the file key.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiProvider()


def test_model_default_and_parent_dotenv_search(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=file-key\nGEMINI_MODEL=\n", encoding="utf-8")
    child = tmp_path / "nested"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: FakeClient())
    provider = GeminiProvider()
    assert provider.api_key == "file-key"
    assert provider.model_name == GeminiProvider.DEFAULT_MODEL


@pytest.mark.parametrize("status", [200, 401, 429, 500])
def test_public_sdk_request_and_errors_with_mock_transport(monkeypatch, status, capsys):
    """Exercise SDK serialization and public exception mapping, without network."""
    import json
    from google import genai
    from google.genai import types
    from ai.gemini import GeminiProviderError

    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path.endswith("/models/test-model:generateContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        assert body["contents"][0]["parts"][0]["text"] == "private prompt"
        assert "tools" not in body
        assert request.extensions["timeout"]["read"] == 20.0
        if status == 200:
            return httpx.Response(200, json={"candidates": [{"content": {
                "parts": [{"text": "ok"}], "role": "model"
            }}]})
        return httpx.Response(status, json={"error": {
            "code": status, "message": "private provider payload", "status": "UNKNOWN"
        }})

    with genai.Client(api_key="test-key", http_options=types.HttpOptions(
        client_args={"transport": httpx.MockTransport(respond)}
    )) as client:
        monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: client)
        provider = GeminiProvider(api_key="test-key", model_name="test-model")
        if status == 200:
            assert provider.generate_text("private prompt") == "ok"
        else:
            with pytest.raises(GeminiProviderError, match="Gemini request failed"):
                provider.generate_text("private prompt")
    assert len(requests) == 1
    assert "private" not in capsys.readouterr().out


@pytest.mark.parametrize("response_text", [None, "", "   "])
def test_empty_response_is_controlled(monkeypatch, response_text):
    from ai.gemini import GeminiProviderError

    client = FakeClient()
    monkeypatch.setattr(client.models, "generate_content", lambda **kwargs: FakeContentResponse(response_text))
    monkeypatch.setattr("ai.gemini.genai.Client", lambda api_key: client)
    with pytest.raises(GeminiProviderError, match="no text"):
        GeminiProvider(api_key="test-key").generate_text("hello")
